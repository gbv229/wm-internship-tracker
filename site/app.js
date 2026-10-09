/* WM Internship Tracker front end. Reads data/*.json (written by the
   scraper) and renders the postings and firms tables. No build step. */
(() => {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const TODAY = new Date(); TODAY.setHours(0, 0, 0, 0);
  const DAY = 86400000;
  const parseDay = (s) => { if (!s) return null; const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
  const fmtDay = (d, withYear) => d.toLocaleDateString("en-US", { month: "short", day: "numeric", ...(withYear ? { year: "numeric" } : {}) });
  const daysUntil = (d) => Math.round((d - TODAY) / DAY);

  // Academic year: from July on, the year that ends next spring.
  const AY_END = TODAY.getMonth() >= 6 ? TODAY.getFullYear() + 1 : TODAY.getFullYear();
  const CLASS_NAMES = { [AY_END]: "Seniors", [AY_END + 1]: "Juniors", [AY_END + 2]: "Sophomores", [AY_END + 3]: "Freshmen" };
  const classLabel = (y) => CLASS_NAMES[y] ? `${CLASS_NAMES[y]} ’${String(y).slice(2)}` : `Class of ${y}`;

  const SEASON_ORDER = { Winter: 0, Spring: 1, Summer: 2, Fall: 3 };
  const seasonKey = (s) => { if (!s) return 99999; const [n, y] = s.split(" "); return +y * 10 + (SEASON_ORDER[n] ?? 5); };

  const state = {
    postings: [], firms: [], run: null, track: "wealth",
    cls: String(AY_END + 2), unstated: true, q: "", season: "upcoming", type: "", status: "active", level: "Undergraduate", region: "US", area: "",
    sort: "deadline", dir: 1, open: new Set(),
  };

  // ---------------------------------------------------------- url state
  const TRACKS = {
    wealth: { h1: "Wealth management internships",
      lede: (n) => `Internships at ${n} banks, private banks, brokerages, RIAs and wealthtech firms, pulled straight from their careers sites. Every role links to the employer's own posting.` },
    real_estate: { h1: "Real estate internships",
      lede: (n) => `Internships at ${n} brokerages, REITs, developers, real estate investors and lenders, pulled straight from their careers sites. Every role links to the employer's own posting.` },
  };
  const inTrack = (p) => (p.tracks || ["wealth"]).includes(state.track);
  const firmInTrack = (f) => (f.tracks || ["wealth"]).includes(state.track);

  const KEYS = ["track", "cls", "q", "season", "type", "status", "level", "region", "area", "sort", "dir"];
  function readHash() {
    const p = new URLSearchParams(location.hash.slice(1));
    KEYS.forEach((k) => { if (p.has(k)) state[k] = k === "dir" ? +p.get(k) : p.get(k); });
    if (p.has("unstated")) state.unstated = p.get("unstated") !== "0";
  }
  function writeHash() {
    const p = new URLSearchParams();
    KEYS.forEach((k) => p.set(k, state[k]));
    p.set("unstated", state.unstated ? "1" : "0");
    history.replaceState(null, "", "#" + p.toString());
  }

  // -------------------------------------------------------------- load
  async function load() {
    const get = (f) => fetch(`data/${f}?t=${Date.now()}`).then((r) => (r.ok ? r.json() : null)).catch(() => null);
    const [p, c, r] = await Promise.all([get("postings.json"), get("companies.json"), get("run.json")]);
    state.postings = (p?.postings || []).map(enrich);
    state.firms = c?.companies || [];
    state.run = r;
    readHash();
    if (!TRACKS[state.track]) state.track = "wealth";
    setupControls();
    applyTrack();
    renderFreshness();
    renderClosing();
    render();
    renderFirms();
    const repo = r?.repo && r.repo.includes("/") && !r.repo.startsWith("local") ? `https://github.com/${r.repo}` : null;
    ["repo-link", "repo-link-2"].forEach((id) => { const a = $("#" + id); if (repo) a.href = repo; else a.removeAttribute("href"); });
  }

  function applyTrack() {
    const t = TRACKS[state.track];
    document.querySelectorAll(".track-switch button").forEach((b) => b.setAttribute("aria-checked", b.dataset.track === state.track));
    $("#h1").textContent = t.h1;
    const n = state.firms.filter(firmInTrack).length;
    $("#lede").textContent = t.lede(n || "100+");
    document.title = `${t.h1} · Internship Tracker`;
  }

  function enrich(p) {
    const dl = parseDay(p.deadline);
    const status = p.status === "closed" ? "closed" : dl && dl < TODAY ? "past" : dl && daysUntil(dl) <= 14 ? "soon" : "open";
    return { ...p, _dl: dl, _posted: parseDay(p.posted), _first: parseDay(p.first_seen), _status: status,
      _new: p.first_seen && (TODAY - parseDay(p.first_seen)) / DAY <= 3,
      _hay: `${p.company} ${p.title} ${p.location} ${p.company_type} ${p.function}`.toLowerCase() };
  }

  // ----------------------------------------------------------- controls
  function setupControls() {
    const sw = document.querySelector(".track-switch");
    sw.addEventListener("click", (e) => {
      const b = e.target.closest("button"); if (!b || b.dataset.track === state.track) return;
      state.track = b.dataset.track;
      state.open.clear();
      applyTrack(); fillOptions(); renderClosing(); renderFirms(); update();
    });
    sw.addEventListener("keydown", (e) => {
      if (!["ArrowLeft", "ArrowRight"].includes(e.key)) return;
      const bs = [...sw.querySelectorAll("button")]; const n = bs.find((b) => b.dataset.track !== state.track);
      n.focus(); n.click();
    });
    const seg = $("#class-seg");
    const opts = [[String(AY_END + 3), "Freshmen", AY_END + 3], [String(AY_END + 2), "Sophomores", AY_END + 2],
      [String(AY_END + 1), "Juniors", AY_END + 1], [String(AY_END), "Seniors", AY_END], ["any", "Any class year", null]];
    seg.innerHTML = opts.map(([v, label, y]) =>
      `<button type="button" role="radio" data-v="${v}" aria-checked="${state.cls === v}">${label}${y ? `<small>’${String(y).slice(2)}</small>` : ""}</button>`).join("");
    seg.addEventListener("click", (e) => {
      const b = e.target.closest("button"); if (!b) return;
      state.cls = b.dataset.v;
      seg.querySelectorAll("button").forEach((x) => x.setAttribute("aria-checked", x === b));
      update();
    });
    seg.addEventListener("keydown", (e) => {
      if (!["ArrowLeft", "ArrowRight"].includes(e.key)) return;
      const bs = [...seg.querySelectorAll("button")]; const i = bs.findIndex((b) => b.dataset.v === state.cls);
      const n = bs[(i + (e.key === "ArrowRight" ? 1 : bs.length - 1)) % bs.length]; n.focus(); n.click();
    });

    fillOptions();

    const bind = (id, key, ev = "change") => { const el = $(id); el.value = state[key]; el.addEventListener(ev, () => { state[key] = el.value; update(); }); };
    bind("#f-q", "q", "input"); bind("#f-season", "season"); bind("#f-type", "type"); bind("#f-status", "status"); bind("#f-level", "level");
    bind("#f-region", "region"); bind("#f-area", "area");
    const un = $("#f-unstated"); un.checked = state.unstated; un.addEventListener("change", () => { state.unstated = un.checked; update(); });

    document.querySelectorAll("th button[data-sort]").forEach((b) => b.addEventListener("click", () => {
      const k = b.dataset.sort;
      if (state.sort === k) state.dir *= -1; else { state.sort = k; state.dir = k === "posted" ? -1 : 1; }
      update();
    }));
    $("#reset").addEventListener("click", () => {
      Object.assign(state, { cls: String(AY_END + 2), unstated: true, q: "", season: "upcoming", type: "", status: "active", level: "Undergraduate", sort: "deadline", dir: 1 });
      state.region = "US"; state.area = "";
      ["q", "season", "type", "status", "level", "region", "area"].forEach((k) => ($("#f-" + k).value = state[k]));
      un.checked = true;
      seg.querySelectorAll("button").forEach((x) => x.setAttribute("aria-checked", x.dataset.v === state.cls));
      update();
    });
    $("#csv").addEventListener("click", downloadCsv);

    $("#rows").addEventListener("click", (e) => {
      if (e.target.closest("a")) return;
      const tr = e.target.closest("tr.row"); if (!tr) return;
      toggleRow(tr);
    });
    $("#rows").addEventListener("keydown", (e) => {
      const tr = e.target.closest("tr.row");
      if (tr && (e.key === "Enter" || e.key === " ") && e.target === tr) { e.preventDefault(); toggleRow(tr); }
    });

    // tabs
    const tabs = [...document.querySelectorAll('[role="tab"]')];
    const show = (t) => {
      tabs.forEach((x) => { const on = x === t; x.setAttribute("aria-selected", on); x.tabIndex = on ? 0 : -1; $("#" + x.getAttribute("aria-controls")).hidden = !on; });
    };
    tabs.forEach((t, i) => {
      t.addEventListener("click", () => show(t));
      t.addEventListener("keydown", (e) => {
        if (!["ArrowLeft", "ArrowRight"].includes(e.key)) return;
        const n = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length]; n.focus(); show(n);
      });
    });

    ["#ff-q", "#ff-type", "#ff-mode"].forEach((id) => $(id).addEventListener(id === "#ff-q" ? "input" : "change", renderFirms));
  }

  // options that depend on the current field (wealth / real estate)
  function fillOptions() {
    const posts = state.postings.filter(inTrack), firms = state.firms.filter(firmInTrack);
    const seasons = [...new Set(posts.map((p) => p.season).filter(Boolean))].sort((a, b) => seasonKey(a) - seasonKey(b));
    const nowKey = TODAY.getFullYear() * 10 + (TODAY.getMonth() < 2 ? 0 : TODAY.getMonth() < 5 ? 1 : TODAY.getMonth() < 8 ? 2 : 3);
    const upcoming = seasons.filter((x) => seasonKey(x) >= nowKey);
    const past = seasons.filter((x) => seasonKey(x) < nowKey).reverse();
    $("#f-season").innerHTML = `<option value="upcoming">All upcoming seasons</option>` +
      upcoming.map((x) => `<option>${esc(x)}</option>`).join("") +
      `<option value="unknown">Season not stated</option>` +
      (past.length ? `<optgroup label="Past">${past.map((x) => `<option>${esc(x)}</option>`).join("")}</optgroup>` : "") +
      `<option value="all">Any season</option>`;
    const types = [...new Set(firms.map((f) => f.type).concat(posts.map((p) => p.company_type)))].filter(Boolean).sort();
    const areas = [...new Set(posts.map((p) => p.function).filter(Boolean))].sort();
    $("#f-area").innerHTML = `<option value="">All areas</option>` + areas.map((a) => `<option>${esc(a)}</option>`).join("");
    for (const id of ["#f-type", "#ff-type"]) $(id).innerHTML = `<option value="">All firm types</option>` + types.map((t) => `<option>${esc(t)}</option>`).join("");
    const keep = (id, key, fallback) => { const el = $(id); if (![...el.options].some((o) => o.value === state[key])) state[key] = fallback; el.value = state[key]; };
    keep("#f-season", "season", "upcoming"); keep("#f-type", "type", ""); keep("#f-area", "area", "");
  }

  function toggleRow(tr) {
    const id = tr.dataset.id;
    const det = tr.nextElementSibling;
    const open = det.hidden;
    det.hidden = !open;
    tr.setAttribute("aria-expanded", open);
    open ? state.open.add(id) : state.open.delete(id);
  }

  function update() { writeHash(); render(); }

  // ------------------------------------------------------------ filter
  function filtered() {
    const q = state.q.trim().toLowerCase();
    const nowKey = TODAY.getFullYear() * 10 + (TODAY.getMonth() < 2 ? 0 : TODAY.getMonth() < 5 ? 1 : TODAY.getMonth() < 8 ? 2 : 3);
    return state.postings.filter((p) => {
      if (!inTrack(p)) return false;
      if (state.status === "active" && !(p._status === "open" || p._status === "soon")) return false;
      if (state.status === "open" && p._status === "closed") return false;
      if (state.status === "closed" && p._status !== "closed") return false;
      if (state.level && p.level !== state.level) return false;
      if (state.type && p.company_type !== state.type) return false;
      if (state.area && p.function !== state.area) return false;
      if (state.region === "US" ? !(p.region === "US" || !p.region) : state.region && p.region !== state.region) return false;
      if (state.season === "upcoming") { if (p.season && seasonKey(p.season) < nowKey) return false; }
      else if (state.season === "unknown") { if (p.season) return false; }
      else if (state.season !== "all" && p.season !== state.season) return false;
      if (state.cls !== "any") {
        const c = p.classes || [];
        if (c.length ? !c.includes(+state.cls) : !state.unstated) return false;
      }
      if (q && !q.split(/\s+/).every((w) => p._hay.includes(w))) return false;
      return true;
    });
  }

  function sorted(list) {
    const k = state.sort, d = state.dir;
    const val = (p) => ({
      company: p.company.toLowerCase(), title: p.title.toLowerCase(), season: seasonKey(p.season),
      classes: (p.classes || [])[0] ?? 9999, deadline: p._dl ? +p._dl : null, posted: p._posted ? +p._posted : 0,
    })[k];
    return [...list].sort((a, b) => {
      const va = val(a), vb = val(b);
      if (va === null && vb !== null) return 1;      // no deadline always last
      if (vb === null && va !== null) return -1;
      if (va < vb) return -d; if (va > vb) return d;
      return (b._posted || 0) - (a._posted || 0);
    });
  }

  // ------------------------------------------------------------ render
  function render() {
    document.querySelectorAll("th button[data-sort]").forEach((b) => {
      if (b.dataset.sort === state.sort) b.setAttribute("aria-sort", state.dir === 1 ? "ascending" : "descending");
      else b.removeAttribute("aria-sort");
    });
    const list = sorted(filtered());
    const activeTotal = state.postings.filter(inTrack).filter((p) => p._status === "open" || p._status === "soon").length;
    $("#n-postings").textContent = activeTotal;
    $("#result-count").textContent = `${list.length} ${list.length === 1 ? "role" : "roles"}` +
      (state.cls !== "any" ? ` for ${CLASS_NAMES[+state.cls]?.toLowerCase() || "class of " + state.cls}` : "");

    $("#rows").innerHTML = list.map(rowHtml).join("");
    const empty = $("#empty");
    empty.hidden = list.length > 0;
    if (!list.length) {
      const reason = !state.postings.length
        ? `<strong>No postings yet</strong>The first update runs within 30 minutes of setup. Check the Firms tab for progress.`
        : `<strong>No roles match these filters</strong>Try "Any class year", "Any season", or including roles that don't state a class year.`;
      empty.innerHTML = reason;
    }
  }

  function rowHtml(p) {
    const cls = p.classes || [];
    const match = state.cls !== "any" && cls.includes(+state.cls);
    const elig = cls.length
      ? `<td class="elig${match ? " match" : ""}"><b>${cls.map(classLabel).join(", ")}</b></td>`
      : `<td class="elig unstated">Not stated</td>`;
    let dl;
    if (p._dl) {
      const n = daysUntil(p._dl);
      const sub = p._status === "closed" ? "" : n < 0 ? "passed" : n === 0 ? "today" : n === 1 ? "tomorrow" : `in ${n} days`;
      const c = n < 0 ? "past" : n <= 14 ? "soon" : "";
      dl = `<td class="dl ${c}">${fmtDay(p._dl, p._dl.getFullYear() !== TODAY.getFullYear())}${sub ? `<small>${sub}</small>` : ""}</td>`;
    } else dl = `<td class="dl none">Rolling / not stated</td>`;
    const posted = p._posted ? fmtDay(p._posted, p._posted.getFullYear() !== TODAY.getFullYear()) : "";
    const meta = [p.location, p.level === "Graduate/MBA" ? "MBA / graduate" : ""].filter(Boolean).join(" · ");
    const isOpen = state.open.has(p.id);
    const apply = p._status === "closed"
      ? `<span class="status-closed">Closed ${p.closed_on ? fmtDay(parseDay(p.closed_on)) : ""}</span>`
      : `<a href="${esc(p.url)}" target="_blank" rel="noopener" aria-label="Apply: ${esc(p.company)}, ${esc(p.title)} (opens employer site)">Apply</a>`;
    return `<tr class="row ${p._status === "closed" ? "closed" : ""}" data-id="${esc(p.id)}" tabindex="0" aria-expanded="${isOpen}">
      <td class="c-company"><span class="firm">${esc(p.company)}</span><span class="ftype">${esc(p.company_type)}</span></td>
      <td class="role">${esc(p.title)}${p._new ? '<span class="new">New</span>' : ""}${meta ? `<span class="role-meta">${esc(meta)}</span>` : ""}</td>
      <td class="c-season">${p.season ? esc(p.season) + (p.season_inferred ? '<span class="est" title="Year estimated from posting date">est.</span>' : "") : '<span class="est">Not stated</span>'}</td>
      ${elig}${dl}
      <td class="posted">${posted}</td>
      <td class="apply">${apply}</td>
    </tr>
    <tr class="detail" ${isOpen ? "" : "hidden"}><td colspan="7">${detailHtml(p)}</td></tr>`;
  }

  function detailHtml(p) {
    const items = [
      ["Pay", p.pay], ["Minimum GPA", p.gpa], ["Length", p.weeks ? `${p.weeks} weeks` : null],
      ["Work setup", p.work_mode], ["Visa sponsorship", p.sponsorship], ["Area", p.function],
      ["Location", p.location], ["First seen here", p._first ? fmtDay(p._first, true) : null],
    ].filter(([, v]) => v);
    const ev = [];
    if (p.class_evidence) ev.push(`<div class="evidence"><dt>Eligibility, from the posting</dt><dd><blockquote>${esc(p.class_evidence)}</blockquote></dd></div>`);
    if (p.deadline_evidence) ev.push(`<div class="evidence"><dt>Deadline, from the posting</dt><dd><blockquote>${esc(p.deadline_evidence)}</blockquote></dd></div>`);
    return `<dl class="detail-inner">${items.map(([k, v]) => `<div><dt>${k}</dt><dd>${esc(v)}</dd></div>`).join("")}${ev.join("")}
      ${!items.length && !ev.length ? `<div><dd>No extra details were listed. Open the posting for the full description.</dd></div>` : ""}</dl>`;
  }

  function renderClosing() {
    const soon = state.postings
      .filter((p) => inTrack(p) && p._dl && p._dl >= TODAY && p._status !== "closed" && p.level === "Undergraduate" && (p.region === "US" || !p.region))
      .sort((a, b) => a._dl - b._dl).slice(0, 5);
    const ol = $("#closing-list");
    if (!soon.length) {
      ol.innerHTML = `<li class="closing-empty">No upcoming deadlines are listed yet. Most programs review applications on a rolling basis, so apply as soon as a role opens.</li>`;
      return;
    }
    ol.innerHTML = soon.map((p) => {
      const n = daysUntil(p._dl);
      return `<li><a href="${esc(p.url)}" target="_blank" rel="noopener">
        <span class="c-date">${fmtDay(p._dl)}</span>
        <span class="c-left">${n === 0 ? "Today" : n === 1 ? "Tomorrow" : `${n} days left`}</span>
        <span class="c-firm">${esc(p.company)}</span>
        <span class="c-role">${esc(p.title)}</span></a></li>`;
    }).join("");
  }

  function renderFreshness() {
    const el = $("#freshness");
    const r = state.run;
    if (!r?.updated_at) { el.textContent = "Waiting for the first update."; return; }
    const t = new Date(r.updated_at);
    const mins = Math.max(0, Math.round((Date.now() - t) / 60000));
    const ago = mins < 1 ? "just now" : mins < 60 ? `${mins} min ago` : mins < 1440 ? `${Math.round(mins / 60)} hr ago` : `${Math.round(mins / 1440)} days ago`;
    el.classList.toggle("stale", mins > 120);
    el.innerHTML = `<span class="dot" aria-hidden="true"></span>Updated ${ago}. Checks every 30 minutes. ${r.sources_ok} of ${r.sources_total} careers sites reached on the last check.`;
  }

  // -------------------------------------------------------------- firms
  const blocked = (s) => s.kind === "page" && /\b(403|401|429)\b/.test(s.error || "");
  function firmMode(f) {
    const srcs = f.sources || [];
    if (srcs.some((s) => !s.ok && !blocked(s))) return "error";
    return srcs.every((s) => s.kind === "page") ? "page" : "feed";
  }
  function renderFirms() {
    const q = $("#ff-q").value.trim().toLowerCase(), t = $("#ff-type").value, m = $("#ff-mode").value;
    const openCount = {};
    state.postings.forEach((p) => { if (inTrack(p) && (p._status === "open" || p._status === "soon")) openCount[p.company] = (openCount[p.company] || 0) + 1; });
    const list = state.firms.filter(firmInTrack).filter((f) =>
      (!q || `${f.name} ${f.hq} ${f.type}`.toLowerCase().includes(q)) && (!t || f.type === t) &&
      (!m || firmMode(f) === m || (m === "page" && (f.sources || []).some((s) => s.kind === "page")) ))
      .sort((a, b) => (openCount[b.name] || 0) - (openCount[a.name] || 0) || a.name.localeCompare(b.name));
    $("#n-firms").textContent = state.firms.filter(firmInTrack).length;
    $("#firm-rows").innerHTML = list.map((f) => {
      const srcs = f.sources || [];
      const feeds = srcs.filter((s) => s.kind !== "page"), pages = srcs.filter((s) => s.kind === "page");
      const errs = srcs.filter((s) => !s.ok && !blocked(s));
      const isBlocked = srcs.some(blocked);
      let mode = feeds.length ? `<span class="mode${errs.length ? " err" : ""}"><i></i>Live feed</span>` : `<span class="mode page${errs.length ? " err" : ""}"><i></i>Page watch</span>`;
      if (isBlocked && !errs.length) mode += `<span class="role-meta">Site blocks automated checks — open the link</span>`;
      if (errs.length) mode += `<span class="err-msg">Couldn't reach ${errs.map((e) => e.kind).join(", ")}: ${esc((errs[0].error || "").slice(0, 120))}</span>`;
      const changed = pages.map((s) => s.changed_on).filter(Boolean).sort().pop();
      const links = pages.flatMap((s) => s.links || []).slice(0, 4);
      return `<tr>
        <td><a class="firm" href="${esc(f.careers)}" target="_blank" rel="noopener">${esc(f.name)}</a>
          ${links.length ? `<ul class="page-links">${links.map((l) => { const [txt, url] = l.split(" | "); return `<li><a href="${esc(url)}" target="_blank" rel="noopener">${esc(txt)}</a></li>`; }).join("")}</ul>` : ""}</td>
        <td>${esc(f.type)}</td><td>${esc(f.hq || "")}</td>
        <td class="num">${feeds.length ? openCount[f.name] || 0 : "—"}</td>
        <td>${mode}</td>
        <td>${changed ? `Page changed ${fmtDay(parseDay(changed))}` : f.last_ok ? `Checked ${fmtDay(parseDay(f.last_ok))}` : "Not checked yet"}</td>
      </tr>`;
    }).join("") || `<tr><td colspan="6" class="empty">No firms match.</td></tr>`;
  }

  // ---------------------------------------------------------------- csv
  function downloadCsv() {
    const rows = sorted(filtered());
    const cols = [["Firm", "company"], ["Firm type", "company_type"], ["Role", "title"], ["Season", "season"],
      ["Eligible classes", (p) => (p.classes || []).join(" ")], ["Deadline", "deadline"], ["Posted", "posted"],
      ["Location", "location"], ["Pay", "pay"], ["GPA", "gpa"], ["Weeks", "weeks"], ["Sponsorship", "sponsorship"],
      ["Status", (p) => ({ open: "Open", soon: "Closing soon", past: "Deadline passed", closed: "Closed" })[p._status]], ["Link", "url"]];
    const cell = (v) => { const s = String(v ?? ""); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
    const csv = [cols.map((c) => c[0]).join(","), ...rows.map((p) => cols.map(([, k]) => cell(typeof k === "function" ? k(p) : p[k])).join(","))].join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    a.download = `wm-internships-${TODAY.toISOString().slice(0, 10)}.csv`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  setInterval(renderFreshness, 60000);
  load();
})();
