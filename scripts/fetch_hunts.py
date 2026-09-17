"""Bronze/silver: hunt-analyser.com public sessions -> data/raw/<date>/hunts.csv + members.csv.

Sterowanie: config.yaml (sekcja hunts). CLI nadpisuje config:
  python scripts/fetch_hunts.py                                # wszystko z configu
  python scripts/fetch_hunts.py --level-min 100 --level-max 200 --pages 1   # pojedynczy przebieg
  python scripts/fetch_hunts.py --config inna-konfiguracja.yaml

Duo na niskich lvlach praktycznie nie istnieje w publicznych danych
(zweryfikowane 16.09.2026: duo 100-130 = 0) — duo idzie z szerszego zakresu
(hunts.duo w configu), a sklad ED+EK filtrujesz po kolumnie party_comp.

Uwaga o loot: rozbicie loota na itemy ("Creature Stats") uzupelnia tylko czesc
graczy (flaga has_creature_stats). Profit: tor 1 = Balance/h (zawsze),
tor 2 = re-wycena po cenach Nevii (etap 2). Stdlib + pyyaml (config).
"""
import argparse
import csv
import html
import pathlib
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from common import ROOT, VOC_NAMES, load_config, parse_duration

BASE = "https://www.hunt-analyser.com"
UA = {"User-Agent": "Mozilla/5.0 (nevia-pipeline/0.1)"}
OUT = ROOT / "data" / "raw"

HUNT_FIELDS = ["id", "url", "spawn", "hunt_date", "duration", "minutes", "party_size", "party_comp",
               "min_lvl", "max_lvl", "avg_lvl", "has_creature_stats",
               "xp_gain", "raw_xp_gain", "balance", "supplies_total", "loot_total",
               "supplies_known", "xp_h", "raw_xp_h", "balance_h", "loot_h",
               "query_min", "query_max", "query_party", "query_search"]
MEMBER_FIELDS = ["hunt_id", "slot", "name", "voc", "voc_name", "level", "supplies", "balance_m"]
KILL_FIELDS = ["hunt_id", "creature", "killed"]


def get(url: str, retries: int = 5) -> str:
    """GET z retry: hunt-analyser resetuje polaczenia przy szybszym scrapowaniu (CI)."""
    last = None
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                time.sleep(0.4)  # lagodniej = mniej resetow
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            last = e
            time.sleep(2 * (a + 1))
    raise last


def list_ids(level_min: int, level_max: int, vocations: list, member_counts: list, pages: int, search: str = "") -> list[str]:
    ids: list[str] = []
    for p in range(1, pages + 1):
        q = [("hunt_sessions_by", "is_public"), ("page", p), ("sort", "session_date_desc")]
        if level_min > 0:
            q.append(("level_min", level_min))
        if level_max > 0:
            q.append(("level_max", level_max))
        if search:
            q.append(("search", search))
        q += [("vocations[]", v) for v in (vocations or [])]
        q += [("member_counts[]", m) for m in (member_counts or [])]
        try:
            page = get(f"{BASE}/hunt_sessions?{urllib.parse.urlencode(q)}")
        except Exception as e:
            print(f"list page={p} FAILED ({e}) — biore co uzbierane ({len(ids)}) i ide dalej")
            break
        found = re.findall(r"data-row-click-url-value=\"/hunt_sessions/(\d+)\"", page)
        tag = f"search={search} " if search else ""
        print(f"list {tag}{level_min}-{level_max} {vocations or 'any-voc'} {member_counts or 'any-party'} page={p} ids={len(found)}", flush=True)
        if not found:
            break
        ids.extend(found)
    return sorted(set(ids))


def num(s: str) -> int:
    s = (s or "").replace(",", "").replace(" ", "")
    m = re.search(r"-?\d+", s)
    return int(m.group()) if m else 0


def parse_detail(hid: str, qmin: int, qmax: int, qparty: str, qsearch: str = "") -> tuple[dict, list[dict], list[dict]]:
    page = get(f"{BASE}/hunt_sessions/{hid}")
    title = re.search(r"<h1[^>]*text-2xl[^>]*>\s*([^<]+)", page)
    date = re.search(r"(\w{3}\s+\d{1,2},\s+\d{4}\s+\d{2}:\d{2})", page)

    def field(label: str) -> str:
        m = re.search(label + r"</p>\s*<p[^>]*>(.*?)</p>", page, re.S)
        return html.unescape(re.sub(r"<[^>]+>", "", m.group(1)).strip()) if m else ""

    members = []
    pm = re.search(r"Party Members</h3>.*?<tbody>(.*?)</tbody>", page, re.S)
    if pm:
        # Wiersz: # | nick (XX lvl) | damage | healing | supplies | balance
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", pm.group(1), re.S):
            tds = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip()
                   for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
            if len(tds) < 6:
                continue
            m = re.match(r"(.+?)\s*\(([A-Z]{2})\s+(\d+)\)", tds[1])
            if not m:
                continue
            members.append({"hunt_id": hid, "slot": len(members) + 1, "name": m.group(1).strip(),
                            "voc": m.group(2), "voc_name": VOC_NAMES.get(m.group(2), m.group(2)),
                            "level": int(m.group(3)), "supplies": num(tds[4]), "balance_m": num(tds[5])})
    if not members:
        # Fallback: sama lista nickow (bez supplies)
        members = [
            {"hunt_id": hid, "slot": i + 1, "name": n.strip(), "voc": v.strip(),
             "voc_name": VOC_NAMES.get(v.strip(), v.strip()), "level": int(lv),
             "supplies": None, "balance_m": None}
            for i, (n, v, lv) in enumerate(re.findall(r"<td[^>]*>\s*([^<(]+?)\s*\(([A-Z]{2})\s+(\d+)\)\s*</td>", page))
        ]
    # Tabela "Monster Killed" (tylko ta sekcja, zeby nie lapac innych obrazkow):
    # <img alt="CREATURE" .../> ... </td><td>COUNT</td>
    kills: list[dict] = []
    mk = page.find("Monster Killed")
    if mk != -1:
        section = page[mk:page.find("</table>", mk) + len("</table>")]
        for alt, cnt in re.findall(
                r"<img alt=\"([^\"]+)\"[^>]*?/>\s*[^<]*?</td>\s*<td[^>]*>\s*([\d, ]+?)\s*</td>", section):
            c = cnt.replace(",", "").replace(" ", "")
            if alt.strip() and c.isdigit():
                kills.append({"hunt_id": hid, "creature": html.unescape(alt.strip()), "killed": int(c)})
    lvls = [m["level"] for m in members]
    # Czesc huntow nie pokazuje skladu niezalogowanym (brak tabeli Party Members).
    # Fallback: rozmiar party z filtra zapytania, lvl = srodek bracketu zapytania.
    size_fallback = {"Solo": 1, "Duo": 2, "x3": 3, "x4": 4, "x5": 5, "x6+": 6}.get(qparty, 0)
    avg_lvl = round(sum(lvls) / len(lvls)) if lvls else ((qmin + qmax) // 2 if qmin and qmax else "")
    mins = parse_duration(field("Session Duration")) or 0
    sup_known = any(m.get("supplies") is not None for m in members)
    # supplies w tabeli sa ujemne (wydatki): loot = balance_sesji + wydatki
    sup_total = -sum(m["supplies"] for m in members if m.get("supplies") not in (None, 0)) if sup_known else 0
    bal_total = num(field("Balance"))
    loot_total = bal_total + sup_total if sup_known else bal_total
    hunt = {
        "id": hid,
        "url": f"{BASE}/hunt_sessions/{hid}",
        "spawn": html.unescape(title.group(1).strip()) if title else "",
        "hunt_date": date.group(1) if date else "",
        "duration": field("Session Duration"),
        "minutes": parse_duration(field("Session Duration")) or "",
        "party_size": len(members) if members else size_fallback,
        "party_comp": "+".join(f"{x['voc']} {x['level']}" for x in members),
        "min_lvl": min(lvls) if lvls else "",
        "max_lvl": max(lvls) if lvls else "",
        "avg_lvl": avg_lvl,
        "has_creature_stats": 1 if kills else 0,
        "xp_gain": num(field("XP Gain")),
        "raw_xp_gain": num(field("Raw XP Gain")),
        "balance": bal_total,
        "supplies_total": sup_total,
        "loot_total": loot_total,
        "supplies_known": 1 if sup_known else 0,
        "xp_h": num(field("XP/h")),
        "raw_xp_h": num(field("Raw XP/h")),
        "balance_h": num(field("Balance/h")),
        "loot_h": round(loot_total / (mins / 60), 0) if mins > 0 else bal_total,
        "query_min": qmin,
        "query_max": qmax,
        "query_party": qparty,
        "query_search": qsearch,
    }
    return hunt, members, kills


def fetch_run(level_min: int, level_max: int, vocations: list, member_counts: list, pages: int, search: str = ""):
    """Jeden przebieg: lista id + detale. Zwraca (hunts, members, kills)."""
    ids = list_ids(level_min, level_max, vocations, member_counts, pages, search)
    qparty = member_counts[0] if len(member_counts) == 1 else ""
    hunts, members, kills = [], [], []
    for k, hid in enumerate(ids):
        try:
            h, m, kl = parse_detail(hid, level_min, level_max, qparty, search)
            hunts.append(h)
            members.extend(m)
            kills.extend(kl)
        except Exception as e:
            print(f"detail failed {hid}: {e}")
        if (k + 1) % 10 == 0:
            print(f"details {k + 1}/{len(ids)}", flush=True)
    return hunts, members, kills


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    ap.add_argument("--level-min", type=int, default=None)
    ap.add_argument("--level-max", type=int, default=None)
    ap.add_argument("--vocations", default=None, help="comma separated, pusty string = wszystkie")
    ap.add_argument("--member-counts", default=None, help="comma separated: Solo,Duo / pusty = wszystkie")
    ap.add_argument("--pages", type=int, default=None)
    ap.add_argument("--search", default=None, help="celowany spawn, np. quara (tryb pojedynczy)")
    ap.add_argument("--no-duo-fallback", action="store_true")
    ap.add_argument("--date", default=None)
    a = ap.parse_args()
    import datetime as dt

    cfg = load_config(pathlib.Path(a.config) if a.config else None)
    day = a.date or dt.date.today().isoformat()
    (OUT / day).mkdir(parents=True, exist_ok=True)

    if a.level_min is not None or a.level_max is not None or a.search:
        # Tryb pojedynczego przebiegu (CLI nadpisuje config; bez duo i targetow).
        single = True
        runs = [{
            "min": a.level_min if a.level_min is not None else 0,
            "max": a.level_max if a.level_max is not None else 0,
            "vocations": [v.strip() for v in a.vocations.split(",") if v.strip()] if a.vocations is not None else [],
            "party": [m.strip() for m in a.member_counts.split(",") if m.strip()] if a.member_counts is not None else [],
            "pages": a.pages or 3,
            "search": a.search or "",
        }]
        duo_cfg = None if a.no_duo_fallback else None
    else:
        single = False
        hcfg = cfg["hunts"]
        runs = []
        for b in hcfg["brackets"]:
            b = dict(b)
            if a.pages:
                b["pages"] = a.pages
            runs.append(b)
        duo_cfg = None if a.no_duo_fallback else hcfg.get("duo")

    all_hunts, all_members, all_kills = [], [], []
    for r in runs:
        h, m, kl = fetch_run(r["min"], r["max"], r.get("vocations") or [], r.get("party") or [],
                             r.get("pages", 3), search=r.get("search", ""))
        all_hunts.extend(h)
        all_members.extend(m)
        all_kills.extend(kl)
    if duo_cfg:
        h, m, kl = fetch_run(duo_cfg["min"], duo_cfg["max"], duo_cfg.get("vocations") or [],
                             duo_cfg.get("party") or ["Duo"], duo_cfg.get("pages", 3))
        print(f"narrow={len(all_hunts)} duo widened({duo_cfg['min']}-{duo_cfg['max']})={len(h)}")
        all_hunts.extend(h)
        all_members.extend(m)
        all_kills.extend(kl)
    # Celowane spawny (search): Twoje expowiska, niezaleznie od bracketu lvl.
    # (Tylko w trybie configu — pojedynczy przebieg CLI ich nie rusza.)
    if not single:
        for t in (cfg["hunts"].get("spawn_targets") or []):
            h, m, kl = fetch_run(0, 0, [], [], t.get("pages", 3), search=t.get("search", ""))
            print(f"target {t.get('search')}: {len(h)} hunts")
            all_hunts.extend(h)
            all_members.extend(m)
            all_kills.extend(kl)

    merged_h = {r["id"]: r for r in all_hunts}
    new_ids = set(merged_h)
    merged_m = [m for m in all_members if m["hunt_id"] in new_ids]
    merged_k = [k for k in all_kills if k["hunt_id"] in new_ids]
    hp, mp, kp = OUT / day / "hunts.csv", OUT / day / "members.csv", OUT / day / "hunt_kills.csv"
    # Tryb pojedynczy DOKLEJA do pliku z danego dnia (dedup po id) — nic nie ginie.
    if single:
        if hp.exists():
            with open(hp, encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    if r["id"] not in merged_h:
                        merged_h[r["id"]] = r
        if mp.exists():
            with open(mp, encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    if r["hunt_id"] not in new_ids:
                        merged_m.append(r)
        if kp.exists():
            with open(kp, encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    if r["hunt_id"] not in new_ids:
                        merged_k.append(r)
        new_ids = set(merged_h)
    with open(hp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HUNT_FIELDS)
        w.writeheader()
        w.writerows(merged_h.values())
    with open(mp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MEMBER_FIELDS)
        w.writeheader()
        w.writerows(merged_m)
    with open(kp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=KILL_FIELDS)
        w.writeheader()
        w.writerows(merged_k)
    print(f"DONE hunts={len(merged_h)} members={len(merged_m)} kills={len(merged_k)} -> {hp}")


if __name__ == "__main__":
    main()
