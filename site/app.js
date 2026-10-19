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
    postings: [], firms: [], run: null, track: "wealth", tab: "postings", hidePass: true, newOnly: false,
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
  const US_REGIONS = ["Northeast", "Mid-Atlantic", "Southeast", "Midwest", "Southwest", "West", "Remote", "US"];
  // older records only have the coarse "region" field
  const regionsOf = (p) => p.regions || (p.region ? [p.region] : []);
  const isUS = (p) => { const r = regionsOf(p); return !r.length || r.some((x) => US_REGIONS.includes(x)); };
  function inRegion(p, want) {
    if (!want) return true;
    if (want === "US") return isUS(p);
    const r = regionsOf(p);
    return r.includes(want) || (US_REGIONS.includes(want) && r.includes("Remote"));
  }
  const fmtLoc = (loc) => {
    const parts = (loc || "").split(/;\s*/).filter(Boolean);
    return parts.length > 2 ? `${parts[0]}, ${parts[1]} + ${parts.length - 2} more` : parts.join("; ");
  };
  // firm logo: the firm's site icon over a coloured monogram (shown if the icon can't load)
  let DOMAINS = {};
  const STOP = /^(the|of|and|&|inc\.?|group|financial|incl\.?|co\.?)$/i;
  function initials(name) {
    const w = name.replace(/\(.*?\)/g, "").split(/[\s/]+/).filter((x) => x && !STOP.test(x));
    if (w.length === 1) return w[0].replace(/[^A-Za-z0-9]/g, "").slice(0, 2).toUpperCase();
    return (w[0][0] + w[1][0]).toUpperCase();
  }
  function hue(name) { let h = 0; for (const c of name) h = (h * 31 + c.charCodeAt(0)) % 360; return h; }
  function logoHtml(name) {
    const d = DOMAINS[name];
    const img = d ? `<img src="https://icons.duckduckgo.com/ip3/${esc(d)}.ico" alt="" loading="lazy" onload="if(this.naturalWidth>8)this.classList.add('ok');else this.remove()" onerror="this.remove()">` : "";
    return `<span class="logo" style="--logo-bg:hsl(${hue(name)} 38% 38%)" aria-hidden="true">${esc(initials(name))}${img}</span>`;
  }
  const inTrack = (p) => (p.tracks || ["wealth"]).includes(state.track);
  const firmInTrack = (f) => (f.tracks || ["wealth"]).includes(state.track);

  const KEYS = ["tab", "track", "cls", "q", "season", "type", "status", "level", "region", "area", "sort", "dir"];
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
    const [p, c, r, e, fn] = await Promise.all([get("postings.json"), get("companies.json"), get("run.json"), get("early_programs.json"), get("firm_notes.json")]);
    EARLY.list = e?.programs || [];
    EARLY.researched = e?.researched ? parseDay(e.researched) : null;
    FIRM_NOTES = fn || {};
    state.postings = (p?.postings || []).map(enrich);
    state.firms = c?.companies || [];
    state.firms.forEach((f) => { if (f.domain) DOMAINS[f.name] = f.domain; });
    state.run = r;
    readHash();
    if (!TRACKS[state.track]) state.track = "wealth";
    setupControls();
    applyTrack();
    renderFreshness();
    renderClosing();
    render();
    renderFirms();
    setupEarly();
    rememberSeen();
    if (state.tab && state.tab !== "postings") { const t = $(`[role="tab"][data-tab="${state.tab}"]`); if (t) t.click(); }
    const repo = r?.repo && r.repo.includes("/") && !r.repo.startsWith("local") ? `https://github.com/${r.repo}` : null;
    ["repo-link", "repo-link-2"].forEach((id) => { const a = $("#" + id); if (repo) a.href = repo; else a.removeAttribute("href"); });
  }

  function applyTrack() {
    const t = TRACKS[state.track];
    const fl = $("#feed-link");
    if (fl) { fl.href = state.track === "real_estate" ? "data/feed-real-estate.xml" : "data/feed-wealth.xml"; fl.textContent = `${state.track === "real_estate" ? "Real estate" : "Wealth management"} RSS feed`; }
    document.documentElement.dataset.track = state.track;
    const tc = document.querySelector('meta[name="theme-color"]');
    if (tc) tc.content = state.track === "real_estate" ? "#172f5c" : "#0d3b30";
    document.querySelectorAll(".track-switch button").forEach((b) => b.setAttribute("aria-checked", b.dataset.track === state.track));
    $("#h1").textContent = t.h1;
    const n = state.firms.filter(firmInTrack).length;
    $("#lede").textContent = t.lede(n || "100+");
    document.title = `${t.h1} · Internship Tracker`;
  }

  // ===================================================== local storage
  // Everything personal stays in this browser. Storage can be unavailable
  // (private mode, blocked cookies), so every access is guarded and the page
  // still works without it.
  const mem = {};
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v == null ? (k in mem ? mem[k] : d) : JSON.parse(v); } catch { return k in mem ? mem[k] : d; } },
    set(k, v) { mem[k] = v; try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* in-memory only */ } },
  };

  // ------------------------------------------------- new since last visit
  const PREV_SEEN = new Set(store.get("it.seenIds", []));
  const FIRST_VISIT = PREV_SEEN.size === 0;
  function rememberSeen() { store.set("it.seenIds", state.postings.filter((p) => p.status === "open").map((p) => p.id)); }

  // ----------------------------------------------------- tracker
  const STATUSES = [["saved", "Saved"], ["applied", "Applied"], ["interviewing", "Interviewing"], ["offer", "Offer"],
    ["rejected", "Rejected"], ["pass", "Not for me"]];
  const STATUS_LABEL = Object.fromEntries(STATUSES);
  let TRACK = store.get("it.tracker.v1", {});
  function setStatus(id, status, info) {
    if (!status || (TRACK[id] && TRACK[id].s === status)) delete TRACK[id];
    else TRACK[id] = { ...(TRACK[id] || {}), ...info, s: status, t: new Date().toISOString().slice(0, 10) };
    store.set("it.tracker.v1", TRACK);
  }
  function infoFor(id, kind) {
    if (kind === "program") {
      const p = EARLY.list.find((x) => x.id === id);
      return p ? { kind, company: p.firm, title: p.program, url: p.link, deadline: p.deadline } : { kind };
    }
    const p = state.postings.find((x) => x.id === id);
    return p ? { kind, company: p.company, title: p.title, url: p.url, deadline: p.deadline, location: p.location } : { kind };
  }
  function trackerControls(id, kind) {
    const cur = TRACK[id]?.s;
    return `<div class="tracker" data-id="${esc(id)}" data-kind="${kind}" role="group" aria-label="My status">
      <span class="tracker-label">My status</span>
      ${STATUSES.map(([v, l]) => `<button type="button" data-s="${v}" aria-pressed="${cur === v}">${l}</button>`).join("")}
    </div>`;
  }
  function onTrackerClick(e) {
    const b = e.target.closest(".tracker button, .star"); if (!b) return false;
    e.stopPropagation();
    const box = b.closest("[data-id]"), id = box.dataset.id, kind = box.dataset.kind || "posting";
    setStatus(id, b.dataset.s, infoFor(id, kind));
    refreshTracked();
    return true;
  }
  function refreshTracked() {
    document.querySelectorAll(".tracker").forEach((t) => {
      const cur = TRACK[t.dataset.id]?.s;
      t.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.s === cur));
    });
    document.querySelectorAll(".star").forEach((b) => {
      const cur = TRACK[b.closest("[data-id]").dataset.id]?.s;
      b.setAttribute("aria-pressed", !!cur);
      b.textContent = cur ? STATUS_LABEL[cur] : "Save";
      b.dataset.s = cur || "saved";
      b.className = `star${cur ? " on st-" + cur : ""}`;
    });
    $("#n-mine").textContent = Object.keys(TRACK).length || "";
    renderMine();
  }

  function renderMine() {
    const ids = Object.keys(TRACK);
    const box = $("#mine-list");
    if (!box) return;
    if (!ids.length) {
      $("#mine-summary").innerHTML = "";
      box.innerHTML = `<div class="empty"><strong>Nothing saved yet</strong>Click "Save" on any role, or open a role or program and set its status, and it'll show up here.</div>`;
      return;
    }
    const counts = {};
    ids.forEach((id) => (counts[TRACK[id].s] = (counts[TRACK[id].s] || 0) + 1));
    $("#mine-summary").innerHTML = STATUSES.filter(([v]) => counts[v]).map(([v, l]) => `<span class="mine-chip st-${v}"><b>${counts[v]}</b> ${l}</span>`).join("");
    const live = new Map(state.postings.map((p) => [p.id, p]));
    const prog = new Map(EARLY.list.map((p) => [p.id, p]));
    box.innerHTML = STATUSES.filter(([v]) => counts[v]).map(([v, l]) => {
      const rows = ids.filter((id) => TRACK[id].s === v).map((id) => {
        const t = TRACK[id], lp = live.get(id), pp = prog.get(id);
        const closed = lp ? lp._status === "closed" : (!pp && t.kind === "posting");
        const dl = parseDay((lp && lp.deadline) || (pp && pp.deadline) || t.deadline);
        return `<article class="mine-row" data-id="${esc(id)}" data-kind="${esc(t.kind || "posting")}">
          ${logoHtml(t.company || "?")}
          <div class="mine-main"><span class="prog-firm">${esc(t.company || "")}</span>
            <h4><a href="${esc(t.url || "#")}" target="_blank" rel="noopener">${esc(t.title || id)}</a></h4>
            <p class="prog-when">${esc([t.kind === "program" ? "Early program" : t.location, dl ? `Deadline ${fmtFull(dl)}` : "", closed ? "No longer listed" : "", `Updated ${t.t}`].filter(Boolean).join(" · "))}</p>
          </div>
          ${trackerControls(id, t.kind || "posting")}
        </article>`;
      }).join("");
      return `<section class="egroup"><h3 class="egroup-h">${l} <span>${counts[v]}</span></h3>${rows}</section>`;
    }).join("");
  }

  function mineCsv() {
    const cols = ["status", "company", "title", "deadline", "updated", "kind", "url", "id"];
    const cell = (v) => { const x = String(v ?? ""); return /[",\n]/.test(x) ? `"${x.replace(/"/g, '""')}"` : x; };
    const rows = Object.entries(TRACK).map(([id, t]) => [STATUS_LABEL[t.s], t.company, t.title, t.deadline, t.t, t.kind, t.url, id].map(cell).join(","));
    download([cols.join(","), ...rows].join("\n"), `my-internship-list-${TODAY.toISOString().slice(0, 10)}.csv`, "text/csv");
  }
  function parseCsv(text) {
    const out = []; let row = [], cur = "", q = false;
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (q) { if (c === '"' && text[i + 1] === '"') { cur += '"'; i++; } else if (c === '"') q = false; else cur += c; }
      else if (c === '"') q = true; else if (c === ",") { row.push(cur); cur = ""; }
      else if (c === "\n" || c === "\r") { if (c === "\r" && text[i + 1] === "\n") i++; row.push(cur); out.push(row); row = []; cur = ""; }
      else cur += c;
    }
    if (cur || row.length) { row.push(cur); out.push(row); }
    return out;
  }
  function mineImport(file) {
    const r = new FileReader();
    r.onload = () => {
      const rows = parseCsv(String(r.result)); const head = rows.shift() || [];
      const ix = (k) => head.indexOf(k);
      const byLabel = Object.fromEntries(STATUSES.map(([v, l]) => [l, v]));
      let n = 0;
      rows.forEach((c) => {
        const id = c[ix("id")], s = byLabel[c[ix("status")]];
        if (!id || !s) return;
        TRACK[id] = { s, company: c[ix("company")], title: c[ix("title")], deadline: c[ix("deadline")] || null,
          t: c[ix("updated")] || TODAY.toISOString().slice(0, 10), kind: c[ix("kind")] || "posting", url: c[ix("url")] };
        n++;
      });
      store.set("it.tracker.v1", TRACK); refreshTracked();
      alert(`Restored ${n} saved ${n === 1 ? "item" : "items"}.`);
    };
    r.readAsText(file);
  }
  function download(text, name, type) {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([text], { type })); a.download = name; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  function enrich(p) {
    const dl = parseDay(p.deadline);
    const status = p.status === "closed" ? "closed" : dl && dl < TODAY ? "past" : dl && daysUntil(dl) <= 14 ? "soon" : "open";
    return { ...p, _dl: dl, _posted: parseDay(p.posted), _first: parseDay(p.first_seen), _status: status,
      _new: FIRST_VISIT ? p.first_seen && (TODAY - parseDay(p.first_seen)) / DAY <= 3 : !PREV_SEEN.has(p.id) && p.status === "open",
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
    $("#hide-pass").addEventListener("change", (e) => { state.hidePass = e.target.checked; render(); });
    $("#new-only").addEventListener("change", (e) => { state.newOnly = e.target.checked; render(); });
    $("#mine-list").addEventListener("click", onTrackerClick);
    $("#early-list").addEventListener("click", onTrackerClick, true);
    $("#mine-csv").addEventListener("click", mineCsv);
    $("#mine-import").addEventListener("change", (e) => { if (e.target.files[0]) mineImport(e.target.files[0]); e.target.value = ""; });

    $("#rows").addEventListener("click", (e) => {
      if (onTrackerClick(e)) return;
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
      state.tab = t.dataset.tab; writeHash();
    };
    tabs.forEach((t, i) => {
      t.addEventListener("click", () => show(t));
      t.addEventListener("keydown", (e) => {
        if (!["ArrowLeft", "ArrowRight"].includes(e.key)) return;
        const n = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length]; n.focus(); show(n);
      });
    });

    $("#region-buttons").addEventListener("click", (e) => {
      const b = e.target.closest("button"); if (!b) return;
      pickRegion(b.dataset.v);
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
  function filtered(ignoreRegion = false) {
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
      if (!ignoreRegion && !inRegion(p, state.region)) return false;
      if (state.season === "upcoming") { if (p.season && seasonKey(p.season) < nowKey) return false; }
      else if (state.season === "unknown") { if (p.season) return false; }
      else if (state.season !== "all" && p.season !== state.season) return false;
      if (state.cls !== "any") {
        const c = p.classes || [];
        if (c.length ? !c.includes(+state.cls) : !state.unstated) return false;
      }
      if (q && !q.split(/\s+/).every((w) => p._hay.includes(w))) return false;
      if (state.hidePass && TRACK[p.id]?.s === "pass") return false;
      if (state.newOnly && !p._new) return false;
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
    const flat = sorted(filtered());
    // one row per role: the same program posted for many offices is grouped
    const gmap = new Map();
    flat.forEach((p) => { const k = p.group || `${p.company}|${p.title}`; if (!gmap.has(k)) gmap.set(k, []); gmap.get(k).push(p); });
    const list = [...gmap.values()];
    GROUPS = new Map(list.map((g) => [g[0].id, g]));
    const activeTotal = state.postings.filter(inTrack).filter((p) => p._status === "open" || p._status === "soon").length;
    $("#n-postings").textContent = activeTotal;
    $("#result-count").innerHTML = `<b>${list.length}</b> ${list.length === 1 ? "role" : "roles"}` +
      (flat.length > list.length ? ` <span class="muted">(${flat.length} postings across offices)</span>` : "") +
      (state.cls !== "any" ? ` for ${esc(CLASS_NAMES[+state.cls]?.toLowerCase() || "class of " + state.cls)}` : "") +
      (state.region && state.region !== "US" ? ` in ${esc(REGION_LABEL[state.region] || state.region)}` : "");
    renderStats();
    renderMap();

    $("#rows").innerHTML = list.map((g) => rowHtml(g[0], g)).join("");
    refreshTracked();
    const nNew = state.postings.filter((p) => inTrack(p) && p._new && p.status === "open").length;
    $("#new-only-wrap").hidden = FIRST_VISIT || (!nNew && !state.newOnly);
    $("#new-only-label").textContent = `Only new since my last visit (${nNew})`;
    const empty = $("#empty");
    empty.hidden = list.length > 0;
    if (!list.length) {
      const reason = !state.postings.length
        ? `<strong>No postings yet</strong>The first update runs within 30 minutes of setup. Check the Firms tab for progress.`
        : `<strong>No roles match these filters</strong>Try "Any class year", "Any season", or including roles that don't state a class year.`;
      empty.innerHTML = reason;
    }
  }

  // ===================================================== early programs
  const EARLY = { list: [], type: "", field: "", status: "active", q: "" };
  const TYPE_LABEL = { sophomore: "Sophomore program", insight: "Insight program", fellowship: "Fellowship",
    first_year: "First-year program", summer_2028: "Summer 2028 internship", training: "Training", ambassador: "Campus ambassadors" };
  const TYPE_FILTERS = [["", "All"], ["sophomore", "Sophomore programs"], ["insight", "Insight days & fellowships"],
    ["summer_2028", "Summer 2028 internships"], ["first_year", "First-year"], ["training", "Training"], ["ambassador", "Ambassadors"]];
  const fmtFull = (d) => fmtDay(d, d.getFullYear() !== TODAY.getFullYear());
  const ymd = (d) => `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}${String(d.getDate()).padStart(2, "0")}`;

  function earlyState(p) {
    const op = parseDay(p.opens), dl = parseDay(p.deadline);
    const est = (flag) => (flag ? " (est.)" : "");
    if (p.status === "invite") return { k: "invite", label: "By invitation" };
    if (p.status === "closed" || (dl && dl < TODAY))
      return { k: "closed", label: dl ? `${p.deadline_est ? "Likely closed" : "Closed"} ${fmtFull(dl)}` : "Closed" };
    if (op && op > TODAY) return { k: "upcoming", label: `Opens ${fmtFull(op)}${est(p.opens_est)}`, date: op };
    if (p.status === "open" || (op && !p.opens_est))
      return { k: "open", label: dl ? `Open · due ${fmtFull(dl)}${est(p.deadline_est)}` : "Open now", date: dl };
    if (op && p.opens_est) return { k: "check", label: "Expected to be open – check", date: dl };
    if (dl) return { k: "check", label: `Due ${fmtFull(dl)}${est(p.deadline_est)} – check if open`, date: dl };
    return { k: "watch", label: "No date yet" };
  }

  // calendar events for one program (mirrors scraper/early.py)
  function earlyEvents(p) {
    if (p.status === "closed" || p.status === "invite") return [];
    const name = `${p.firm} – ${p.program}`;
    const desc = [p.eligibility, p.when, p.opens_note, p.deadline_note, p.notes, p.link].filter(Boolean).join("\n");
    const out = [];
    const op = parseDay(p.opens), dl = parseDay(p.deadline);
    if (op && op >= TODAY) out.push({ uid: `${p.id}-opens`, d: op, kind: "opens",
      summary: `${p.opens_est ? "Expected to open" : "Opens"}: ${name}`, desc, alarms: ["-PT15H", "PT9H"] });
    if (dl && dl >= TODAY) out.push({ uid: `${p.id}-deadline`, d: dl, kind: "deadline",
      summary: `${p.deadline_est ? "Likely deadline" : "Deadline"}: ${name}`, desc, alarms: ["-P6DT15H", "-P1DT15H", "-PT15H"] });
    return out;
  }
  const icsEsc = (t) => String(t || "").replace(/\\/g, "\\\\").replace(/;/g, "\\;").replace(/,/g, "\\,").replace(/\n/g, "\\n");
  function icsFor(events) {
    const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d+/, "");
    const L = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//WM Internship Tracker//Early programs//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH"];
    events.forEach((e) => {
      const next = new Date(e.d); next.setDate(next.getDate() + 1);
      L.push("BEGIN:VEVENT", `UID:${e.uid}@wm-internship-tracker`, `DTSTAMP:${stamp}`, `DTSTART;VALUE=DATE:${ymd(e.d)}`,
        `DTEND;VALUE=DATE:${ymd(next)}`, `SUMMARY:${icsEsc(e.summary)}`, `DESCRIPTION:${icsEsc(e.desc)}`, "TRANSP:TRANSPARENT");
      e.alarms.forEach((a) => L.push("BEGIN:VALARM", "ACTION:DISPLAY", `DESCRIPTION:${icsEsc(e.summary)}`, `TRIGGER:${a}`, "END:VALARM"));
      L.push("END:VEVENT");
    });
    L.push("END:VCALENDAR");
    return L.join("\r\n") + "\r\n";
  }
  function gcalLink(e) {
    const next = new Date(e.d); next.setDate(next.getDate() + 1);
    const q = new URLSearchParams({ action: "TEMPLATE", text: e.summary, dates: `${ymd(e.d)}/${ymd(next)}`, details: e.desc });
    return `https://calendar.google.com/calendar/render?${q}`;
  }

  function setupEarly() {
    const feed = new URL("data/early-programs.ics", location.href.split("#")[0]);
    const webcal = feed.href.replace(/^https?:/, "webcal:");
    $("#cal-google").href = `https://calendar.google.com/calendar/render?cid=${encodeURIComponent(webcal)}`;
    $("#cal-webcal").href = webcal;

    const seg = $("#early-type");
    seg.innerHTML = TYPE_FILTERS.map(([v, l]) => `<button type="button" role="radio" data-v="${v}" aria-checked="${EARLY.type === v}">${l}</button>`).join("");
    seg.addEventListener("click", (e) => {
      const b = e.target.closest("button"); if (!b) return;
      EARLY.type = b.dataset.v;
      seg.querySelectorAll("button").forEach((x) => x.setAttribute("aria-checked", x === b));
      renderEarly();
    });
    $("#e-q").addEventListener("input", (e) => { EARLY.q = e.target.value; renderEarly(); });
    $("#e-field").addEventListener("change", (e) => { EARLY.field = e.target.value; renderEarly(); });
    $("#e-status").addEventListener("change", (e) => { EARLY.status = e.target.value; renderEarly(); });
    $("#early-list").addEventListener("click", (e) => {
      const b = e.target.closest(".btn-remind"); if (!b) return;
      const p = EARLY.list.find((x) => x.id === b.dataset.id); if (!p) return;
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([icsFor(earlyEvents(p))], { type: "text/calendar" }));
      a.download = `${p.id}.ics`; a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
      b.textContent = "Added – open the file";
    });
    $("#early-note").innerHTML = `Campus ambassadors at J.P. Morgan and Goldman Sachs are picked from past interns, so there's no public application. They're listed so you know to ask during your internship. Programs last researched ${EARLY.researched ? fmtFull(EARLY.researched) : "recently"}; rows marked <span class="pill live">Live posting</span> come straight from firm job boards and update every 30 minutes.`;
    renderEarly();
  }

  function renderEarly() {
    const q = EARLY.q.trim().toLowerCase();
    const items = EARLY.list.map((p) => ({ p, st: earlyState(p) })).filter(({ p, st }) => {
      if (EARLY.type && !(p.type === EARLY.type || (EARLY.type === "insight" && p.type === "fellowship"))) return false;
      if (EARLY.field === "wealth" && !["wealth", "asset_mgmt", "multi"].includes(p.field)) return false;
      if (EARLY.field === "real_estate" && p.field !== "real_estate") return false;
      if (EARLY.field === "banking" && !["banking", "multi"].includes(p.field)) return false;
      if (EARLY.status === "active" && st.k === "closed") return false;
      if (EARLY.status === "open" && !["open", "check"].includes(st.k)) return false;
      if (EARLY.status === "closed" && st.k !== "closed") return false;
      if (q && !`${p.firm} ${p.program} ${p.eligibility || ""}`.toLowerCase().includes(q)) return false;
      return true;
    });
    $("#n-early").textContent = EARLY.list.filter((p) => earlyState(p).k !== "closed").length;

    const groups = new Map();
    const add = (key, label, order, it) => { if (!groups.has(key)) groups.set(key, { label, order, items: [] }); groups.get(key).items.push(it); };
    items.forEach((it) => {
      const { k, date } = it.st;
      if (k === "open" || k === "check") add("open", "Open now – apply", 0, it);
      else if (k === "upcoming") {
        const m = date.toLocaleDateString("en-US", { month: "long", year: "numeric" });
        add("m" + date.getFullYear() * 100 + date.getMonth(), `Opening ${m}`, 1 + date.getFullYear() * 100 + date.getMonth(), it);
      } else if (k === "watch") add("watch", "No date announced yet – watch these", 900000, it);
      else if (k === "invite") add("invite", "By invitation", 900001, it);
      else add("closed", "Closed this cycle", 900002, it);
    });
    const byDate = (a, b) => ((a.st.date || 9e15) - (b.st.date || 9e15)) || a.p.firm.localeCompare(b.p.firm);
    const html = [...groups.values()].sort((a, b) => a.order - b.order).map((g) =>
      `<section class="egroup"><h3 class="egroup-h">${esc(g.label)} <span>${g.items.length}</span></h3>
        ${g.items.sort(byDate).map(progHtml).join("")}</section>`).join("");
    $("#early-list").innerHTML = html || `<div class="empty"><strong>Nothing matches</strong>Try "Everything" or a different program type.</div>`;
  }

  function progHtml({ p, st }) {
    const op = parseDay(p.opens), dl = parseDay(p.deadline);
    const dateCell = (lbl, d, est, note) => `<div><dt>${lbl}</dt><dd>${d ? `${fmtFull(d)}${est ? ' <span class="est-tag">est.</span>' : ""}` : '<span class="muted">Not announced</span>'}</dd></div>`;
    const evs = earlyEvents(p);
    const next = evs[0];
    const openish = st.k === "open" || st.k === "check";
    return `<article class="prog st-${st.k}">
      ${logoHtml(p.firm)}
      <div class="prog-main">
        <div class="prog-top"><span class="prog-firm">${esc(p.firm)}</span><span class="pill">${esc(TYPE_LABEL[p.type] || p.type)}</span>${p.origin === "live" ? '<span class="pill live">Live posting</span>' : ""}</div>
        <h4>${esc(p.program)}</h4>
        ${p.eligibility ? `<p class="prog-elig">${esc(p.eligibility)}</p>` : ""}
        ${p.when || p.notes ? `<p class="prog-when">${esc([p.when, p.notes].filter(Boolean).join(" · "))}</p>` : ""}
        ${p.opens_note || p.deadline_note ? `<p class="prog-why">${esc([p.opens_note, p.deadline_note].filter(Boolean).join(" "))}</p>` : ""}
      </div>
      <div class="prog-side">
        <span class="state">${esc(st.label)}</span>
        <dl class="prog-dates">${dateCell("Opens", op, p.opens_est)}${dateCell("Deadline", dl, p.deadline_est)}</dl>
        ${trackerControls(p.id, "program")}
        <div class="prog-actions">
          <a class="btn-go" href="${esc(p.link)}" target="_blank" rel="noopener">${openish && p.status !== "invite" ? "Apply" : "Program page"}</a>
          ${evs.length ? `<button type="button" class="btn-remind" data-id="${esc(p.id)}">Remind me</button>` : ""}
          ${next ? `<a class="gcal" href="${esc(gcalLink(next))}" target="_blank" rel="noopener" title="Add the ${next.kind === "opens" ? "opening date" : "deadline"} to Google Calendar">Google Calendar</a>` : ""}
          ${p.source && p.source !== p.link ? `<a class="src" href="${esc(p.source)}" target="_blank" rel="noopener">Date source</a>` : ""}
        </div>
      </div>
    </article>`;
  }

  // ------------------------------------------------------- hero stats
  function renderStats() {
    const act = state.postings.filter((p) => inTrack(p) && (p._status === "open" || p._status === "soon") && p.level === "Undergraduate");
    const firms = new Set(act.map((p) => p.company)).size;
    const week = act.filter((p) => p._posted && (TODAY - p._posted) / DAY <= 7).length;
    const soph = act.filter((p) => (p.classes || []).includes(AY_END + 2)).length;
    const items = [
      [act.length, "open roles", "", true], [firms, "firms hiring", "", false],
      ...(FIRST_VISIT ? [[week, "posted this week", "hot", false]]
        : [[act.filter((p) => p._new).length, "new since your last visit", "hot newstat", false]]), [soph, `open to sophomores ’${String(AY_END + 2).slice(2)}`, "", false],
    ].filter(([n, , , always]) => always || n > 0);
    $("#stats").innerHTML = items.map(([n, l, c]) => c.includes("newstat")
      ? `<li class="${c}"><button type="button" id="new-stat" aria-pressed="${state.newOnly}"><b>${n}</b><span>${l}</span></button></li>`
      : `<li class="${c}"><b>${n}</b><span>${l}</span></li>`).join("");
    const ns = $("#new-stat");
    if (ns) ns.onclick = () => {
      state.newOnly = !state.newOnly; $("#new-only").checked = state.newOnly;
      $("#tab-postings").click(); render();
      $("#results").scrollIntoView({ behavior: "smooth", block: "start" });
    };
  }

  // --------------------------------------------------------------- map
  // tile-grid US map: [state, column, row]
  const TILES = [["AK",0,0],["ME",10,0],["WI",5,1],["VT",9,1],["NH",10,1],
    ["WA",0,2],["ID",1,2],["MT",2,2],["ND",3,2],["MN",4,2],["IL",5,2],["MI",6,2],["NY",8,2],["MA",9,2],
    ["OR",0,3],["NV",1,3],["WY",2,3],["SD",3,3],["IA",4,3],["IN",5,3],["OH",6,3],["PA",7,3],["NJ",8,3],["CT",9,3],["RI",10,3],
    ["CA",0,4],["UT",1,4],["CO",2,4],["NE",3,4],["MO",4,4],["KY",5,4],["WV",6,4],["VA",7,4],["MD",8,4],["DE",9,4],
    ["AZ",1,5],["NM",2,5],["KS",3,5],["AR",4,5],["TN",5,5],["NC",6,5],["SC",7,5],["DC",8,5],
    ["OK",3,6],["LA",4,6],["MS",5,6],["AL",6,6],["GA",7,6],["HI",0,7],["TX",3,7],["FL",8,7]];
  const STATE_REGION = {};
  Object.entries({ Northeast: "CT ME MA NH RI VT NY NJ PA", "Mid-Atlantic": "DE MD DC VA WV",
    Southeast: "NC SC GA FL AL MS TN KY AR LA", Midwest: "OH IN IL MI WI MN IA MO KS NE ND SD",
    Southwest: "TX OK NM AZ", West: "CA OR WA NV UT CO ID MT WY AK HI" })
    .forEach(([r, codes]) => codes.split(" ").forEach((c) => (STATE_REGION[c] = r)));
  const REGION_LABEL = { Northeast: "the Northeast", "Mid-Atlantic": "the Mid-Atlantic", Southeast: "the Southeast",
    Midwest: "the Midwest", Southwest: "the Southwest", West: "the West", Canada: "Canada", International: "outside the US & Canada" };
  let mapBuilt = false;

  function renderMap() {
    const svg = $("#map");
    const S = 38, G = 3;
    if (!mapBuilt) {
      svg.innerHTML = TILES.map(([st, c, r], i) =>
        `<g class="tile" data-st="${st}" style="--i:${c + r}" transform="translate(${c * (S + G) + 1},${r * (S + G) + 1})">
          <title>${st}</title><rect width="${S}" height="${S}"/><text x="${S / 2}" y="${S / 2 - 6}">${st}</text><text class="n" x="${S / 2}" y="${S / 2 + 8}"></text></g>`).join("");
      svg.classList.add("intro");
      setTimeout(() => svg.classList.remove("intro"), 1400);
      svg.addEventListener("click", (e) => {
        const g = e.target.closest(".tile"); if (!g) return;
        pickRegion(STATE_REGION[g.dataset.st]);
      });
      mapBuilt = true;
    }
    // counts ignore the region filter so the map shows where else you could look
    const base = filtered(true);
    const byState = {}, byRegion = {};
    let us = 0;
    base.forEach((p) => {
      const rs = regionsOf(p);
      if (isUS(p)) us++;
      rs.forEach((r) => (byRegion[r] = (byRegion[r] || 0) + 1));
      (p.states || []).forEach((st) => (byState[st] = (byState[st] || 0) + 1));
    });
    const max = Math.max(1, ...Object.values(byState));
    const style = getComputedStyle(document.documentElement);
    const accent = style.getPropertyValue("--accent").trim(), hero2 = style.getPropertyValue("--hero-2").trim();
    svg.querySelectorAll(".tile").forEach((g) => {
      const st = g.dataset.st, n = byState[st] || 0, reg = STATE_REGION[st];
      const t = n ? 0.28 + 0.72 * Math.sqrt(n / max) : 0;
      const rect = g.querySelector("rect");
      rect.style.fill = n ? `color-mix(in srgb, ${accent} ${Math.round(t * 100)}%, ${hero2})` : "rgba(255,255,255,.05)";
      const dark = t > 0.62;
      g.querySelectorAll("text").forEach((x) => (x.style.fill = dark ? "var(--accent-ink)" : "var(--on-hero)"));
      g.querySelector(".n").textContent = n || "";
      g.querySelector("title").textContent = `${st}: ${n} ${n === 1 ? "role" : "roles"} · ${reg}`;
      const regionOn = US_REGIONS.includes(state.region) && state.region !== "US";
      g.classList.toggle("dim", regionOn && reg !== state.region);
      g.classList.toggle("sel", regionOn && reg === state.region);
    });
    $("#map-sub").textContent = `${us} US ${us === 1 ? "role" : "roles"} matching your filters`;
    const btns = [["US", "All US", us], ...["Northeast", "Mid-Atlantic", "Southeast", "Midwest", "Southwest", "West"].map((r) => [r, r, (byRegion[r] || 0) + (byRegion.Remote || 0)]),
      ["International", "Outside US", (byRegion.International || 0) + (byRegion.Canada || 0)]];
    $("#region-buttons").innerHTML = btns.map(([v, l, n]) =>
      `<button type="button" data-v="${v}" aria-pressed="${state.region === v || (v === "International" && state.region === "Canada")}">${l}<b>${n}</b></button>`).join("");
  }

  function pickRegion(r) {
    state.region = state.region === r ? "US" : r;
    $("#f-region").value = state.region;
    update();
  }

  let GROUPS = new Map();
  function rowHtml(p, members = [p]) {
    const multi = members.length > 1;
    const cls = p.classes || [];
    const elig = cls.length
      ? `<td class="elig">${cls.map((y) => `<span class="pill${state.cls !== "any" && y === +state.cls ? " match" : ""}">${classLabel(y)}</span>`).join("")}</td>`
      : `<td class="elig unstated">Not stated</td>`;
    let dl;
    if (p._dl) {
      const n = daysUntil(p._dl);
      const sub = p._status === "closed" ? "" : n < 0 ? "passed" : n === 0 ? "today" : n === 1 ? "tomorrow" : `in ${n} days`;
      const c = n < 0 ? "past" : n <= 14 ? "soon" : "";
      dl = `<td class="dl ${c}"><span class="pill">${fmtDay(p._dl, p._dl.getFullYear() !== TODAY.getFullYear())}</span>${sub ? `<small>${sub}</small>` : ""}</td>`;
    } else {
      const age = p._posted ? Math.round((TODAY - p._posted) / DAY) : null;
      const ageTxt = age == null ? "" : age <= 0 ? "posted today" : age === 1 ? "posted yesterday" : `posted ${age} days ago`;
      dl = `<td class="dl none" title="No deadline stated. Most firms review on a rolling basis, so earlier is better."><span class="pill rolling">Rolling</span>${ageTxt ? `<small>${ageTxt}${age > 45 ? " – may fill soon" : ""}</small>` : ""}</td>`;
    }
    const posted = p._posted ? fmtDay(p._posted, p._posted.getFullYear() !== TODAY.getFullYear()) : "";
    const regs = [...new Set(members.flatMap((m) => regionsOf(m)))].filter((r) => r !== "US");
    const where = multi ? `${members.length} offices${regs.length ? " · " + regs.slice(0, 3).join(", ") + (regs.length > 3 ? "…" : "") : ""}` : fmtLoc(p.location);
    const meta = [where, p.level === "Graduate/MBA" ? "MBA / graduate" : ""].filter(Boolean).join(" · ");
    const isOpen = state.open.has(p.id);
    const apply = p._status === "closed" && !multi
      ? `<span class="status-closed">Closed ${p.closed_on ? fmtDay(parseDay(p.closed_on)) : ""}</span>`
      : multi ? `<button type="button" class="pick-office" aria-label="Choose an office for ${esc(p.company)}, ${esc(p.group_title || p.title)}">Pick office</button>`
      : `<a href="${esc(p.url)}" target="_blank" rel="noopener" aria-label="Apply: ${esc(p.company)}, ${esc(p.title)} (opens employer site)">Apply</a>`;
    return `<tr class="row ${p._status === "closed" ? "closed" : ""}" data-id="${esc(p.id)}" tabindex="0" aria-expanded="${isOpen}">
      <td class="c-company"><div class="firmcell">${logoHtml(p.company)}<div><span class="firm">${esc(p.company)}</span><span class="ftype">${esc(p.company_type)}</span></div></div></td>
      <td class="role">${esc(multi ? p.group_title || p.title : p.title)}${p._new ? '<span class="new">New</span>' : ""}${p.verified ? `<span class="verified" title="Details confirmed by hand on ${esc(p.verified)}">Verified</span>` : ""}${meta ? `<span class="role-meta" title="${esc(p.location)}">${esc(meta)}</span>` : ""}</td>
      <td class="c-season">${p.season ? `<span class="pill">${esc(p.season)}</span>` + (p.season_inferred ? '<span class="est" title="Year estimated from posting date">est.</span>' : "") : '<span class="est">Season not stated</span>'}</td>
      ${elig}${dl}
      <td class="posted">${posted}</td>
      <td class="apply"><div class="apply-box" data-id="${esc(p.id)}" data-kind="posting">${apply}<button type="button" class="star" data-s="saved" aria-pressed="false">Save</button></div></td>
    </tr>
    <tr class="detail" ${isOpen ? "" : "hidden"}><td colspan="7">${detailHtml(p, members)}</td></tr>`;
  }

  let FIRM_NOTES = {};
  function firmNoteHtml(name) {
    const n = FIRM_NOTES[name];
    if (!n) return "";
    return `<div class="firm-note"><h5>How ${esc(n.short || name)} recruits</h5>
      ${n.timeline ? `<p>${esc(n.timeline)}</p>` : ""}
      ${n.programs?.length ? `<p><b>Programs:</b> ${esc(n.programs.join(" · "))}</p>` : ""}
      ${n.tips ? `<p><b>Tip:</b> ${esc(n.tips)}</p>` : ""}
      ${n.links?.length ? `<p class="firm-links">${n.links.map((l) => `<a href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.label)}</a>`).join(" · ")}</p>` : ""}
    </div>`;
  }

  function reportUrl(p) {
    const repo = state.run?.repo && !state.run.repo.startsWith("local") ? state.run.repo : "gbv229/wm-internship-tracker";
    const body = [`**Posting:** ${p.company} – ${p.title}`, `**Link:** ${p.url}`, `**Posting id:** \`${p.id}\``,
      `**Shown as:** season ${p.season || "not stated"}; eligible ${(p.classes || []).join(", ") || "not stated"}; deadline ${p.deadline || "rolling"}; location ${p.location || "not stated"}`,
      "", "**What's wrong / correct info:**", "", "**Where you confirmed it (link or source):**", ""].join("\n");
    return `https://github.com/${repo}/issues/new?${new URLSearchParams({ title: `Fix: ${p.company} – ${p.title}`.slice(0, 120), body, labels: "data fix" })}`;
  }

  function officesHtml(members) {
    if (members.length < 2) return "";
    const fmtDl = (m) => (m._dl ? `due ${fmtFull(m._dl)}` : "rolling");
    return `<div class="offices"><h5>${members.length} offices – apply to the one you want</h5><ul>
      ${members.map((m) => `<li><span class="office-where">${esc(m.location || m.title)}</span>
        <span class="office-meta">${esc([fmtDl(m), (m.classes || []).length ? "Class of " + m.classes.join(", ") : ""].filter(Boolean).join(" · "))}</span>
        ${m._status === "closed" ? '<span class="status-closed">Closed</span>' : `<a class="office-apply" href="${esc(m.url)}" target="_blank" rel="noopener">Apply</a>`}</li>`).join("")}
    </ul></div>`;
  }

  function detailHtml(p, members = [p]) {
    const items = [
      ["Pay", p.pay], ["Minimum GPA", p.gpa], ["Length", p.weeks ? `${p.weeks} weeks` : null],
      ["Work setup", p.work_mode], ["Visa sponsorship", p.sponsorship], ["Area", p.function],
      ["Location", p.location], ["Region", regionsOf(p).filter((r) => r !== "US").join(", ") || null], ["First seen here", p._first ? fmtDay(p._first, true) : null],
    ].filter(([, v]) => v);
    const ev = [];
    const from = (v) => (/^Confirmed by hand/.test(v || "") ? "confirmed by hand" : "from the posting");
    if (p.note) ev.push(`<div class="evidence"><dt>Note${p.verified ? ` (verified ${esc(p.verified)})` : ""}</dt><dd><blockquote>${esc(p.note)}</blockquote></dd></div>`);
    if (p.class_evidence) ev.push(`<div class="evidence"><dt>Eligibility, ${from(p.class_evidence)}</dt><dd><blockquote>${esc(p.class_evidence)}</blockquote></dd></div>`);
    if (p.deadline_evidence) ev.push(`<div class="evidence"><dt>Deadline, ${from(p.deadline_evidence)}</dt><dd><blockquote>${esc(p.deadline_evidence)}</blockquote></dd></div>`);
    return `<div class="detail-wrap">
      <div class="detail-track">${trackerControls(p.id, "posting")}</div>
      ${officesHtml(members)}
      <dl class="detail-inner">${items.map(([k, v]) => `<div><dt>${k}</dt><dd>${esc(v)}</dd></div>`).join("")}${ev.join("")}
        ${!items.length && !ev.length ? `<div><dd>No extra details were listed. Open the posting for the full description.</dd></div>` : ""}</dl>
      ${firmNoteHtml(p.company)}
      <p class="detail-foot"><a href="${esc(reportUrl(p))}" target="_blank" rel="noopener">Report a problem with this role</a> · opens a prefilled GitHub issue</p>
    </div>`;
  }

  function renderClosing() {
    const soon = state.postings
      .filter((p) => inTrack(p) && p._dl && p._dl >= TODAY && p._status !== "closed" && p.level === "Undergraduate" && regionsOf(p).some((r) => US_REGIONS.includes(r)))
      .sort((a, b) => a._dl - b._dl)
      .filter((p, i, arr) => arr.findIndex((q) => (q.group || q.id) === (p.group || p.id)) === i)
      .slice(0, 5);
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
        <span class="c-firm">${logoHtml(p.company)}${esc(p.company)}</span>
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
    el.innerHTML = `<span class="dot" aria-hidden="true"></span>Updated ${ago}. Checks about every 30 minutes. ${r.sources_ok} of ${r.sources_total} careers sites reached on the last check.`;
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
      const realFeeds = feeds.filter((x) => x.kind !== "browser"), br = srcs.find((x) => x.kind === "browser" && x.ok);
      let mode = realFeeds.length ? `<span class="mode${errs.length ? " err" : ""}"><i></i>Live feed</span>`
        : br ? `<span class="mode${errs.length ? " err" : ""}"><i></i>Read via browser</span>`
        : `<span class="mode page${errs.length ? " err" : ""}"><i></i>Page watch</span>`;
      if (isBlocked && !errs.length) mode += `<span class="role-meta">Site blocks automated checks — open the link</span>`;
      if (errs.length) mode += `<span class="err-msg">Couldn't reach ${errs.map((e) => e.kind).join(", ")}: ${esc((errs[0].error || "").slice(0, 120))}</span>`;
      const changed = pages.map((s) => s.changed_on).filter(Boolean).sort().pop();
      const links = pages.flatMap((s) => s.links || []).slice(0, 4);
      return `<tr>
        <td><div class="firmcell">${logoHtml(f.name)}<a class="firm" href="${esc(f.careers)}" target="_blank" rel="noopener">${esc(f.name)}</a></div>
          ${FIRM_NOTES[f.name] ? `<details class="firm-details"><summary>How they recruit</summary>${firmNoteHtml(f.name)}</details>` : ""}
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
      ["Location", "location"], ["Region", (p) => regionsOf(p).join(" / ")], ["Pay", "pay"], ["GPA", "gpa"], ["Weeks", "weeks"], ["Sponsorship", "sponsorship"],
      ["Status", (p) => ({ open: "Open", soon: "Closing soon", past: "Deadline passed", closed: "Closed" })[p._status]], ["Link", "url"]];
    const cell = (v) => { const s = String(v ?? ""); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
    const csv = [cols.map((c) => c[0]).join(","), ...rows.map((p) => cols.map(([, k]) => cell(typeof k === "function" ? k(p) : p[k])).join(","))].join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    a.download = `wm-internships-${TODAY.toISOString().slice(0, 10)}.csv`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  // visitor counts: only when a GoatCounter code is set in index.html
  if (window.GOATCOUNTER_CODE) {
    const sc = document.createElement("script");
    sc.async = true; sc.src = "https://gc.zgo.at/count.js";
    sc.dataset.goatcounter = `https://${window.GOATCOUNTER_CODE}.goatcounter.com/count`;
    document.head.appendChild(sc);
  }
  document.addEventListener("click", (e) => {
    if (e.target.id === "alerts-how") { e.preventDefault(); $("#tab-about").click(); $("#alerts").scrollIntoView({ behavior: "smooth" }); }
  });

  setInterval(renderFreshness, 60000);
  load();
})();
