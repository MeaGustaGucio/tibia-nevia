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
        if pathlib.Path(p).parent.name == "sessions":
            continue
        with open(p, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r.get("side") == "buy_max":
                    prices[r["item"]] = int(r["price_gp"])
    return prices


def latest(pattern: str):
    files = sorted((ROOT / "data" / "raw").glob(f"*/{pattern}"))
    return files[-1] if files else None


PRICE_COLS = ["item_id", "item", "instant", "fair", "patient", "upside",
              "depth_units", "n_sell", "n_buy", "captured_at"]


def price_stats(boards: dict) -> list[dict]:
    """Uczciwa cena z drabinki: instant (top buy), fair (VWAP buy po obcieciu top 5%
    jednostek), patient (min sell), upside ((p25 sell - fair)/fair)."""
    out = []
    for iid, b in boards.items():
        sells = sorted(((o.get("price", 0), o.get("amount", 0)) for o in b.get("sellers", []) if o.get("price", 0) > 0))
        buys = sorted(((o.get("price", 0), o.get("amount", 0)) for o in b.get("buyers", []) if o.get("price", 0) > 0), reverse=True)
        if not sells and not buys:
            continue
        instant = buys[0][0] if buys else ""
        patient = sells[0][0] if sells else ""
        # fair: buy-side VWAP po obcieciu top 5% jednostek (scianki/bait)
        fair = ""
        if buys:
            total = sum(u for _, u in buys)
            cut = total * 0.05
            rest = []
            for price, units in buys:
                if cut >= units:
                    cut -= units
                    continue
                rest.append((price, units - cut))
                cut = 0
            # jesli obcielismy wszystko (1 oferta), wez ja w calosci
            rest = rest or buys
            fair = int(sum(p * u for p, u in rest) / sum(u for _, u in rest))
        # p25 sell (25% jednostek sell-side od dolu)
        p25 = ""
        if sells:
            total_s = sum(u for _, u in sells)
            acc = 0
            for price, units in sells:
                acc += units
                if acc >= total_s * 0.25:
                    p25 = price
                    break
        upside = round((p25 - fair) / fair, 3) if fair and p25 else ""
        depth = ""
        if fair:
            lo, hi = fair * 0.9, fair * 1.1
            depth = sum(u for p, u in sells + buys if lo <= p <= hi)
        ts = b.get("update_time", "")
        try:
            captured = dt.datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M") if ts else ""
        except (ValueError, TypeError):
            captured = ""
        out.append({"item_id": iid, "instant": instant, "fair": fair, "patient": patient,
                    "upside": upside, "depth_units": depth,
                    "n_sell": len(sells), "n_buy": len(buys), "captured_at": captured,
                    "_sells": sells, "_buys": buys})
    return out


SPAWN_ITEM_COLS = ["spawn", "item", "item_id", "instant", "fair", "patient", "price_date",
                   "n_sessions_spawn", "creatures"]


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


def spawn_items(hunts: list[dict], kills: list[dict], creatures: dict,
                price_by_name: dict, meta_by_name: dict) -> list[dict]:
    """Spawn -> itemy: unia loot_list potworow bitych na spawnie (z hunt_kills).
    Bez procentow dropu (Wiki ich nie daje) — to MAPA 'co tu pada + po ile chodzi',
    nie srednia/h. Srednie/h liczymy dopiero z session_loot (Wasze logi)."""
    hunt_spawn = {h["id"]: h.get("spawn", "") for h in hunts}
    spawn_creatures: dict[str, dict[str, int]] = {}
    spawn_sessions: dict[str, set] = {}
    for k in kills:
        sp = hunt_spawn.get(k["hunt_id"], "")
        if not sp:
            continue
        spawn_creatures.setdefault(sp, {}).setdefault(k["creature"], 0)
        spawn_creatures[sp][k["creature"]] += 1
        spawn_sessions.setdefault(sp, set()).add(k["hunt_id"])
    out = []
    for sp, census in spawn_creatures.items():
        items: dict[str, set] = {}
        for creature in census:
            for item in (creatures.get(creature, {}).get("loot_list") or []):
                items.setdefault(item, set()).add(creature)
        for item, crs in sorted(items.items()):
            key = item.lower()
            m = meta_by_name.get(key) or (meta_by_name.get(key[:-1]) if key.endswith("s") else None) or {}
            iid = m.get("id", "")
            pr = (price_by_name.get(key)
                  or (price_by_name.get(m.get("name", "").lower()) if m.get("name") else None)
                  or {})
            out.append({"spawn": sp, "item": item, "item_id": iid,
                        "instant": pr.get("instant", ""), "fair": pr.get("fair", ""),
                        "patient": pr.get("patient", ""), "price_date": pr.get("captured_at", ""),
                        "n_sessions_spawn": len(spawn_sessions.get(sp, set())),
                        "creatures": "|".join(sorted(crs)[:6])})
    return out


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

    # Drabinka + stworzenia + metadata (najnowsze snapshoty)
    boards, creatures, meta = {}, {}, []
    bf = latest("orderbook_nevia.json")
    if bf:
        boards = json.loads(bf.read_text(encoding="utf-8"))
    cf = latest("creatures.json")
    if cf:
        creatures = json.loads(cf.read_text(encoding="utf-8"))
    mf = latest("market_metadata_all.json")
    if mf:
        meta = json.loads(mf.read_text(encoding="utf-8"))
    meta_by_name = {str(m.get("name", "")).lower(): m for m in meta if m.get("name")}
    id_to_name = {str(m["id"]): m.get("name", "") for m in meta if m.get("id")}

    # Uczciwe ceny z drabinki
    prices = price_stats(boards)
    for p in prices:
        p["item"] = id_to_name.get(str(p["item_id"]), "")
    with open(GOLD / "price_stats.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=PRICE_COLS)
        w.writeheader()
        for p in prices:
            w.writerow({k: p.get(k, "") for k in PRICE_COLS})
    price_by_name = {str(p["item"]).lower(): p for p in prices if p.get("item")}
    print(f"price_stats items={len(prices)}")

    # Kille ze wszystkich zrzutow (do mapy spawn->itemy)
    kills = []
    for p in sorted((ROOT / "data" / "raw").glob("*/hunt_kills.csv"))[-14:]:
        with open(p, encoding="utf-8") as f:
            kills.extend(list(csv.DictReader(f)))
    all_hunts = {h["id"]: h for h in hunts_exp + hunts_profit}.values()
    si = spawn_items(list(all_hunts), kills, creatures, price_by_name, meta_by_name)
    with open(GOLD / "spawn_items.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SPAWN_ITEM_COLS)
        w.writeheader()
        w.writerows(si)
    print(f"spawn_items rows={len(si)}")

    # Per-item: drabinka + historia do docs/data (nadpisywane — tylko najnowszy stan)
    hist = {}
    hf = latest("market_history_top.json")
    if hf:
        hist = json.loads(hf.read_text(encoding="utf-8"))
    lad_dir, hist_dir = PAGES_DATA / "ladder", PAGES_DATA / "history"
    lad_dir.mkdir(exist_ok=True)
    hist_dir.mkdir(exist_ok=True)
    for p in prices:
        iid = str(p["item_id"])
        with open(lad_dir / f"{iid}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["side", "price", "units"])
            for price, units in p.pop("_sells"):
                w.writerow(["sell", price, units])
            for price, units in p.pop("_buys"):
                w.writerow(["buy", price, units])
        if iid in hist:
            with open(hist_dir / f"{iid}.csv", "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["date", "buy", "sell"])
                for snap in hist[iid]:
                    try:
                        d = dt.datetime.fromtimestamp(float(snap.get("time", 0))).strftime("%Y-%m-%d")
                    except (ValueError, TypeError):
                        d = ""
                    w.writerow([d, snap.get("day_average_buy", snap.get("buy_offer", "")),
                                snap.get("day_average_sell", snap.get("sell_offer", ""))])
    print(f"per-item files: ladder+history for {len(prices)} items")

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
                    "price_items": len(prices), "spawn_items": len(si),
                    "manual_prices": manual}, indent=1), encoding="utf-8")

    # Kopia rankingow do docs/data/ — GitHub Pages serwuje caly folder docs/,
    # wiec dashboard (docs/index.html) czyta te CSV bez zadnego backendu.
    for p in (list(GOLD.glob("ranking_*.csv")) + list(GOLD.glob("spawn_stats*.csv"))
              + [GOLD / "price_stats.csv", GOLD / "spawn_items.csv",
                 GOLD / "session_loot.csv", GOLD / "build_info.json"]):
        if p.exists():
            shutil.copy(p, PAGES_DATA / p.name)
    print(f"copied {len(list(PAGES_DATA.glob('*')))} files -> {PAGES_DATA}")
    try:
        import openpyxl

        wb = openpyxl.Workbook()
        first = True
        for p in sorted(list(GOLD.glob("ranking_*.csv")) + list(GOLD.glob("spawn_stats*.csv"))
                         + [GOLD / "price_stats.csv", GOLD / "spawn_items.csv", GOLD / "session_loot.csv"]):
            if not p.exists():
                continue
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
