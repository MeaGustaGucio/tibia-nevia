/* Nevia — 2 pytania: gdzie expić? gdzie profitować? Bez zależności. */
const $ = id => document.getElementById(id);
const state = { bracket: "100_200", bracketP: "100_200", party: "all", q: "", qP: "", rows: [], rowsP: [] };

function parseCSV(text) {
  const rows = []; let cur = [""], q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) {
      if (c === '"') { if (text[i + 1] === '"') { cur[cur.length - 1] += '"'; i++; } else q = false; }
      else cur[cur.length - 1] += c;
    } else if (c === '"') q = true;
    else if (c === ",") cur.push("");
    else if (c === "\n" || c === "\r") {
      if (cur.length > 1 || cur[0] !== "") rows.push(cur);
      cur = [""];
      if (c === "\r" && text[i + 1] === "\n") i++;
    } else cur[cur.length - 1] += c;
  }
  if (cur.length > 1 || cur[0] !== "") rows.push(cur);
  const head = rows.shift() || [];
  return rows.map(r => Object.fromEntries(head.map((h, j) => [h, r[j] ?? ""])));
}

/* Krótki format: 1 850 000 -> 1,9M • 833 152 -> 833 tys. */
function fmtK(n) {
  const v = Number(n);
  if (!isFinite(v) || n === "" || n === undefined || n === null) return "—";
  const sign = v < 0 ? "−" : "";
  const a = Math.abs(v);
  const pl = (x, d) => x.toLocaleString("pl-PL", { maximumFractionDigits: d });
  if (a >= 1000000) return sign + pl(a / 1000000, 1) + "M";
  if (a >= 10000) return sign + Math.round(a / 1000) + " tys.";
  if (a >= 1000) return sign + pl(a / 1000, 1) + " tys.";
  return sign + pl(a, 0);
}
const fmt = n => { const v = Number(n); return (!isFinite(v) || n === "" || n === undefined) ? "—" : v.toLocaleString("pl-PL"); };

async function getCSV(path) {
  try { return parseCSV(await (await fetch(path)).text()); } catch { return []; }
}

async function loadMeta() {
  try {
    const info = await (await fetch("data/build_info.json")).json();
    $("meta").textContent = `dane z ${info.date} • sesji ≤31 dni: ${info.sessions_le31d ?? "?"} • ≤62 dni: ${info.sessions_le62d ?? "?"} • eventy 2× wykluczone: ${info.events_excluded ?? 0}`;
  } catch { $("meta").textContent = "brak danych — pipeline w drodze"; }
}

/* ---------- WIDOK 1: gdzie expić? ---------- */
async function loadExp() {
  state.rows = await getCSV(`data/ranking_exp_${state.bracket}.csv`);
  renderExp();
}
function renderExp() {
  const rows = state.rows.filter(r => {
    if (state.party !== "all" && String(r.party_size) !== state.party &&
        !(state.party === "2" && Number(r.party_size) >= 2)) return false;
    if (state.q && !(r.spawn || "").toLowerCase().includes(state.q)) return false;
    return true;
  }).sort((a, b) => Number(b.xp_h) - Number(a.xp_h));
  document.querySelector("#tbl thead tr").innerHTML =
    `<th>#</th><th>Gdzie expić? (top sesje)</th><th class="num">EXP/h</th><th>Kto expił</th><th>Link</th>`;
  document.querySelector("#tbl tbody").innerHTML = rows.map((r, i) => `<tr>
    <td>${i + 1}</td><td><a href="spawn.html?spawn=${encodeURIComponent(r.spawn || "")}">${r.spawn || "—"}</a></td>
    <td class="num"><b>${fmtK(r.xp_h)}</b></td>
    <td>${r.party_comp || ""}${r.min_lvl && r.max_lvl ? ` (lvl ${r.min_lvl}–${r.max_lvl})` : ""}${r.duration ? ` • ${r.duration}` : ""}</td>
    <td><a href="${r.url}" target="_blank" rel="noopener">sesja</a></td>
  </tr>`).join("") || `<tr><td colspan="5">Brak sesji dla tych filtrów — poszerz bracket albo wyczyść szukajkę.</td></tr>`;
  const max = Math.max(1, ...rows.slice(0, 10).map(r => Number(r.xp_h)));
  $("chartTitle").textContent = `Top 10 EXP/h (${state.bracket.replace("_", "–")})`;
  $("chart").innerHTML = rows.slice(0, 10).map(r => {
    const v = Number(r.xp_h), pct = Math.max(1, Math.round(v / max * 100));
    return `<div class="bar-row"><span>${r.spawn || "—"}</span>
      <div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>
      <span style="text-align:right">${fmtK(v)}</span></div>`;
  }).join("") || "Brak danych.";
}

/* ---------- WIDOK 2: gdzie profitować? ---------- */
async function loadProfit() {
  state.rowsP = await getCSV(`data/profit_consensus_${state.bracketP}.csv`);
  renderProfit();
}
function renderProfit() {
  const rows = state.rowsP.filter(r => {
    if (state.qP && !((r.spawn || "") + " " + (r.members || "")).toLowerCase().includes(state.qP)) return false;
    return true;
  }).sort((a, b) => Number(b.consensus_h) - Number(a.consensus_h));
  document.querySelector("#tblP thead tr").innerHTML =
    `<th>#</th><th>Gdzie profitować?</th><th class="num">Profit/h</th><th class="num">Zgodność źródeł</th>`;
  document.querySelector("#tblP tbody").innerHTML = rows.map((r, i) => {
    const spread = Math.round(Number(r.spread_pct || 0) * 100);
    const conf = spread <= 50 ? "wysoka" : spread <= 120 ? "średnia" : "niska";
    return `<tr>
    <td>${i + 1}</td><td><a href="spawn.html?spawn=${encodeURIComponent(r.spawn || "")}">${r.spawn || "—"}</a></td>
    <td class="num"><b>${fmtK(r.consensus_h)}</b></td>
    <td class="num" title="rozrzut ±${spread}%, źródeł: ${r.n_sources}">${r.n_sources} źr. • ${conf}</td>
  </tr>`; }).join("") || `<tr><td colspan="4">Brak danych — spróbuj inny przedział lub wyczyść szukajkę.</td></tr>`;
  const max = Math.max(1, ...rows.slice(0, 10).map(r => Number(r.consensus_h)));
  $("chartTitleP").textContent = `Top 10 profit/h (${state.bracketP.replace("_", "–")})`;
  $("chartP").innerHTML = rows.slice(0, 10).map(r => {
    const v = Number(r.consensus_h), pct = Math.max(1, Math.round(v / max * 100));
    return `<div class="bar-row"><span>${r.spawn || "—"}</span>
      <div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>
      <span style="text-align:right">${fmtK(v)}</span></div>`;
  }).join("") || "Brak danych.";
  const ew = $("estwrapP");
  if (rows.length < 3) {
    getCSV("data/control_estimates.csv").then(est => {
      const tag = state.bracketP.replace("_", "-");
      const rel = est.filter(r => (r.bracket || "").replace("_", "-") === tag);
      if (!rel.length) { ew.innerHTML = ""; return; }
      const f2 = n => n === "" || n === undefined ? "—" : fmtK(n);
      ew.innerHTML = `<h3 style="margin:12px 0 6px;font-size:.95rem">Za mało sesji? Szacunki z poradników (nie sesje!)</h3>
      <table style="width:100%;border-collapse:collapse;font-size:.78rem"><thead><tr><th>Spawn</th><th class="num">EXP/h</th><th class="num">Profit/h</th><th>Źródło</th></tr></thead><tbody>` +
      rel.map(r => `<tr><td>${r.spawn}</td><td class="num">${f2(r.exp_lo)}${r.exp_hi && r.exp_hi !== r.exp_lo ? "–" + f2(r.exp_hi) : ""}</td><td class="num">${f2(r.profit_lo)}${r.profit_hi && r.profit_hi !== r.profit_lo ? "–" + f2(r.profit_hi) : ""}</td><td>${r.source} (${r.source_date})</td></tr>`).join("") +
      `</tbody></table><p class="sub">Liczby z poradników, nie z sesji — punkt startu, nie fakt.</p>`;
    }).catch(() => { ew.innerHTML = ""; });
  } else ew.innerHTML = "";
}

/* ---------- KPI do poradnika ---------- */
async function loadKpi() {
  const s = await getCSV("data/spawn_stats_100_200.csv");
  const byExp = [...s].sort((a, b) => Number(b.median_xp_h) - Number(a.median_xp_h))[0];
  const byPf = [...s].sort((a, b) => Number(b.median_profit_h) - Number(a.median_profit_h))[0];
  $("kpi").innerHTML =
    (byExp ? `<div><b>${byExp.spawn}</b>top EXP/h (100–200): ${fmtK(byExp.median_xp_h)} (n=${byExp.n_hunts})</div>` : "") +
    (byPf ? `<div><b>${byPf.spawn}</b>top loot/h (100–200): ${fmtK(byPf.median_profit_h)} (n=${byPf.n_hunts})</div>` : "") +
    `<div><b>ED 114 + EK 114</b>share OK (≥⅔) • bonus duo +35%</div>`;
}

/* ---------- Zakładki + kontrolki ---------- */
function tab(name) {
  for (const t of ["Exp", "Profit", "Guide"]) {
    $("t" + t).classList.toggle("on", t === name);
    $("v" + t).classList.toggle("on", t === name);
  }
  if (name === "Exp") loadExp();
  if (name === "Profit") loadProfit();
  if (name === "Guide") loadKpi();
}
$("tExp").onclick = () => tab("Exp");
$("tProfit").onclick = () => tab("Profit");
$("tGuide").onclick = () => tab("Guide");
$("bracket").onchange = e => { state.bracket = e.target.value; loadExp(); };
$("bracketP").onchange = e => { state.bracketP = e.target.value; loadProfit(); };
$("party").onchange = e => { state.party = e.target.value; renderExp(); };
$("q").oninput = e => { state.q = e.target.value.toLowerCase(); renderExp(); };
$("qP").oninput = e => { state.qP = e.target.value.toLowerCase(); renderProfit(); };
document.querySelectorAll("#presets button").forEach(b => b.onclick = () => {
  $("q").value = b.dataset.q; state.q = b.dataset.q; renderExp();
});
loadMeta();
loadExp();

/* ---------- Kalkulator duo (guide) ---------- */
function duoCalc() {
  if (!$("duoA")) return;
  const a = Number($("duoA").value) || 0, b = Number($("duoB").value) || 0, v = $("duoV").value;
  const lo = Math.min(a, b), hi = Math.max(a, b);
  const ok = hi > 0 && lo >= (2 / 3) * hi;
  const bonus = { 1: 20, 2: 35, 3: 70, 4: 100 }[v] ?? 35;
  const perHead = hi > 0 ? Math.round(1000 * (1 + bonus / 100) / 2).toLocaleString("pl-PL") : "—";
  $("duoOut").innerHTML = ok
    ? `✅ Share działa (niższy ${lo} ≥ ⅔ z ${hi}). Bonus ${bonus}% → z potwora 1000 bazowo każdy dostaje <b>${perHead}</b> (× stamina/prey osobno).`
    : `❌ Share NIE działa: niższy ${lo} &lt; ⅔ z ${hi} (min. ${Math.ceil((2 / 3) * hi)}). Zrównajcie levele.`;
}
if ($("duoA")) { ["duoA", "duoB", "duoV"].forEach(id => $(id).oninput = duoCalc); duoCalc(); }
