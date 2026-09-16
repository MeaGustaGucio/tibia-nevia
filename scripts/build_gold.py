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


SPAWN_COLS = ["spawn", "n_hunts", "median_xp_h", "max_xp_h", "median_profit_h", "max_profit_h",
              "min_lvl_seen", "max_lvl_seen", "sample_url"]


def spawn_stats(rows: list[dict]) -> list[dict]:
    import statistics

    groups: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("spawn"):
            groups.setdefault(r["spawn"], []).append(r)
    out = []
    for spawn, g in groups.items():
        xp = sorted(r["xp_h"] for r in g)
        pf = sorted(r["balance_h"] for r in g)
        lvls = [r["avg_lvl"] for r in g if r["avg_lvl"]]
        best = max(g, key=lambda r: r["xp_h"])
        out.append({
            "spawn": spawn, "n_hunts": len(g),
            "median_xp_h": int(statistics.median(xp)),
            "max_xp_h": max(xp),
            "median_profit_h": int(statistics.median(pf)),
            "max_profit_h": max(pf),
            "min_lvl_seen": min(lvls) if lvls else "",
            "max_lvl_seen": max(lvls) if lvls else "",
            "sample_url": best["url"],
        })
    return sorted(out, key=lambda r: r["median_xp_h"], reverse=True)


def write_spawns(name: str, rows: list[dict]):
    with open(GOLD / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SPAWN_COLS)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    ap.add_argument("--recent-days", type=int, default=None, help="nadpisuje OBA odciecia (tryb prosty)")
    ap.add_argument("--recent-days-profit", type=int, default=None)
    ap.add_argument("--recent-days-exp", type=int, default=None)
    ap.add_argument("--brackets", default=None, help="comma separated, np. '50-100,100-200'")
    a = ap.parse_args()
    cfg = load_config(pathlib.Path(a.config) if a.config else None)
    g = cfg["gold"]
    if a.recent_days is not None:
        rd_profit = rd_exp = a.recent_days
    else:
        rd_profit = a.recent_days_profit if a.recent_days_profit is not None else g.get("recent_days_profit", g.get("recent_days", 60))
        rd_exp = a.recent_days_exp if a.recent_days_exp is not None else g.get("recent_days_exp", g.get("recent_days", 365))
    brackets = (a.brackets.split(",") if a.brackets else g["brackets"])

    hunts_profit = load_hunts(rd_profit)
    hunts_exp = load_hunts(rd_exp) if rd_exp != rd_profit else hunts_profit
    manual = load_manual_prices()

    write("ranking_exp", sorted(hunts_exp, key=lambda r: r["xp_h"], reverse=True)[:50])
    write("ranking_profit", sorted(hunts_profit, key=lambda r: r["balance_h"], reverse=True)[:50])
    write_spawns("spawn_stats", spawn_stats(hunts_profit))
    for b in brackets:
        lo, hi = (int(x) for x in b.strip().split("-"))
        pe = [r for r in hunts_exp if r["avg_lvl"] and lo <= r["avg_lvl"] <= hi]
        pp = [r for r in hunts_profit if r["avg_lvl"] and lo <= r["avg_lvl"] <= hi]
        tag = f"{lo}_{hi}"
        write(f"ranking_exp_{tag}", sorted(pe, key=lambda r: r["xp_h"], reverse=True)[:50])
        write(f"ranking_profit_{tag}", sorted(pp, key=lambda r: r["balance_h"], reverse=True)[:50])
        write_spawns(f"spawn_stats_{tag}", spawn_stats(pp))
        print(f"bracket {b}: exp={len(pe)} profit={len(pp)} hunts")

    (GOLD / "build_info.json").write_text(
        json.dumps({"date": dt.date.today().isoformat(), "hunts": len(hunts_profit),
                    "hunts_exp": len(hunts_exp),
                    "recent_days": rd_profit, "recent_days_exp": rd_exp,
                    "manual_prices": manual}, indent=1), encoding="utf-8")

    # Kopia rankingow do docs/data/ — GitHub Pages serwuje caly folder docs/,
    # wiec dashboard (docs/index.html) czyta te CSV bez zadnego backendu.
    for p in list(GOLD.glob("ranking_*.csv")) + list(GOLD.glob("spawn_stats*.csv")) + [GOLD / "build_info.json"]:
        shutil.copy(p, PAGES_DATA / p.name)
    print(f"copied {len(list(PAGES_DATA.glob('*')))} files -> {PAGES_DATA}")
    try:
        import openpyxl

        wb = openpyxl.Workbook()
        first = True
        for p in sorted(list(GOLD.glob("ranking_*.csv")) + list(GOLD.glob("spawn_stats*.csv"))):
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
    print(f"DONE gold: profit_hunts={len(hunts_profit)} exp_hunts={len(hunts_exp)} manual={manual}")


if __name__ == "__main__":
    main()
