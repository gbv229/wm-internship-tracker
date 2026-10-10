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
    const img = d ? `<img src="https://icons.duckduckgo.com/ip3/${esc(d)}.ico" alt="" loading="lazy" onerror="this.remove()">` : "";
    return `<span class="logo" style="--logo-bg:hsl(${hue(name)} 38% 38%)" aria-hidden="true">${esc(initials(name))}${img}</span>`;
  }
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
    const repo = r?.repo && r.repo.includes("/") && !r.repo.startsWith("local") ? `https://github.com/${r.repo}` : null;
    ["repo-link", "repo-link-2"].forEach((id) => { const a = $("#" + id); if (repo) a.href = repo; else a.removeAttribute("href"); });
  }

  function applyTrack() {
    const t = TRACKS[state.track];
    document.documentElement.dataset.track = state.track;
    const tc = document.querySelector('meta[name="theme-color"]');
    if (tc) tc.content = state.track === "real_estate" ? "#172f5c" : "#0d3b30";
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
    $("#result-count").innerHTML = `<b>${list.length}</b> ${list.length === 1 ? "role" : "roles"}` +
      (state.cls !== "any" ? ` for ${esc(CLASS_NAMES[+state.cls]?.toLowerCase() || "class of " + state.cls)}` : "") +
      (state.region && state.region !== "US" ? ` in ${esc(REGION_LABEL[state.region] || state.region)}` : "");
    renderStats();
    renderMap();

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

  // ------------------------------------------------------- hero stats
  function renderStats() {
    const act = state.postings.filter((p) => inTrack(p) && (p._status === "open" || p._status === "soon") && p.level === "Undergraduate");
    const firms = new Set(act.map((p) => p.company)).size;
    const week = act.filter((p) => p._posted && (TODAY - p._posted) / DAY <= 7).length;
    const soph = act.filter((p) => (p.classes || []).includes(AY_END + 2)).length;
    const items = [
      [act.length, "open roles", "", true], [firms, "firms hiring", "", false],
      [week, "posted this week", "hot", false], [soph, `open to sophomores ’${String(AY_END + 2).slice(2)}`, "", false],
    ].filter(([n, , , always]) => always || n > 0);
    $("#stats").innerHTML = items.map(([n, l, c]) => `<li class="${c}"><b>${n}</b><span>${l}</span></li>`).join("");
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

  function rowHtml(p) {
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
    } else dl = `<td class="dl none">Rolling / not stated</td>`;
    const posted = p._posted ? fmtDay(p._posted, p._posted.getFullYear() !== TODAY.getFullYear()) : "";
    const meta = [fmtLoc(p.location), p.level === "Graduate/MBA" ? "MBA / graduate" : ""].filter(Boolean).join(" · ");
    const isOpen = state.open.has(p.id);
    const apply = p._status === "closed"
      ? `<span class="status-closed">Closed ${p.closed_on ? fmtDay(parseDay(p.closed_on)) : ""}</span>`
      : `<a href="${esc(p.url)}" target="_blank" rel="noopener" aria-label="Apply: ${esc(p.company)}, ${esc(p.title)} (opens employer site)">Apply</a>`;
    return `<tr class="row ${p._status === "closed" ? "closed" : ""}" data-id="${esc(p.id)}" tabindex="0" aria-expanded="${isOpen}">
      <td class="c-company"><div class="firmcell">${logoHtml(p.company)}<div><span class="firm">${esc(p.company)}</span><span class="ftype">${esc(p.company_type)}</span></div></div></td>
      <td class="role">${esc(p.title)}${p._new ? '<span class="new">New</span>' : ""}${meta ? `<span class="role-meta" title="${esc(p.location)}">${esc(meta)}</span>` : ""}</td>
      <td class="c-season">${p.season ? `<span class="pill">${esc(p.season)}</span>` + (p.season_inferred ? '<span class="est" title="Year estimated from posting date">est.</span>' : "") : '<span class="est">Season not stated</span>'}</td>
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
      ["Location", p.location], ["Region", regionsOf(p).filter((r) => r !== "US").join(", ") || null], ["First seen here", p._first ? fmtDay(p._first, true) : null],
    ].filter(([, v]) => v);
    const ev = [];
    if (p.class_evidence) ev.push(`<div class="evidence"><dt>Eligibility, from the posting</dt><dd><blockquote>${esc(p.class_evidence)}</blockquote></dd></div>`);
    if (p.deadline_evidence) ev.push(`<div class="evidence"><dt>Deadline, from the posting</dt><dd><blockquote>${esc(p.deadline_evidence)}</blockquote></dd></div>`);
    return `<dl class="detail-inner">${items.map(([k, v]) => `<div><dt>${k}</dt><dd>${esc(v)}</dd></div>`).join("")}${ev.join("")}
      ${!items.length && !ev.length ? `<div><dd>No extra details were listed. Open the posting for the full description.</dd></div>` : ""}</dl>`;
  }

  function renderClosing() {
    const soon = state.postings
      .filter((p) => inTrack(p) && p._dl && p._dl >= TODAY && p._status !== "closed" && p.level === "Undergraduate" && isUS(p))
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
        <td><div class="firmcell">${logoHtml(f.name)}<a class="firm" href="${esc(f.careers)}" target="_blank" rel="noopener">${esc(f.name)}</a></div>
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

  setInterval(renderFreshness, 60000);
  load();
})();
