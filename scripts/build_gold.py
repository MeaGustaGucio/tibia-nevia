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
import re
import shutil

from common import ROOT, load_config

GOLD = ROOT / "data" / "gold"
GOLD.mkdir(parents=True, exist_ok=True)
PAGES_DATA = ROOT / "docs" / "data"  # kopia dla GitHub Pages (docs/ = root strony)
PAGES_DATA.mkdir(parents=True, exist_ok=True)

COLS = ["id", "spawn", "hunt_date", "duration", "minutes", "party_size", "party_comp",
        "min_lvl", "max_lvl", "avg_lvl", "xp_h", "raw_xp_h", "loot_h", "balance_h",
        "supplies_total", "supplies_known", "has_creature_stats", "event_flag", "url"]


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
    min_year = 2026  # TWARDY FILTR: tylko biezacy rok, zadnych 2024/2025!
    fresh, stale, oldyear = [], 0, 0
    for r in ded.values():
        d = parse_hunt_date(r.get("hunt_date", ""))
        if d and d.year < min_year:
            oldyear += 1
            continue
        r["_days_ago"] = (today - d).days if d else 9999
        if r["_days_ago"] <= recent_days:
            fresh.append(r)
        else:
            stale += 1
    print(f"hunts total={len(ded)} fresh(<={recent_days}d)={len(fresh)} stale={stale} pre2026={oldyear}")
    for r in fresh:
        for k in ("xp_h", "raw_xp_h", "balance_h", "loot_h", "party_size", "min_lvl",
                  "max_lvl", "avg_lvl", "supplies_total", "supplies_known", "minutes"):
            try:
                r[k] = int(float(r.get(k) or 0))
            except ValueError:
                r[k] = 0
    return fresh


def load_events() -> set:
    """Daty eventow 2x exp/loot (wykluczane z median — pompowalyby wyniki).
    Zrodlo: data/raw/<date>/events.json (fetch_tibia_events.py) + reczne daty
    z configu (tu tez, zeby dzialaly bez re-fetcha)."""
    dates = set()
    for p in sorted((ROOT / "data" / "raw").glob("*/events.json"))[-4:]:
        try:
            for e in json.loads(p.read_text(encoding="utf-8")):
                if e.get("date"):
                    dates.add(str(e["date"])[:10])
        except Exception:
            pass
    try:
        for d in (load_config().get("events", {}) or {}).get("extra_dates", []) or []:
            dates.add(str(d)[:10])
    except Exception:
        pass
    return dates


def flag_events(rows: list[dict], event_dates: set) -> int:
    n = 0
    for r in rows:
        d = parse_hunt_date(r.get("hunt_date", ""))
        r["event_flag"] = 1 if (d and d.isoformat() in event_dates) else 0
        n += r["event_flag"]
    return n


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


PRICE_COLS = ["item_id", "item", "instant", "top_buy", "fair", "shelf", "shelf_units",
              "patient", "upside", "depth_units", "n_sell", "n_buy", "n_sell_red",
              "captured_at"]


def price_stats(boards: dict, rules: dict, item_names: dict, averages: dict) -> list[dict]:
    """Uczciwa cena z drabinki (reguly globalne + per-item z config pricing).
    RED = zasada z oficjalnego manuala Tibii: sell >= +25% sredniej serwera
    i buy <= -25% sredniej -> ODRZUCAMY (ostrzezenie o nieuczciwej ofercie).
    instant = min sell (po filtrach) - 1, czyli cena natychmiastowego podciecia;
    top_buy (zakladka BUY) to tylko statystyka poboczna.
    fair = VWAP buy po obcieciu top trim% jednostek; shelf/polka = poziom sell
    z max jednostek; patient = min sell; upside = (p25 sell - fair)/fair."""
    trim = float(rules.get("trim_top_pct", 5)) / 100.0
    excl_anon = bool(rules.get("exclude_anonymous", False))
    use_red = bool(rules.get("use_red_filter", True))
    cap_global = rules.get("max_sell_cap")
    per_item = rules.get("items", {}) or {}
    out = []
    for iid, b in boards.items():
        name = (item_names.get(str(iid), "") or "").lower()
        ir = per_item.get(name, {}) or {}
        cap = ir.get("max_sell_cap", cap_global)
        excl = ir.get("exclude_anonymous", excl_anon)
        avg = averages.get(str(iid), {}) or {}
        avg_sell = avg.get("day_average_sell") or avg.get("month_average_sell") or 0
        avg_buy = avg.get("day_average_buy") or avg.get("month_average_buy") or 0

        def red(price, side):
            if not use_red:
                return False
            if side == "sell" and avg_sell > 0:
                return price >= 1.25 * avg_sell
            if side == "buy" and avg_buy > 0:
                return price <= 0.75 * avg_buy
            return False

        def keep(o, side):
            if o.get("price", 0) <= 0:
                return False
            if excl and str(o.get("name", "")).lower() == "anonymous":
                return False
            if side == "sell" and cap and o["price"] > cap:
                return False
            if red(o["price"], side):
                return False
            return True

        raw_sells = sorted((o["price"] for o in b.get("sellers", []) if o.get("price", 0) > 0))
        sells = sorted(((o["price"], o.get("amount", 0)) for o in b.get("sellers", []) if keep(o, "sell")))
        buys = sorted(((o["price"], o.get("amount", 0)) for o in b.get("buyers", []) if keep(o, "buy")), reverse=True)
        n_red = len(raw_sells) - sum(1 for o in b.get("sellers", [])
                                     if o.get("price", 0) > 0 and not (cap and o["price"] > cap)
                                     and not red(o["price"], "sell")
                                     and not (excl and str(o.get("name", "")).lower() == "anonymous"))
        if not sells and not buys:
            continue
        top_buy = buys[0][0] if buys else ""
        patient = sells[0][0] if sells else ""
        instant = patient - 1 if patient else ""
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
        out.append({"item_id": iid, "instant": instant, "top_buy": top_buy, "fair": fair,
                    "shelf": shelf,
                    "shelf_units": shelf_units, "patient": patient,
                    "upside": upside, "depth_units": depth,
                    "n_sell": len(sells), "n_buy": len(buys), "n_sell_red": n_red,
                    "captured_at": captured,
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
              "n_full_loot", "min_lvl_seen", "max_lvl_seen", "sample_url"]


def spawn_stats(rows: list[dict]) -> list[dict]:
    import statistics

    groups: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("spawn"):
            groups.setdefault(r["spawn"], []).append(r)
    out = []
    for spawn, g in groups.items():
        xp = sorted(r["xp_h"] for r in g)
        # PROFIT = loot/h policzony z sesji (Balance + supplies), NIE gotowy Balance!
        pf = sorted(r["loot_h"] for r in g)
        lvls = [r["avg_lvl"] for r in g if r["avg_lvl"]]
        best = max(g, key=lambda r: r["xp_h"])
        n_full = sum(1 for r in g if r.get("supplies_known"))
        out.append({
            "spawn": spawn, "n_hunts": len(g),
            "median_xp_h": int(statistics.median(xp)),
            "max_xp_h": max(xp),
            "median_profit_h": int(statistics.median(pf)),
            "max_profit_h": max(pf),
            "n_full_loot": n_full,
            "min_lvl_seen": min(lvls) if lvls else "",
            "max_lvl_seen": max(lvls) if lvls else "",
            "sample_url": best["url"],
        })
    return sorted(out, key=lambda r: r["median_xp_h"], reverse=True)


def spawn_items(hunts: list[dict], kills: list[dict], creatures: dict,
                price_by_name: dict, meta_by_name: dict) -> list[dict]:
    """Spawn -> itemy: unia loot_list potworow bitych na spawnie (z hunt_kills).
    Bez procentow dropu (Wiki ich nie daje) — to MAPA 'co tu pada + po ile chodzi'.
    Srednie/h per item liczy strona z value-per-kill (creature_value.csv)."""
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
                "kills_per_h", "xp_h", "loot_h", "balance_h", "url"]

VCALIB_DAYS = 120  # kalibracja value-per-kill: swieze sesje (ceny malo dryfuja), ale szersze niz profit


def wmedian(pairs: list) -> int:
    """Mediana wazona: pairs = [(wartosc, waga)]."""
    tot = sum(w for _, w in pairs)
    if tot <= 0:
        return 0
    acc = 0
    for v, w in sorted(pairs):
        acc += w
        if acc >= tot / 2:
            return int(v)
    return int(sorted(pairs)[-1][0])


def calibrate_value_per_kill(hunts: list[dict], kills: list[dict]):
    """Ile warta jest SREDNIO jedna sztuka potwora: loot/h sesji rozdzielony na
    gatunki proporcjonalnie do killi, obserwacje wazone udzialem (dominantne sesje
    waza najmocniej). Mediana wazona per gatunek. W pelni weryfikowalne."""
    hmap = {h["id"]: h for h in hunts
            if (h.get("_days_ago", 9999) or 9999) <= VCALIB_DAYS and (h.get("loot_h") or 0) > 0}
    by_hunt: dict[str, list] = {}
    for k in kills:
        if k["hunt_id"] in hmap:
            by_hunt.setdefault(k["hunt_id"], []).append(k)
    obs: dict[str, list] = {}
    samples: dict[str, list] = {}
    for hid, rows in by_hunt.items():
        h = hmap[hid]
        try:
            mins = int(h.get("minutes") or 0)
        except ValueError:
            continue
        if mins < 15:
            continue
        counts = [(r["creature"], int(r.get("killed") or 0)) for r in rows]
        counts = [(c, n) for c, n in counts if n > 0]
        tot = sum(n for _, n in counts)
        if tot <= 0:
            continue
        loot_h = float(h["loot_h"])
        for creature, n in counts:
            share = n / tot
            kph = n / mins * 60
            if kph <= 0:
                continue
            v = (loot_h * share) / kph  # wartosc per kill przy proporcjonalnym podziale
            obs.setdefault(creature, []).append((v, share))
            if len(samples.get(creature, [])) < 5:
                samples.setdefault(creature, []).append(h.get("url", ""))
    out = []
    for creature, o in obs.items():
        vs = sorted(v for v, _ in o)
        out.append({"creature": creature, "n_sessions": len(o),
                    "value_per_kill": wmedian(o),
                    "min_v": int(vs[0]), "max_v": int(vs[-1]),
                    "sample_urls": "|".join(samples.get(creature, []))})
    return sorted(out, key=lambda r: r["n_sessions"], reverse=True)


SPAWN_PROFIT_COLS = ["spawn", "profit_computed_h", "coverage", "n_sessions",
                     "measured_loot_h", "valued", "missing"]


def spawn_profit_computed(hunts: list[dict], kills: list[dict], vcalib: list[dict]):
    """Profit/h spawna POLICZONY: suma po potworach (srednie kille/h × value-per-kill).
    coverage = udzial killi z wycenionych gatunkow. Brak wyceny = jawna luka, nie zgadywanie."""
    vc = {r["creature"]: r["value_per_kill"] for r in vcalib}
    hmap = {h["id"]: h for h in hunts
            if (h.get("_days_ago", 9999) or 9999) <= VCALIB_DAYS}
    sp_kills: dict[str, dict[str, list]] = {}
    sp_hours: dict[str, float] = {}
    sp_loot: dict[str, list] = {}
    seen_hunts: dict[str, set] = {}
    for k in kills:
        h = hmap.get(k["hunt_id"])
        if not h:
            continue
        try:
            mins = int(h.get("minutes") or 0)
            killed = int(k.get("killed") or 0)
        except ValueError:
            continue
        if mins < 15 or killed <= 0:
            continue
        sp = h.get("spawn", "")
        sp_kills.setdefault(sp, {}).setdefault(k["creature"], []).append(killed / mins * 60)
        seen_hunts.setdefault(sp, set()).add(k["hunt_id"])
        if h.get("loot_h"):
            sp_loot.setdefault(sp, []).append(float(h["loot_h"]))
    for sp, hs in seen_hunts.items():
        hrs = 0.0
        for hid in hs:
            try:
                hrs += int(hmap[hid].get("minutes") or 0) / 60
            except ValueError:
                pass
        sp_hours[sp] = hrs
    import statistics
    out = []
    for sp, census in sp_kills.items():
        profit, valued_units, all_units, valued, missing = 0.0, 0.0, 0.0, [], []
        for creature, rates in census.items():
            avg_kph = sum(rates) / len(rates)
            all_units += avg_kph
            if creature in vc:
                profit += avg_kph * vc[creature]
                valued_units += avg_kph
                valued.append(f"{creature} {avg_kph:.0f}/h×{vc[creature]}")
            else:
                missing.append(creature)
        ml = sp_loot.get(sp, [])
        out.append({"spawn": sp, "profit_computed_h": int(profit),
                    "coverage": round(valued_units / all_units, 2) if all_units else 0,
                    "n_sessions": len(seen_hunts.get(sp, set())),
                    "measured_loot_h": int(statistics.median(sorted(ml))) if ml else "",
                    "valued": ";".join(sorted(valued)[:10]),
                    "missing": "|".join(sorted(missing)[:10])})
    return sorted(out, key=lambda r: r["profit_computed_h"], reverse=True)


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
                    "xp_h": h.get("xp_h", ""), "loot_h": h.get("loot_h", ""),
                    "balance_h": h.get("balance_h", ""),
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


CONSENSUS_COLS = ["spawn", "consensus_h", "spread_pct", "n_sources", "sources"]
COMPARE_COLS = ["spawn", "norm", "kind", "source", "lo", "hi", "n", "date", "url",
                "cluster", "cluster_members"]


STOPWORDS = {"the", "solo", "duo", "trio", "team", "ed", "ek", "rp", "ms", "em",
             "druid", "knight", "paladin", "sorcerer", "monk", "hunt", "party",
             "north", "south", "east", "west", "upper", "lower", "depot", "dp",
             "fullmoon", "full", "moon", "double", "rapid", "boosted", "boost",
             "post", "nerf", "teste", "test", "bestiary", "bounty", "with", "and",
             "na", "de", "com", "en", "w", "z", "ze", "do", "no", "nos", "das",
             "adept", "massive", "soloo", "hunts", "boost", "dmg", "dobre", "xp"}


def stem(w: str) -> str:
    if len(w) > 4 and w.endswith("s"):
        return w[:-1]
    return w


def canon_tokens(name: str) -> set:
    t = re.sub(r"\[[^\]]*\]|\([^)]*\)|\|[^|]*\|", " ", (name or "").lower())
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    out = set()
    for w in t.split():
        if w in STOPWORDS or len(w) <= 1 or w.isdigit():
            continue
        out.add(stem(w))
    return out


def norm_spawn(name: str) -> str:
    """Stabilny klucz canonical (sortowany) — tylko do deterministycznych operacji."""
    return " ".join(sorted(canon_tokens(name)))


def cluster_spawns(names: list, threshold: float = 0.5) -> dict:
    """Union-find po Jaccard(tokeny) >= threshold. Zwraca {raw_name: cluster_id}.
    Np. 'Yalahar Cults'~'Cults Yalahar', 'Burster Spectre #25'~'Burster Spectres';
    'Asura Palace' vs 'Asura Mirror' zostaja osobno."""
    uniq = sorted(set(names))
    toks = {n: canon_tokens(n) for n in uniq}
    parent = {n: n for n in uniq}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i, a in enumerate(uniq):
        if not toks[a]:
            continue
        for b in uniq[i + 1:]:
            if not toks[b]:
                continue
            inter = len(toks[a] & toks[b])
            union_ = len(toks[a] | toks[b])
            if union_ and inter / union_ >= threshold:
                union(a, b)
    clusters: dict[str, list] = {}
    for n in uniq:
        clusters.setdefault(find(n), []).append(n)
    mapping = {}
    for cid, members in clusters.items():
        for m in members:
            mapping[m] = cid
    return mapping


def parse_money(s):
    """'150000'->(150000,150000); '750K~900K'->(750000,900000); '2.4kk'->(2400000,2400000)."""
    if s is None:
        return None
    t = str(s).lower().replace("~", "-").replace("–", "-").replace(" ", "")
    if not t or t in ("-", "—"):
        return None
    def one(x):
        m = re.match(r"([\d.,]+)(kk|k)?", x)
        if not m:
            return None
        v = float(m.group(1).replace(",", "."))
        mult = 1000000 if m.group(2) == "kk" else (1000 if m.group(2) == "k" else 1)
        return int(v * mult)
    if "-" in t:
        a, b = t.split("-", 1)
        va, vb = one(a), one(b)
        if va is None or vb is None:
            return None
        return (min(va, vb), max(va, vb))
    v = one(t)
    return (v, v) if v is not None else None


def load_compare_inputs(sprof_rows, spawn_stats_rows, guide_bracket=None):
    """Zbierz wiersze porownawcze: computed + measured + guides + community. Zwraca listę dictów."""
    rows = []
    for r in sprof_rows:
        try:
            v = int(r.get("profit_computed_h") or 0)
        except ValueError:
            continue
        if v > 0:
            rows.append({"spawn": r.get("spawn", ""), "norm": norm_spawn(r.get("spawn", "")),
                         "kind": "computed", "source": "sesje+kille (nasz model)",
                         "lo": v, "hi": v, "n": r.get("n_sessions", ""),
                         "date": dt.date.today().isoformat(), "url": ""})
    for r in spawn_stats_rows:
        try:
            v = int(r.get("median_profit_h") or 0)
        except ValueError:
            continue
        if v > 0:
            rows.append({"spawn": r.get("spawn", ""), "norm": norm_spawn(r.get("spawn", "")),
                         "kind": "measured", "source": "mediana loot/h z sesji",
                         "lo": v, "hi": v, "n": r.get("n_hunts", ""),
                         "date": dt.date.today().isoformat(), "url": r.get("sample_url", "")})
    # poradniki (tylko 2026!); przy tagu bracketu tylko pasujace wiersze
    for fn in ("control_estimates.csv",):
        for base in (ROOT / "research", GOLD):
            p = base / fn if base == ROOT / "research" else base / fn
            if not p.exists():
                continue
            with open(p, encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    if guide_bracket and (r.get("bracket", "") or "") != guide_bracket:
                        continue
                    try:
                        y = int(str(r.get("source_date", ""))[:4])
                    except ValueError:
                        continue
                    if y < 2026:
                        continue
                    lo, hi = None, None
                    try:
                        if r.get("profit_lo"):
                            lo = int(float(r["profit_lo"]))
                        if r.get("profit_hi"):
                            hi = int(float(r["profit_hi"]))
                    except ValueError:
                        continue
                    if lo is None and hi is None:
                        continue
                    rows.append({"spawn": r.get("spawn", ""), "norm": norm_spawn(r.get("spawn", "")),
                                 "kind": "guide", "source": f'{r.get("source", "")} ({r.get("source_date", "")})',
                                 "lo": lo or hi, "hi": hi or lo, "n": "", "date": r.get("source_date", ""), "url": ""})
    # community claims (tylko 2026, tylko z profit_h)
    for p in sorted((ROOT / "research" / "blocks").glob("*/claims.jsonl")):
        with open(p, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                try:
                    y = int(str(r.get("date", ""))[:4])
                except ValueError:
                    continue
                if y < 2026 or not r.get("profit_h"):
                    continue
                rng = parse_money(r["profit_h"])
                if not rng:
                    continue
                rows.append({"spawn": r.get("spawn", ""), "norm": norm_spawn(r.get("spawn", "")),
                             "kind": "community", "source": "gracze (link)",
                             "lo": rng[0], "hi": rng[1], "n": "",
                             "date": r.get("date", ""), "url": r.get("url", "")})
    # klasteryzacja nazw + sklad klastra w kazdym wierszu (frontend laczy po nazwach)
    cmap = cluster_spawns([r["spawn"] for r in rows])
    clmembers: dict[str, set] = {}
    for r in rows:
        r["cluster"] = cmap.get(r["spawn"], r["spawn"])
        clmembers.setdefault(r["cluster"], set()).add(r["spawn"])
    for r in rows:
        r["cluster_members"] = "|".join(sorted(clmembers[r["cluster"]]))
    return rows


def consensus(rows: list[dict]):
    """Konsensus per KLASTER spawnow (clustering Jaccard — patrz cluster_spawns):
    mediana wazona srodkow (computed 3, measured 2, guide 1, community 1)."""
    W = {"computed": 3, "measured": 2, "guide": 1, "community": 1}
    groups: dict[str, list] = {}
    for r in rows:
        groups.setdefault(r.get("cluster", r["spawn"]), []).append(r)
    out = []
    for cid, g in groups.items():
        mids = [((r["lo"] + r["hi"]) / 2, W.get(r["kind"], 1)) for r in g]
        tot = sum(w for _, w in mids)
        acc, cons = 0, mids[0][0] if mids else 0
        for v, w in sorted(mids):
            acc += w
            if acc >= tot / 2:
                cons = v
                break
        lo_all = min(r["lo"] for r in g)
        hi_all = max(r["hi"] for r in g)
        from collections import Counter
        disp = Counter(r["spawn"] for r in g).most_common(1)[0][0]
        members = sorted({r["spawn"] for r in g})
        out.append({"spawn": disp, "norm": cid[:60], "consensus_h": int(cons),
                    "spread_pct": round((hi_all - lo_all) / cons, 2) if cons else "",
                    "n_sources": len(g), "members": "|".join(members),
                    "sources": "|".join(sorted({f'{r["kind"]}:{r["source"]}' for r in g})[:8])})
    return sorted(out, key=lambda r: r["consensus_h"], reverse=True)


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

    # Eventy 2x exp/loot: sesje z tych dni wypadaja z rankingow i median (pompowalyby wyniki).
    event_dates = load_events()
    n_ev = flag_events(hunts_profit, event_dates) + (flag_events(hunts_exp, event_dates) if hunts_exp is not hunts_profit else 0)
    hunts_profit = [h for h in hunts_profit if not h["event_flag"]]
    hunts_exp = [h for h in hunts_exp if not h["event_flag"]]
    print(f"eventy: {len(event_dates)} dni, wykluczono sesji(protexp+exp)={n_ev}")

    # Drabinka: merge z ostatnich 7 dni (nowsze wygrywaja) — dzienny refresh obejmuje
    # tylko podzbior, reszta zyje poprzednim snapshotem (captured_at przy kazdej cenie).
    boards = {}
    for bf in sorted((ROOT / "data" / "raw").glob("*/orderbook_nevia.json"))[-7:]:
        try:
            boards.update(json.loads(bf.read_text(encoding="utf-8")))
        except Exception:
            pass
    print(f"orderbook merged: {len(boards)} items") if boards else None
    creatures, meta = {}, []
    cf = latest("creatures.json")
    if cf:
        creatures = json.loads(cf.read_text(encoding="utf-8"))
    mf = latest("market_metadata_all.json")
    if mf:
        meta = json.loads(mf.read_text(encoding="utf-8"))
    meta_by_name = {str(m.get("name", "")).lower(): m for m in meta if m.get("name")}
    id_to_name = {str(m["id"]): m.get("name", "") for m in meta if m.get("id")}

    # Uczciwe ceny z drabinki (+ srednie serwera do reguly RED z manuala)
    avgs = {}
    vf = latest("market_values_nevia.json")
    if vf:
        for row in json.loads(vf.read_text(encoding="utf-8")):
            avgs[str(row.get("id"))] = row
    prices = price_stats(boards, cfg.get("pricing", {}), id_to_name, avgs)
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

    # Wartosc-per-kill (kalibracja na sesjach jednogatunkowych) + POLICZONY profit/h spawnow
    vcalib = calibrate_value_per_kill(list(all_hunts), kills)
    with open(GOLD / "creature_value.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["creature", "n_sessions", "value_per_kill",
                                          "min_v", "max_v", "sample_urls"])
        w.writeheader()
        w.writerows(vcalib)
    sprof = spawn_profit_computed(list(all_hunts), kills, vcalib)
    with open(GOLD / "spawn_profit.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SPAWN_PROFIT_COLS)
        w.writeheader()
        w.writerows(sprof)
    print(f"creature_value: {len(vcalib)} gatunkow; spawn_profit: {len(sprof)} spawnow")
    for b in brackets:
        lo, hi = (int(x) for x in b.strip().split("-"))
        hb = [h for h in hunts_profit if h["avg_lvl"] and lo <= h["avg_lvl"] <= hi]
        # kalibracja globalna, srednie kille/h z bracketu
        ids = {h["id"] for h in hb}
        kb = [k for k in kills if k["hunt_id"] in ids]
        spb = spawn_profit_computed(hb, kb, vcalib)
        with open(GOLD / f"spawn_profit_{lo}_{hi}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=SPAWN_PROFIT_COLS)
            w.writeheader()
            w.writerows(spb)
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
    # PROFIT = loot/h policzony z sesji (Balance + supplies), NIE gotowy Balance!
    write("ranking_profit", sorted(hunts_profit, key=lambda r: r["loot_h"], reverse=True)[:50])
    ss_all = spawn_stats(hunts_profit)
    write_spawns("spawn_stats", ss_all)
    bracket_inputs = {}
    for b in brackets:
        lo, hi = (int(x) for x in b.strip().split("-"))
        pe = [r for r in hunts_exp if r["avg_lvl"] and lo <= r["avg_lvl"] <= hi]
        pp = [r for r in hunts_profit if r["avg_lvl"] and lo <= r["avg_lvl"] <= hi]
        tag = f"{lo}_{hi}"
        write(f"ranking_exp_{tag}", sorted(pe, key=lambda r: r["xp_h"], reverse=True)[:50])
        write(f"ranking_profit_{tag}", sorted(pp, key=lambda r: r["loot_h"], reverse=True)[:50])
        ss_b = spawn_stats(pp)
        write_spawns(f"spawn_stats_{tag}", ss_b)
        bracket_inputs[tag] = (pp, ss_b)
        print(f"bracket {b}: exp={len(pe)} profit={len(pp)} hunts")

    # PROFIT-KONSENSUS z wielu zrodel (sesje policzone/zmierzone + poradniki + gracze).
    # Zadnych danych sprzed 2026 (filtr twardy) i zadnego polegania na jednym zrodle.
    def build_consensus(sprof_rows, ss_rows, suffix, guide_bracket=None):
        cmp_rows = load_compare_inputs(sprof_rows, ss_rows, guide_bracket)
        with open(GOLD / f"profit_compare{suffix}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COMPARE_COLS)
            w.writeheader()
            w.writerows(cmp_rows)
        cons = consensus(cmp_rows)
        with open(GOLD / f"profit_consensus{suffix}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["spawn", "norm", "consensus_h", "spread_pct",
                                              "n_sources", "members", "sources"])
            w.writeheader()
            w.writerows(cons)
        print(f"consensus{suffix or ' ALL'}: rows={len(cmp_rows)} spawns={len(cons)}")
        return cmp_rows, cons

    sprof_all = []
    for p in sorted(GOLD.glob("spawn_profit.csv")):
        with open(p, encoding="utf-8") as f:
            sprof_all.extend(list(csv.DictReader(f)))
    build_consensus(sprof_all, ss_all, "")
    for b in brackets:
        lo, hi = (int(x) for x in b.strip().split("-"))
        tag = f"{lo}_{hi}"
        with open(GOLD / f"spawn_profit_{tag}.csv", encoding="utf-8") as f:
            sp_b = list(csv.DictReader(f))
        with open(GOLD / f"spawn_stats_{tag}.csv", encoding="utf-8") as f:
            ss_b = list(csv.DictReader(f))
        build_consensus(sp_b, ss_b, f"_{tag}", guide_bracket=tag)

    (GOLD / "build_info.json").write_text(
        json.dumps({"date": dt.date.today().isoformat(), "hunts": len(hunts_profit),
                    "hunts_exp": len(hunts_exp),
                    "recent_days": rd_profit, "recent_days_exp": rd_exp,
                    "price_items": len(prices), "spawn_items": len(si),
                    "tagged_items": len(tag_rows),
                    "events_days": len(event_dates), "events_excluded": n_ev,
                    "sessions_le31d": sum(1 for h in hunts_exp if h.get("_days_ago", 9999) <= 31),
                    "sessions_le62d": sum(1 for h in hunts_exp if h.get("_days_ago", 9999) <= 62),
                    "manual_prices": manual}, indent=1), encoding="utf-8")

    # Kopia rankingow do docs/data/ — GitHub Pages serwuje caly folder docs/,
    # wiec dashboard (docs/index.html) czyta te CSV bez zadnego backendu.
    for p in (list(GOLD.glob("ranking_*.csv")) + list(GOLD.glob("spawn_stats*.csv"))
              + list(GOLD.glob("spawn_profit*.csv")) + list(GOLD.glob("profit_compare*.csv"))
              + list(GOLD.glob("profit_consensus*.csv"))
              + [GOLD / "price_stats.csv", GOLD / "spawn_items.csv", GOLD / "hunt_kills_h.csv",
                 GOLD / "item_tags.csv", GOLD / "creature_value.csv", GOLD / "build_info.json"]):
        if p.exists():
            shutil.copy(p, PAGES_DATA / p.name)
    # Szacunki zewnetrzne (poradniki) tez na strone — statyczny plik referencyjny.
    est = ROOT / "research" / "control_estimates.csv"
    if est.exists():
        shutil.copy(est, PAGES_DATA / "control_estimates.csv")
    print(f"copied {len(list(PAGES_DATA.glob('*')))} files -> {PAGES_DATA}")
    try:
        import openpyxl

        wb = openpyxl.Workbook()
        first = True
        for p in sorted(list(GOLD.glob("ranking_*.csv")) + list(GOLD.glob("spawn_stats*.csv"))
                         + list(GOLD.glob("spawn_profit*.csv")) + list(GOLD.glob("profit_compare*.csv"))
                         + list(GOLD.glob("profit_consensus*.csv"))
                         + [GOLD / "price_stats.csv", GOLD / "spawn_items.csv",
                            GOLD / "hunt_kills_h.csv", GOLD / "item_tags.csv",
                            GOLD / "creature_value.csv"]):
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
