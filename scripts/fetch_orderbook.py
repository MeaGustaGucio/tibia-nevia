"""Drabinka ofert (market_board): pelny rozklad cen + sztuki per item na Nevii.

Items = watchlist z configu + unia loot_list potworow z hunt_kills (cap max_items).
Wyjscie: data/raw/<dzis>/orderbook_nevia.json: {item_id: {sellers, buyers, update_time}}.
Resume: istniejacy plik z danego dnia jest doczytywany. Pacing 0.6s + retry na 429.
Stdlib + pyyaml (config).
"""
import argparse
import datetime as dt
import glob
import json
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request

from common import ROOT, load_config

cfg = load_config()
OUT = ROOT / "data" / "raw" / dt.date.today().isoformat()
OUT.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "nevia-pipeline/0.1"}
API = "https://api.tibiamarket.top"
SERVER = cfg.get("world", "Nevia")
OB = cfg.get("orderbook", {})
WATCH = [w.lower() for w in OB.get("watchlist", [])]
MAX_ITEMS = int(OB.get("max_items", 300))
DAILY_MAX = int(OB.get("daily_max", 40))  # dziennie tylko tyle (watchlista + top volume)


def get(path: str, params: dict, retries: int = 6):
    url = f"{API}{path}?{urllib.parse.urlencode(params)}"
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                time.sleep(2.0)  # wolniej = mniej 429 = szybciej globalnie
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429 and a < retries - 1:
                wait = 5 * (a + 1)
                print(f"429, czekam {wait}s: {path} {params.get('item_id')}")
                time.sleep(wait)
                continue
            raise


def load_metadata() -> list[dict]:
    files = sorted(glob.glob(str(ROOT / "data" / "raw" / "*" / "market_metadata_all.json")))
    if not files:
        return []
    return json.loads(pathlib.Path(files[-1]).read_text(encoding="utf-8"))


def loot_items() -> set[str]:
    """Unia loot_list potworow widzianych w hunt_kills (najnowsze creatures.json)."""
    files = sorted(glob.glob(str(ROOT / "data" / "raw" / "*" / "creatures.json")))
    if not files:
        return set()
    creatures = json.loads(pathlib.Path(files[-1]).read_text(encoding="utf-8"))
    out: set[str] = set()
    for c in creatures.values():
        for item in c.get("loot_list") or []:
            out.add(item.lower())
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="pelny refresh wszystkich targetow (job tygodniowy)")
    a = ap.parse_args()
    meta = load_metadata()
    if not meta:
        print("BRAK metadata (uruchom najpierw fetch_market.py) — koniec")
        return
    name_to_id = {str(m.get("name", "")).lower(): m["id"] for m in meta if m.get("id")}

    def resolve(name: str):
        # loot_list z TibiaData bywa w liczbie mnogiej ("gold coins" vs "gold coin")
        if name in name_to_id:
            return name_to_id[name]
        if name.endswith("s") and name[:-1] in name_to_id:
            return name_to_id[name[:-1]]
        return None

    wanted: list[int] = []
    for w in WATCH:
        iid = resolve(w)
        if iid:
            wanted.append(iid)
        else:
            print(f"watchlist: nie znaleziono itemu '{w}'")
    for item in sorted(loot_items()):
        if len(wanted) >= MAX_ITEMS:
            break
        iid = resolve(item)
        if iid and iid not in wanted:
            wanted.append(iid)
    print(f"orderbook target items: {len(wanted)} (watch={len(WATCH)}, cap={MAX_ITEMS})")

    path = OUT / "orderbook_nevia.json"
    snap = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not snap:
        # Seed z poprzednich dni (ciaglosc) — dzisiejszy run tylko odswieza.
        prev = sorted(glob.glob(str(ROOT / "data" / "raw" / "*" / "orderbook_nevia.json")))
        prev = [p for p in prev if pathlib.Path(p).parent != OUT]
        if prev:
            snap = json.loads(pathlib.Path(prev[-1]).read_text(encoding="utf-8"))
            print(f"seed z {prev[-1]}: {len(snap)} items")
    if not a.full:
        # Dziennie: watchlista + top po wolumenie (szybko, bez throttlingu).
        # Pelny refresh robi job tygodniowy (--full).
        vols = {}
        for p in sorted(glob.glob(str(ROOT / "data" / "raw" / "*" / "market_values_nevia.json")))[-2:]:
            try:
                for row in json.loads(pathlib.Path(p).read_text(encoding="utf-8")):
                    v = (row.get("month_sold", 0) or 0) + (row.get("month_bought", 0) or 0)
                    vols[str(row.get("id"))] = max(vols.get(str(row.get("id")), 0), v)
            except Exception:
                pass
        watch_ids = wanted[:len(WATCH)]  # watchlista jest zawsze na poczatku listy
        rest = sorted((i for i in wanted if i not in watch_ids),
                      key=lambda i: vols.get(str(i), 0), reverse=True)
        wanted = watch_ids + rest[:max(0, DAILY_MAX - len(watch_ids))]
        print(f"tryb dzienny: refresh {len(wanted)} items (pelny w sobote)")
    todo = [i for i in wanted if str(i) not in snap]
    # odswiez tez wpisy starsze niz 8 dni (rotacja w ramach dziennego limitu)
    print(f"done={len(snap)} todo={len(todo)}")
    for i, item_id in enumerate(todo):
        try:
            snap[str(item_id)] = get("/market_board", {"server": SERVER, "item_id": item_id})
        except Exception as e:
            print(f"board failed id={item_id}: {e}")
        if (i + 1) % 20 == 0:
            path.write_text(json.dumps(snap), encoding="utf-8")
            print(f"board {i + 1}/{len(todo)} (flush)", flush=True)
    path.write_text(json.dumps(snap), encoding="utf-8")
    print(f"DONE orderbook items={len(snap)} -> {path}")


if __name__ == "__main__":
    main()
