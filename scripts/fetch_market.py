"""Bronze: api.tibiamarket.top (Nevia) -> data/raw/<date>/market_*.json. Stdlib only.

Zapisuje: world_data, market_values (paginacja skip/limit), item_history dla TOP-N
najbardziej handlowanych itemów + item_metadata. To pokrywa wymóg "historia z tego miesiąca".
"""
import argparse
import datetime as dt
import glob
import json
import pathlib
import urllib.parse
import urllib.request

from common import ROOT, load_config

cfg = load_config()
API = "https://api.tibiamarket.top"
SERVER = cfg.get("world", "Nevia")
OUT = ROOT / "data" / "raw" / dt.date.today().isoformat()
OUT.mkdir(parents=True, exist_ok=True)
import os
MKT = cfg.get("market", {})
TOP_N_HISTORY = int(os.environ.get("TOP_N_HISTORY", MKT.get("top_n_history", 150)))
HISTORY_DAYS = int(os.environ.get("HISTORY_DAYS", MKT.get("history_days", 90)))
DAILY_HIST_MAX = int(os.environ.get("DAILY_HIST_MAX", MKT.get("daily_hist_max", 40)))
PAGE_LIMIT = 200  # mniejsze strony = mniej 429
REQ_DELAY = 0.6  # odstep miedzy requestami (API ma rate limit)


def get(path: str, params: dict, retries: int = 6) -> object:
    url = f"{API}{path}?{urllib.parse.urlencode(params)}"
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "nevia-pipeline/0.1"})
            with urllib.request.urlopen(req, timeout=60) as r:
                time.sleep(REQ_DELAY)
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries - 1:
                wait = 5 * (attempt + 1)
                print(f"429, czekam {wait}s (proba {attempt + 1}/{retries}): {path}")
                time.sleep(wait)
                continue
            raise


world = get("/world_data", {})
(OUT / "market_world_data.json").write_text(json.dumps(world), encoding="utf-8")

vals_path = OUT / "market_values_nevia.json"
if vals_path.exists() and vals_path.stat().st_size > 100000:
    all_rows = json.loads(vals_path.read_text(encoding="utf-8"))
    print(f"market_values: reuse z dysku ({len(all_rows)} rows)")
else:
    all_rows: list = []
    skip = 0
    while True:
        page = get("/market_values", {"server": SERVER, "skip": skip, "limit": PAGE_LIMIT})
        if not page:
            break
        all_rows.extend(page)
        print(f"market_values skip={skip} rows={len(page)} total={len(all_rows)}")
        if len(page) < PAGE_LIMIT:
            break
        skip += PAGE_LIMIT
    vals_path.write_text(json.dumps(all_rows), encoding="utf-8")

# TOP-N po miesiecznym wolumenie -> historia.
# Seed z poprzednich dni + dziennie tylko DAILY_HIST_MAX top (reszte dobiera sobota).
import glob as _glob
hist_path = OUT / "market_history_top.json"
hist = json.loads(hist_path.read_text(encoding="utf-8")) if hist_path.exists() else {}
if not hist:
    prev = sorted(_glob.glob(str(ROOT / "data" / "raw" / "*" / "market_history_top.json")))
    prev = [p for p in prev if pathlib.Path(p).parent != OUT]
    if prev:
        try:
            hist = json.loads(pathlib.Path(prev[-1]).read_text(encoding="utf-8"))
            print(f"history seed z {prev[-1]}: {len(hist)} items")
        except Exception:
            hist = {}
ranked = sorted(all_rows, key=lambda r: (r.get("month_sold", 0) or 0) + (r.get("month_bought", 0) or 0), reverse=True)
top_ids = [r["id"] for r in ranked[:TOP_N_HISTORY] if r.get("id")]
daily_ids = set(top_ids[:DAILY_HIST_MAX])
todo = [i for i in top_ids if str(i) not in hist or i in daily_ids]
print(f"history: done={len(hist)} todo={len(todo)} (dzienny refresh top-{DAILY_HIST_MAX})")
for i, item_id in enumerate(todo):
    try:
        hist[str(item_id)] = get("/item_history", {"server": SERVER, "item_id": item_id, "days": HISTORY_DAYS})
    except Exception as e:  # jeden item nie moze wywalic calego batcha
        print(f"history failed id={item_id}: {e}")
    if (i + 1) % 10 == 0:
        hist_path.write_text(json.dumps(hist), encoding="utf-8")
        print(f"history {i + 1}/{len(todo)} (flush)")
hist_path.write_text(json.dumps(hist), encoding="utf-8")

# metadata: JEDEN call bez item_id zwraca WSZYSTKIE itemy (id->nazwa/NPC/Wiki).
# (Dokumentacja API: "or all items if no item id is given".)
meta_path = OUT / "market_metadata_all.json"
try:
    meta_all = get("/item_metadata", {})
    meta_path.write_text(json.dumps(meta_all), encoding="utf-8")
    print(f"metadata ALL: {len(meta_all)} items (1 call)")
except Exception as e:
    print(f"metadata ALL failed: {e}")
print(f"DONE market Nevia: values={len(all_rows)} history_items={len(hist)}")
