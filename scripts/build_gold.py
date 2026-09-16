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

COLS = ["id", "spawn", "hunt_date", "duration", "minutes", "party_size", "party_comp",
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


PRICE_COLS = ["item_id", "item", "instant", "fair", "shelf", "shelf_units", "patient",
              "upside", "depth_units", "n_sell", "n_buy", "captured_at"]


def price_stats(boards: dict, rules: dict, item_names: dict) -> list[dict]:
    """Uczciwa cena z drabinki (reguly globalne + per-item z config pricing):
    instant (top buy), fair (VWAP buy po obcieciu top trim% jednostek),
    shelf/polka (poziom sell z max jednostek, VWAP ±1% wokol niego),
    patient (min sell), upside ((p25 sell - fair)/fair).
    Filtry: max_sell_cap (np. vampire teeth 4000), exclude_anonymous."""
    trim = float(rules.get("trim_top_pct", 5)) / 100.0
    excl_anon = bool(rules.get("exclude_anonymous", False))
    cap_global = rules.get("max_sell_cap")
    per_item = rules.get("items", {}) or {}
    out = []
    for iid, b in boards.items():
        name = (item_names.get(str(iid), "") or "").lower()
        ir = per_item.get(name, {}) or {}
        cap = ir.get("max_sell_cap", cap_global)
        excl = ir.get("exclude_anonymous", excl_anon)

        def keep(o, side):
            if o.get("price", 0) <= 0:
                return False
            if excl and str(o.get("name", "")).lower() == "anonymous":
                return False
            if side == "sell" and cap and o["price"] > cap:
                return False
            return True

        sells = sorted(((o["price"], o.get("amount", 0)) for o in b.get("sellers", []) if keep(o, "sell")))
        buys = sorted(((o["price"], o.get("amount", 0)) for o in b.get("buyers", []) if keep(o, "buy")), reverse=True)
        if not sells and not buys:
            continue
        instant = buys[0][0] if buys else ""
        patient = sells[0][0] if sells else ""
        fair = ""
        if buys:
            total = sum(u for _, u in buys)
            cut = total * trim
            rest = []
            for price, units in buys:
                if cut >= units:
                    cut -= units
                    continue
                rest.append((price, units - cut))
                cut = 0
            rest = rest or buys
            fair = int(sum(p * u for p, u in rest) / sum(u for _, u in rest))
        # polka: poziom sell z najwieksza liczba jednostek (+-1% wokol niego)
        shelf, shelf_units = "", ""
        if sells:
            levels: dict[int, int] = {}
            for price, units in sells:
                levels[price] = levels.get(price, 0) + units
            shelf = max(levels, key=lambda p: (levels[p], -p))
            shelf_units = levels[shelf]
            near = [(p, u) for p, u in sells if abs(p - shelf) <= shelf * 0.01]
            if near:
                shelf = int(sum(p * u for p, u in near) / sum(u for _, u in near))
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
        out.append({"item_id": iid, "instant": instant, "fair": fair, "shelf": shelf,
                    "shelf_units": shelf_units, "patient": patient,
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


KILLS_H_COLS = ["hunt_id", "spawn", "hunt_date", "minutes", "creature", "killed",
                "kills_per_h", "xp_h", "balance_h", "url"]


def kills_enriched(hunts: list[dict], kills: list[dict]) -> list[dict]:
    """Kille per sesja + kills/h (czas sesji z kolumny minutes). Najwieksza granulacja
    jaka istnieje publicznie: dokladnie ile potworow padlo w danej sesji i w jakim tempie."""
    hmap = {h["id"]: h for h in hunts}
    out = []
    for k in kills:
        h = hmap.get(k["hunt_id"])
        if not h:
            continue
        try:
            mins = int(h.get("minutes") or 0)
        except ValueError:
            mins = 0
        try:
            killed = int(k.get("killed") or 0)
        except ValueError:
            killed = 0
        out.append({"hunt_id": k["hunt_id"], "spawn": h.get("spawn", ""),
                    "hunt_date": h.get("hunt_date", ""), "minutes": mins,
                    "creature": k.get("creature", ""), "killed": killed,
                    "kills_per_h": round(killed / mins * 60, 1) if mins > 0 else "",
                    "xp_h": h.get("xp_h", ""), "balance_h": h.get("balance_h", ""),
                    "url": h.get("url", "")})
    return out


TAGS_COLS = ["item", "fair", "imbuements", "delivery_npcs", "delivery_bands", "npc_price"]


def load_reference_tags() -> tuple[dict, dict]:
    """Zwraca (imbu, delivery):
    imbu[item_lower] = {"Powerful Vampirism x25", ...}
    delivery[item_lower] = {"npcs": set, "bands": set, "npc_price": int|""}"""
    imbu: dict[str, set] = {}
    p = ROOT / "data" / "reference" / "imbuing_items.csv"
    if p.exists():
        with open(p, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r.get("item"):
                    imbu.setdefault(r["item"].strip().lower(), set()).add(
                        f'{r.get("tier", "")} {r.get("imbuement", "")} x{r.get("qty", "")}'.strip())
    delivery: dict[str, dict] = {}
    for fn in ("delivery_npc.csv", "delivery_items.csv"):
        q = ROOT / "data" / "reference" / fn
        if not q.exists():
            continue
        with open(q, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                name = (r.get("item") or "").strip()
                if not name:
                    continue
                d = delivery.setdefault(name.lower(), {"name": name, "npcs": set(), "bands": set(), "npc_price": ""})
                npc = (r.get("npc") or "").strip()
                if npc and npc != "Everything":
                    d["npcs"].add("Rashid" if npc == "RashidTab" else npc)
                band = (r.get("market_band") or "").strip()
                if band:
                    d["bands"].add(band)
                try:
                    pr = int(str(r.get("npc_price", "")).replace(" ", ""))
                    if pr and (d["npc_price"] == "" or pr > d["npc_price"]):
                        d["npc_price"] = pr
                except ValueError:
                    pass
    return imbu, delivery


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
    prices = price_stats(boards, cfg.get("pricing", {}), id_to_name)
    for p in prices:
        p["item"] = id_to_name.get(str(p["item_id"]), "")
    with open(GOLD / "price_stats.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=PRICE_COLS)
        w.writeheader()
        for p in prices:
            w.writerow({k: p.get(k, "") for k in PRICE_COLS})
    price_by_name = {str(p["item"]).lower(): p for p in prices if p.get("item")}
    print(f"price_stats items={len(prices)}")

    # Tagi popytu: imbu + delivery, z fair Nevii (podstawa strony demand.html)
    imbu, delivery = load_reference_tags()
    tag_rows = []
    for key in sorted(set(imbu) | set(delivery)):
        pr = price_by_name.get(key, {}) or {}
        # display name: z price, inaczej z delivery/imbu klucza
        disp = pr.get("item") or (delivery.get(key, {}).get("name") or key)
        d = delivery.get(key, {"npcs": set(), "bands": set(), "npc_price": ""})
        tag_rows.append({"item": disp, "fair": pr.get("fair", ""),
                         "imbuements": "|".join(sorted(imbu.get(key, set()))),
                         "delivery_npcs": "|".join(sorted(d["npcs"])),
                         "delivery_bands": "|".join(sorted(d["bands"])),
                         "npc_price": d["npc_price"]})
    with open(GOLD / "item_tags.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TAGS_COLS)
        w.writeheader()
        w.writerows(tag_rows)
    print(f"item_tags rows={len(tag_rows)}")

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

    # Kille/h per sesja per potwor — maksymalna publiczna granulacja
    kh = kills_enriched(list(all_hunts), kills)
    with open(GOLD / "hunt_kills_h.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=KILLS_H_COLS)
        w.writeheader()
        w.writerows(kh)
    print(f"hunt_kills_h rows={len(kh)}")

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
                    "tagged_items": len(tag_rows),
                    "sessions_le31d": sum(1 for h in hunts_exp if h.get("_days_ago", 9999) <= 31),
                    "sessions_le62d": sum(1 for h in hunts_exp if h.get("_days_ago", 9999) <= 62),
                    "manual_prices": manual}, indent=1), encoding="utf-8")

    # Kopia rankingow do docs/data/ — GitHub Pages serwuje caly folder docs/,
    # wiec dashboard (docs/index.html) czyta te CSV bez zadnego backendu.
    for p in (list(GOLD.glob("ranking_*.csv")) + list(GOLD.glob("spawn_stats*.csv"))
              + [GOLD / "price_stats.csv", GOLD / "spawn_items.csv", GOLD / "hunt_kills_h.csv",
                 GOLD / "item_tags.csv",
                 GOLD / "session_loot.csv", GOLD / "build_info.json"]):
        if p.exists():
            shutil.copy(p, PAGES_DATA / p.name)
    print(f"copied {len(list(PAGES_DATA.glob('*')))} files -> {PAGES_DATA}")
    try:
        import openpyxl

        wb = openpyxl.Workbook()
        first = True
        for p in sorted(list(GOLD.glob("ranking_*.csv")) + list(GOLD.glob("spawn_stats*.csv"))
                         + [GOLD / "price_stats.csv", GOLD / "spawn_items.csv",
                            GOLD / "hunt_kills_h.csv", GOLD / "item_tags.csv",
                            GOLD / "session_loot.csv"]):
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
