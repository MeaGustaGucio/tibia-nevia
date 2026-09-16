/* Dashboard: Rankingi + Spawny (mediana) + Poradnik. Bez zaleznosci. */
const $ = id => document.getElementById(id);
const state = { bracket: "100_200", mode: "exp", party: "all", q: "", rows: [], spawns: [], spawnSort: "exp" };

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

const fmt = n => (Number(n) || 0).toLocaleString("pl-PL");
async function getCSV(path) {
  try { return parseCSV(await (await fetch(path)).text()); } catch { return []; }
}

/* ---------- Rankingi huntów ---------- */
async function loadRank() {
  try {
    const info = await (await fetch("data/build_info.json")).json();
    $("meta").textContent = `zrzut ${info.date} • profit-huntów (≤${info.recent_days}d): ${info.hunts} • exp-huntów (≤${info.recent_days_exp || info.recent_days}d): ${info.hunts_exp ?? info.hunts}`;
  } catch { $("meta").textContent = "brak build_info.json — odpal build_gold.py"; }
  const file = state.mode === "exp" ? `ranking_exp_${state.bracket}` : `ranking_profit_${state.bracket}`;
  state.rows = await getCSV(`data/${file}.csv`);
  renderRank();
}

function filtered() {
  return state.rows.filter(r => {
    if (state.party !== "all" && String(r.party_size) !== state.party &&
        !(state.party === "2" && Number(r.party_size) >= 2)) return false;
    if (state.q && !(r.spawn || "").toLowerCase().includes(state.q)) return false;
    return true;
  });
}

function renderRank() {
  const key = state.mode === "exp" ? "xp_h" : "balance_h";
  const rows = filtered().sort((a, b) => Number(b[key]) - Number(a[key]));
  document.querySelector("#tbl tbody").innerHTML = rows.map((r, i) => `<tr>
    <td>${i + 1}</td><td>${r.spawn || "—"}</td><td>${r.party_comp || ""}</td>
    <td class="num">${fmt(r.xp_h)}</td>
    <td class="num ${Number(r.balance_h) < 0 ? "neg" : "pos"}">${fmt(r.balance_h)}</td>
    <td>${r.hunt_date || ""}</td><td><a href="${r.url}" target="_blank" rel="noopener">hunt</a></td>
  </tr>`).join("") || `<tr><td colspan="7">Brak danych dla tych filtrów.</td></tr>`;
  const max = Math.max(1, ...rows.slice(0, 15).map(r => Number(r[key])));
  $("chartTitle").textContent = `Top 15 — ${state.mode === "exp" ? "EXP/h" : "Profit/h"} (${state.bracket.replace("_", "–")})`;
  $("chart").innerHTML = rows.slice(0, 15).map(r => {
    const v = Number(r[key]), pct = Math.max(1, Math.round(v / max * 100));
    return `<div class="bar-row"><span>${r.spawn || "—"}</span>
      <div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>
      <span style="text-align:right">${fmt(v)}</span></div>`;
  }).join("") || "Brak danych.";
}

/* ---------- Spawny (mediana) ---------- */
async function loadSpawns() {
  const b = $("bracket2").value;
  state.spawns = await getCSV(`data/spawn_stats${b ? "_" + b : ""}.csv`);
  renderSpawns();
}
function renderSpawns() {
  const key = state.spawnSort === "exp" ? "median_xp_h" : "median_profit_h";
  const rows = [...state.spawns].sort((a, b) => Number(b[key]) - Number(a[key]));
  document.querySelector("#tbl2 tbody").innerHTML = rows.map((r, i) => `<tr>
    <td>${i + 1}</td><td>${r.spawn}</td><td class="num">${r.n_hunts}</td>
    <td class="num">${fmt(r.median_xp_h)}</td><td class="num">${fmt(r.max_xp_h)}</td>
    <td class="num ${Number(r.median_profit_h) < 0 ? "neg" : "pos"}">${fmt(r.median_profit_h)}</td>
    <td class="num ${Number(r.max_profit_h) < 0 ? "neg" : "pos"}">${fmt(r.max_profit_h)}</td>
    <td class="num">${r.min_lvl_seen || "?"}–${r.max_lvl_seen || "?"}</td>
    <td><a href="${r.sample_url}" target="_blank" rel="noopener">hunt</a></td>
  </tr>`).join("") || `<tr><td colspan="9">Brak danych.</td></tr>`;
}

/* ---------- KPI do poradnika ---------- */
async function loadKpi() {
  const s = await getCSV("data/spawn_stats_100_200.csv");
  const byExp = [...s].sort((a, b) => Number(b.median_xp_h) - Number(a.median_xp_h))[0];
  const byPf = [...s].sort((a, b) => Number(b.median_profit_h) - Number(a.median_profit_h))[0];
  $("kpi").innerHTML =
    (byExp ? `<div><b>${byExp.spawn}</b>top mediana EXP/h (100–200): ${fmt(byExp.median_xp_h)} (n=${byExp.n_hunts})</div>` : "") +
    (byPf ? `<div><b>${byPf.spawn}</b>top mediana profit/h (100–200): ${fmt(byPf.median_profit_h)} (n=${byPf.n_hunts})</div>` : "") +
    `<div><b>ED 114 + EK 114</b>share OK (≥⅔) • bonus duo +30%</div>`;
}

/* ---------- Zakładki + kontrolki ---------- */
function tab(name) {
  for (const t of ["Rank", "Spawn", "Guide"]) {
    $("t" + t).classList.toggle("on", t === name);
    $("v" + t).classList.toggle("on", t === name);
  }
  if (name === "Spawn" && !state.spawns.length) loadSpawns();
  if (name === "Guide") loadKpi();
}
$("tRank").onclick = () => tab("Rank");
$("tSpawn").onclick = () => tab("Spawn");
$("tGuide").onclick = () => tab("Guide");
$("bracket").onchange = e => { state.bracket = e.target.value; loadRank(); };
$("party").onchange = e => { state.party = e.target.value; renderRank(); };
$("q").oninput = e => { state.q = e.target.value.toLowerCase(); renderRank(); };
$("mExp").onclick = () => { state.mode = "exp"; $("mExp").classList.add("on"); $("mProfit").classList.remove("on"); loadRank(); };
$("mProfit").onclick = () => { state.mode = "profit"; $("mProfit").classList.add("on"); $("mExp").classList.remove("on"); loadRank(); };
$("bracket2").onchange = () => loadSpawns();
$("sExp").onclick = () => { state.spawnSort = "exp"; $("sExp").classList.add("on"); $("sProfit").classList.remove("on"); renderSpawns(); };
$("sProfit").onclick = () => { state.spawnSort = "profit"; $("sProfit").classList.add("on"); $("sExp").classList.remove("on"); renderSpawns(); };
loadRank();
