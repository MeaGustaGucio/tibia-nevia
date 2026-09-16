"""Bronze: api.tibiamarket.top (Nevia) -> data/raw/<date>/market_*.json. Stdlib only.

Zapisuje: world_data, market_values (paginacja skip/limit), item_history dla TOP-N
najbardziej handlowanych itemów + item_metadata. To pokrywa wymóg "historia z tego miesiąca".
"""
import datetime as dt
import json
import pathlib
import urllib.parse
import urllib.request

API = "https://api.tibiamarket.top"
SERVER = "Nevia"
OUT = pathlib.Path(__file__).resolve().parents[1] / "data" / "raw" / dt.date.today().isoformat()
OUT.mkdir(parents=True, exist_ok=True)
import os
TOP_N_HISTORY = int(os.environ.get("TOP_N_HISTORY", "60"))  # podwyzsz np. do 300 gdy chcesz historie dla wiekszosci loota
PAGE_LIMIT = 500


def get(path: str, params: dict) -> object:
    url = f"{API}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "nevia-pipeline/0.1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


world = get("/world_data", {})
(OUT / "market_world_data.json").write_text(json.dumps(world, indent=1), encoding="utf-8")

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
(OUT / "market_values_nevia.json").write_text(json.dumps(all_rows, indent=1), encoding="utf-8")

# TOP-N po miesiecznym wolumenie -> historia 30d (to sa kandydaci do re-wyceny loota)
ranked = sorted(all_rows, key=lambda r: (r.get("month_sold", 0) or 0) + (r.get("month_bought", 0) or 0), reverse=True)
top_ids = [r["id"] for r in ranked[:TOP_N_HISTORY] if r.get("id")]
hist = {}
for i, item_id in enumerate(top_ids):
    try:
        hist[str(item_id)] = get("/item_history", {"server": SERVER, "item_id": item_id, "days": 30})
    except Exception as e:  # jeden item nie moze wywalic calego batcha
        print(f"history failed id={item_id}: {e}")
    if i % 10 == 0:
        print(f"history {i + 1}/{len(top_ids)}")
(OUT / "market_history_top.json").write_text(json.dumps(hist, indent=1), encoding="utf-8")

# metadata hurtowo (mapowanie id -> nazwa/kategoria/NPC) — pojedynczo, bo API nie ma batcha
meta = {}
for i in range(0, len(top_ids), 1):
    item_id = top_ids[i]
    try:
        meta[str(item_id)] = get("/item_metadata", {"item_id": item_id})
    except Exception as e:
        print(f"metadata failed id={item_id}: {e}")
(OUT / "market_metadata_top.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
print(f"DONE market Nevia: values={len(all_rows)} history_items={len(hist)}")
