/* Dashboard: czyta CSV z data/ (kopiowane przez build_gold.py). Bez zaleznosci. */
const $ = id => document.getElementById(id);
const state = { bracket: "100_200", mode: "exp", party: "all", q: "", rows: [] };

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

async function load() {
  try {
    const info = await (await fetch("data/build_info.json")).json();
    $("meta").textContent = `zrzut ${info.date} • huntów: ${info.hunts} • świeżość ≤${info.recent_days}d`;
  } catch { $("meta").textContent = "brak build_info.json — odpal build_gold.py"; }
  const file = state.mode === "exp" ? `ranking_exp_${state.bracket}` : `ranking_profit_${state.bracket}`;
  try {
    const txt = await (await fetch(`data/${file}.csv`)).text();
    state.rows = parseCSV(txt);
  } catch { state.rows = []; }
  render();
}

function filtered() {
  return state.rows.filter(r => {
    if (state.party !== "all" && String(r.party_size) !== state.party &&
        !(state.party === "2" && Number(r.party_size) >= 2)) return false;
    if (state.q && !(r.spawn || "").toLowerCase().includes(state.q)) return false;
    return true;
  });
}

function render() {
  const key = state.mode === "exp" ? "xp_h" : "balance_h";
  const rows = filtered().sort((a, b) => Number(b[key]) - Number(a[key]));
  const tb = document.querySelector("#tbl tbody");
  tb.innerHTML = rows.map((r, i) => `<tr>
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

$("bracket").onchange = e => { state.bracket = e.target.value; load(); };
$("party").onchange = e => { state.party = e.target.value; render(); };
$("q").oninput = e => { state.q = e.target.value.toLowerCase(); render(); };
$("mExp").onclick = () => { state.mode = "exp"; $("mExp").classList.add("on"); $("mProfit").classList.remove("on"); load(); };
$("mProfit").onclick = () => { state.mode = "profit"; $("mProfit").classList.add("on"); $("mExp").classList.remove("on"); load(); };
load();
