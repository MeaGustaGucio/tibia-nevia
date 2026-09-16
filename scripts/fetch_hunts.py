"""Bronze/silver: hunt-analyser.com public sessions -> data/raw/<date>/hunts.csv + members.csv.

Zakres levelowy jest W PELNI konfigurowalny (domyslnie 50-300, brackety w workflow):
  python scripts/fetch_hunts.py --level-min 50 --level-max 300 --pages 3
  python scripts/fetch_hunts.py --level-min 50 --level-max 100 --vocations Druid --member-counts Solo --pages 3 --append
  python scripts/fetch_hunts.py --level-min 50 --level-max 300 --member-counts Duo --pages 3 --append
  # --append dokleja do hunts.csv z tego samego dnia (dedup po id), zeby workflow
  # mogl przejechac kilka bracketow w jednym runie.

Duo na niskich lvlach praktycznie nie istnieje w publicznych danych
(zweryfikowane 16.09.2026: duo 100-130 = 0, duo 80-150 = 1/strone) — dlatego duo
sciagamy ZAWSZE z szerszego zakresu (--duo-min/--duo-max, default 50-300, bez filtra
voc), a sklad ED+EK filtrujesz potem po kolumnie party_comp.

Uwaga o loot: detal hunta ma Hunt Summary (XP/h, Balance/h) i Party Members, ale
rozbicie loota na itemy ("Creature Stats") jest uzupelniane tylko przez czesc graczy
(brak = flaga has_creature_stats=0). Dlatego profit liczymy dwutorowo, patrz build_gold.py:
  tor 1 (zawsze): Balance/h z hunta jako proxy,
  tor 2 (docelowy): re-wycena loota po cenach Nevii tam gdzie sa dane o dropie.
Stdlib only.
"""
import argparse
import csv
import html
import pathlib
import re
import urllib.parse
import urllib.request

BASE = "https://www.hunt-analyser.com"
UA = {"User-Agent": "Mozilla/5.0 (nevia-pipeline/0.1)"}
OUT = pathlib.Path(__file__).resolve().parents[1] / "data" / "raw"

HUNT_FIELDS = ["id", "url", "spawn", "hunt_date", "duration", "party_size", "party_comp",
               "min_lvl", "max_lvl", "has_creature_stats",
               "xp_gain", "raw_xp_gain", "balance", "xp_h", "raw_xp_h", "balance_h",
               "query_min", "query_max"]
MEMBER_FIELDS = ["hunt_id", "slot", "name", "voc", "level"]


def get(url: str) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def list_ids(level_min: int, level_max: int, vocations: list[str], member_counts: list[str], pages: int) -> list[str]:
    ids: list[str] = []
    for p in range(1, pages + 1):
        q = [("hunt_sessions_by", "is_public"), ("level_min", level_min), ("level_max", level_max),
             ("page", p), ("sort", "session_date_desc")]
        q += [("vocations[]", v) for v in vocations]
        q += [("member_counts[]", m) for m in member_counts]
        page = get(f"{BASE}/hunt_sessions?{urllib.parse.urlencode(q)}")
        found = re.findall(r"data-row-click-url-value=\"/hunt_sessions/(\d+)\"", page)
        print(f"list {level_min}-{level_max} {vocations or 'any-voc'} {member_counts or 'any-party'} page={p} ids={len(found)}")
        if not found:
            break
        ids.extend(found)
    return sorted(set(ids))


def num(s: str) -> int:
    s = (s or "").replace(",", "").replace(" ", "")
    m = re.search(r"-?\d+", s)
    return int(m.group()) if m else 0


def parse_detail(hid: str, qmin: int, qmax: int) -> tuple[dict, list[dict]]:
    page = get(f"{BASE}/hunt_sessions/{hid}")
    title = re.search(r"<h1[^>]*text-2xl[^>]*>\s*([^<]+)", page)
    date = re.search(r"(\w{3}\s+\d{1,2},\s+\d{4}\s+\d{2}:\d{2})", page)

    def field(label: str) -> str:
        m = re.search(label + r"</p>\s*<p[^>]*>(.*?)</p>", page, re.S)
        return html.unescape(re.sub(r"<[^>]+>", "", m.group(1)).strip()) if m else ""

    members = [
        {"hunt_id": hid, "slot": i + 1, "name": n.strip(), "voc": v.strip(), "level": int(lv)}
        for i, (n, v, lv) in enumerate(re.findall(r"<td[^>]*>\s*([^<(]+?)\s*\(([A-Z]{2})\s+(\d+)\)\s*</td>", page))
    ]
    lvls = [m["level"] for m in members]
    hunt = {
        "id": hid,
        "url": f"{BASE}/hunt_sessions/{hid}",
        "spawn": html.unescape(title.group(1).strip()) if title else "",
        "hunt_date": date.group(1) if date else "",
        "duration": field("Session Duration"),
        "party_size": len(members),
        "party_comp": "+".join(f"{x['voc']} {x['level']}" for x in members),
        "min_lvl": min(lvls) if lvls else "",
        "max_lvl": max(lvls) if lvls else "",
        "has_creature_stats": 0 if "Creature Stats - None" in page else 1,
        "xp_gain": num(field("XP Gain")),
        "raw_xp_gain": num(field("Raw XP Gain")),
        "balance": num(field("Balance")),
        "xp_h": num(field("XP/h")),
        "raw_xp_h": num(field("Raw XP/h")),
        "balance_h": num(field("Balance/h")),
        "query_min": qmin,
        "query_max": qmax,
    }
    return hunt, members


def read_existing(path: pathlib.Path, fields: list[str]) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--level-min", type=int, default=50)
    ap.add_argument("--level-max", type=int, default=300)
    ap.add_argument("--vocations", default="Druid", help="comma separated, pusty = wszystkie")
    ap.add_argument("--member-counts", default="Solo", help="comma separated: Solo,Duo / pusty = wszystkie")
    ap.add_argument("--pages", type=int, default=3)
    ap.add_argument("--duo-min", type=int, default=50, help="poszerzony zakres dla Duo")
    ap.add_argument("--duo-max", type=int, default=300)
    ap.add_argument("--no-duo-fallback", action="store_true")
    ap.add_argument("--append", action="store_true", help="doklej do plikow z danego dnia zamiast nadpisywac")
    ap.add_argument("--date", default=None)
    a = ap.parse_args()
    import datetime as dt

    vocs = [v.strip() for v in a.vocations.split(",") if v.strip()]
    mcs = [m.strip() for m in a.member_counts.split(",") if m.strip()]
    day = a.date or dt.date.today().isoformat()
    (OUT / day).mkdir(parents=True, exist_ok=True)

    ids = list_ids(a.level_min, a.level_max, vocs, mcs, a.pages)
    if "Duo" in mcs and not a.no_duo_fallback:
        duo_ids = list_ids(a.duo_min, a.duo_max, [], ["Duo"], a.pages)
        print(f"solo/narrow={len(ids)} duo widened({a.duo_min}-{a.duo_max})={len(duo_ids)}")
        ids += [i for i in duo_ids if i not in ids]
    print(f"unique hunts: {len(ids)}")

    hunts, members = [], []
    for k, hid in enumerate(ids):
        try:
            h, m = parse_detail(hid, a.level_min, a.level_max)
            hunts.append(h)
            members.extend(m)
        except Exception as e:
            print(f"detail failed {hid}: {e}")
        if (k + 1) % 10 == 0:
            print(f"details {k + 1}/{len(ids)}")

    hp, mp = OUT / day / "hunts.csv", OUT / day / "members.csv"
    old_hunts = read_existing(hp, HUNT_FIELDS) if a.append else []
    old_members = read_existing(mp, MEMBER_FIELDS) if a.append else []
    merged_h = {r["id"]: r for r in old_hunts}
    merged_h.update({r["id"]: r for r in hunts})
    keep_mids = set(merged_h)
    merged_m = [r for r in old_members if r["hunt_id"] in keep_mids and r["hunt_id"] not in {h["id"] for h in hunts}]
    merged_m.extend(members)
    with open(hp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HUNT_FIELDS)
        w.writeheader()
        w.writerows(merged_h.values())
    with open(mp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MEMBER_FIELDS)
        w.writeheader()
        w.writerows(merged_m)
    print(f"DONE hunts={len(merged_h)} members={len(merged_m)} -> {hp}")


if __name__ == "__main__":
    main()
