/* Test renderu strony BEZ przegladarki (QA-loop): parsuje docs/*.html w jsdom,
   podstawia fetch czytajacy lokalne CSV i odpala prawdziwy app.js / skrypty stron.
   FAILuje CI gdy: pusta tabela, brak wykresu, zerwane linki spawn/item, brak danych.
   Uruchomienie lokalne: npm --prefix test install && node test/render.test.js
   W CI: .github/workflows/render.yml */
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.join(__dirname, "..", "docs");
let failures = [];
function ok(cond, msg) {
  console.log((cond ? "PASS " : "FAIL ") + msg);
  if (!cond) failures.push(msg);
}
function stubFetch(window) {
  window.fetch = async (u) => {
    const p = path.join(ROOT, String(u).split("?")[0]);
    try {
      const text = fs.readFileSync(p, "utf8");
      return { ok: true, text: async () => text, json: async () => JSON.parse(text) };
    } catch (e) {
      return { ok: false, status: 404, text: async () => { throw e; }, json: async () => { throw e; } };
    }
  };
}
function loadPage(file, url) {
  const html = fs.readFileSync(path.join(ROOT, file), "utf8");
  const dom = new JSDOM(html, { url: "https://x/" + (url || file), runScripts: "outside-only" });
  stubFetch(dom.window);
  for (const m of html.matchAll(/<script src="([^"]+)"><\/script>/g)) {
    try {
      dom.window.eval(fs.readFileSync(path.join(ROOT, m[1]), "utf8"));
    } catch (e) { ok(false, `${file}: blad JS w ${m[1]}: ${e.message}`); }
  }
  const inlines = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]).filter(s => s.trim());
  for (const code of inlines) {
    try { dom.window.eval(code); } catch (e) { ok(false, `${file}: blad inline JS: ${e.message}`); }
  }
  return dom;
}
const wait = (ms) => new Promise(r => setTimeout(r, ms));

(async () => {
  // --- index: rankingi EXP ---
  const idx = loadPage("index.html");
  await wait(1200);
  const rows = idx.window.document.querySelectorAll("#tbl tbody tr");
  ok(rows.length > 3, `index EXP: wierszy=${rows.length} (oczekiwano >3)`);
  const chart = idx.window.document.querySelectorAll("#chart .bar-row");
  ok(chart.length > 0, `index EXP: wykres slupkow=${chart.length}`);
  const links = [...idx.window.document.querySelectorAll("#tbl tbody a")].map(a => a.getAttribute("href"));
  ok(links.some(h => h && h.startsWith("spawn.html?spawn=")), "index EXP: linki do spawn.html");
  ok(links.some(h => h && h.startsWith("https://www.hunt-analyser.com/")), "index EXP: linki do sesji zrodlowych");

  // --- widok profit (konsensus) ---
  idx.window.document.getElementById("tProfit").click();
  await wait(1200);
  const prows = idx.window.document.querySelectorAll("#tblP tbody tr");
  const ptxt = idx.window.document.querySelector("#tblP tbody").textContent;
  ok(prows.length > 1 && /źr/.test(ptxt), `index PROFIT: wierszy=${prows.length} z kolumna zgodnosci`);
  await wait(800);
  const est = idx.window.document.getElementById("estwrap").textContent;
  ok(/Szacunki|%/.test(est) || prows.length >= 3, "index PROFIT: fallback szacunkow lub >=3 wiersze");

  // --- spawn.html dla top spawna z POLICZONEGO profitu ---
  const sprows = fs.readFileSync(path.join(ROOT, "data", "spawn_profit.csv"), "utf8")
    .split("\n").slice(1).filter(Boolean);
  const testSpawn = (sprows[0].match(/^"?(.*?)"?,/) || [])[1] || "";
  const sp = loadPage("spawn.html", "spawn.html?spawn=" + encodeURIComponent(testSpawn));
  await wait(1200);
  const kpi = sp.window.document.getElementById("kpi").textContent;
  ok(/sesji/.test(kpi), `spawn '${testSpawn}': KPI renderuje (${kpi.trim().slice(0, 60)})`);
  ok(sp.window.document.querySelectorAll("#tblLoot tbody tr").length > 0, "spawn: jedna tabela loota (tblLoot)");

  // --- item.html: rope belt ---
  const it = loadPage("item.html", "item.html?id=11492&name=rope%20belt");
  await wait(1200);
  ok(/rope belt/i.test(it.window.document.getElementById("title").textContent), "item: tytul rope belt");
  ok(it.window.document.querySelectorAll("#sells .bar-row").length > 5, "item: drabinka sell");
  ok(it.window.document.querySelectorAll("#buys .bar-row").length > 0, "item: drabinka buy");

  // --- demand.html ---
  const dm = loadPage("demand.html");
  await wait(1200);
  ok(dm.window.document.querySelectorAll("#tbl tbody tr").length > 20, "demand: tagi popytu");

  // --- log.html usuniety? (funkcjonalnosc skasowana na zyczenie) ---
  ok(!fs.existsSync(path.join(ROOT, "log.html")), "log.html nie istnieje (usuniete)");

  console.log(failures.length ? `\nWYNIK: ${failures.length} FAIL` : "\nWYNIK: WSZYSTKO OK");
  process.exit(failures.length ? 1 : 0);
})().catch(e => { console.error("FATAL", e); process.exit(1); });
