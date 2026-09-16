"""Gold: rankingi EXP/h i profit/h + export CSV/XLSX do Excela/Pages.

Wejscie: data/raw/<date>/hunts.csv (+ market_values_nevia.json i data/manual/*.csv).
  python scripts/build_gold.py                              # caly zakres, hunty < 90 dni
  python scripts/build_gold.py --recent-days 30             # tylko swieze (po nerfie golda 07.09.2026!)
  python scripts/build_gold.py --brackets "50-100,100-200,200-300"

Profit dwutorowo (bo rozbicie loota na itemy ma tylko czesc huntow, flaga has_creature_stats):
  tor 1 (zawsze): Balance/h z hunta jako proxy profitu,
  tor 2: data/manual/*.csv (Twoje live ceny z gry, np. Rope Belt buy_max=4526) nadpisuje
         ceny trackera przy re-wycenie — pelna re-wycena dropu wlaczy sie w etapie 2
         (hunt_loot z Members Details), gdy uzbieramy hunty z creature stats.
XLSX wymaga openpyxl; bez niego zapisuje same CSV (pipeline nie failuje).
"""
import argparse
import csv
import datetime as dt
import glob
import json
import pathlib
import shutil

from common import ROOT, load_config

GOLD = ROOT / "data" / "gold"
GOLD.mkdir(parents=True, exist_ok=True)
PAGES_DATA = ROOT / "docs" / "data"  # kopia dla GitHub Pages (docs/ = root strony)
PAGES_DATA.mkdir(parents=True, exist_ok=True)

COLS = ["id", "spawn", "hunt_date", "duration", "party_size", "party_comp",
        "min_lvl", "max_lvl", "avg_lvl", "xp_h", "raw_xp_h", "balance_h", "has_creature_stats", "url"]


def parse_hunt_date(s: str):
    try:
        return dt.datetime.strptime(s.strip(), "%b %d, %Y %H:%M").date()
    except (ValueError, AttributeError):
        return None


def load_hunts(recent_days: int):
    rows = []
    for p in sorted((ROOT / "data" / "raw").glob("*/hunts.csv"))[-14:]:
        with open(p, encoding="utf-8") as f:
            rows.extend(list(csv.DictReader(f)))
    ded = {}
    for r in rows:
        ded[r["id"]] = r
    today = dt.date.today()
    fresh, stale = [], 0
    for r in ded.values():
        d = parse_hunt_date(r.get("hunt_date", ""))
        r["_days_ago"] = (today - d).days if d else 9999
        if r["_days_ago"] <= recent_days:
            fresh.append(r)
        else:
            stale += 1
    print(f"hunts total={len(ded)} fresh(<={recent_days}d)={len(fresh)} stale={stale}")
    for r in fresh:
        for k in ("xp_h", "raw_xp_h", "balance_h", "party_size", "min_lvl", "max_lvl", "avg_lvl"):
            try:
                r[k] = int(r.get(k) or 0)
            except ValueError:
                r[k] = 0
    return fresh


def load_manual_prices():
    prices = {}
    for p in glob.glob(str(ROOT / "data" / "manual" / "*.csv")):
        with open(p, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r.get("side") == "buy_max":
                    prices[r["item"]] = int(r["price_gp"])
    return prices


def write(name: str, rows: list[dict]):
    with open(GOLD / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in COLS})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    ap.add_argument("--recent-days", type=int, default=None)
    ap.add_argument("--brackets", default=None, help="comma separated, np. '50-100,100-200'")
    a = ap.parse_args()
    cfg = load_config(pathlib.Path(a.config) if a.config else None)
    recent_days = a.recent_days if a.recent_days is not None else cfg["gold"]["recent_days"]
    brackets = (a.brackets.split(",") if a.brackets else cfg["gold"]["brackets"])

    hunts = load_hunts(recent_days)
    manual = load_manual_prices()

    write("ranking_exp", sorted(hunts, key=lambda r: r["xp_h"], reverse=True)[:50])
    write("ranking_profit", sorted(hunts, key=lambda r: r["balance_h"], reverse=True)[:50])
    for b in brackets:
        lo, hi = (int(x) for x in b.strip().split("-"))
        part = [r for r in hunts if r["avg_lvl"] and lo <= r["avg_lvl"] <= hi]
        tag = f"{lo}_{hi}"
        write(f"ranking_exp_{tag}", sorted(part, key=lambda r: r["xp_h"], reverse=True)[:50])
        write(f"ranking_profit_{tag}", sorted(part, key=lambda r: r["balance_h"], reverse=True)[:50])
        print(f"bracket {b}: {len(part)} hunts")

    (GOLD / "build_info.json").write_text(
        json.dumps({"date": dt.date.today().isoformat(), "hunts": len(hunts),
                    "recent_days": recent_days, "manual_prices": manual}, indent=1), encoding="utf-8")

    # Kopia rankingow do docs/data/ — GitHub Pages serwuje caly folder docs/,
    # wiec dashboard (docs/index.html) czyta te CSV bez zadnego backendu.
    for p in list(GOLD.glob("ranking_*.csv")) + [GOLD / "build_info.json"]:
        shutil.copy(p, PAGES_DATA / p.name)
    print(f"copied {len(list(PAGES_DATA.glob('*')))} files -> {PAGES_DATA}")
    try:
        import openpyxl

        wb = openpyxl.Workbook()
        first = True
        for p in sorted(GOLD.glob("ranking_*.csv")):
            ws = wb.active if first else wb.create_sheet(p.stem)
            if first:
                ws.title = p.stem
                first = False
            with open(p, encoding="utf-8") as f:
                for row in csv.reader(f):
                    ws.append(row)
        wb.save(GOLD / "dashboard.xlsx")
        print("saved dashboard.xlsx")
    except ImportError:
        print("openpyxl missing -> tylko CSV")
    print(f"DONE gold: hunts={len(hunts)} manual={manual}")


if __name__ == "__main__":
    main()
