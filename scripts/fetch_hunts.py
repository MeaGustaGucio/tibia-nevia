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
import urllib.parse
import urllib.request

from common import ROOT, load_config

BASE = "https://www.hunt-analyser.com"
UA = {"User-Agent": "Mozilla/5.0 (nevia-pipeline/0.1)"}
OUT = ROOT / "data" / "raw"

HUNT_FIELDS = ["id", "url", "spawn", "hunt_date", "duration", "party_size", "party_comp",
               "min_lvl", "max_lvl", "avg_lvl", "has_creature_stats",
               "xp_gain", "raw_xp_gain", "balance", "xp_h", "raw_xp_h", "balance_h",
               "query_min", "query_max", "query_party"]
MEMBER_FIELDS = ["hunt_id", "slot", "name", "voc", "level"]


def get(url: str) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def list_ids(level_min: int, level_max: int, vocations: list, member_counts: list, pages: int) -> list[str]:
    ids: list[str] = []
    for p in range(1, pages + 1):
        q = [("hunt_sessions_by", "is_public"), ("level_min", level_min), ("level_max", level_max),
             ("page", p), ("sort", "session_date_desc")]
        q += [("vocations[]", v) for v in (vocations or [])]
        q += [("member_counts[]", m) for m in (member_counts or [])]
        page = get(f"{BASE}/hunt_sessions?{urllib.parse.urlencode(q)}")
        found = re.findall(r"data-row-click-url-value=\"/hunt_sessions/(\d+)\"", page)
        print(f"list {level_min}-{level_max} {vocations or 'any-voc'} {member_counts or 'any-party'} page={p} ids={len(found)}", flush=True)
        if not found:
            break
        ids.extend(found)
    return sorted(set(ids))


def num(s: str) -> int:
    s = (s or "").replace(",", "").replace(" ", "")
    m = re.search(r"-?\d+", s)
    return int(m.group()) if m else 0


def parse_detail(hid: str, qmin: int, qmax: int, qparty: str) -> tuple[dict, list[dict]]:
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
    # Czesc huntow nie pokazuje skladu niezalogowanym (brak tabeli Party Members).
    # Fallback: rozmiar party z filtra zapytania, lvl = srodek bracketu zapytania.
    size_fallback = {"Solo": 1, "Duo": 2, "x3": 3, "x4": 4, "x5": 5, "x6+": 6}.get(qparty, 0)
    avg_lvl = round(sum(lvls) / len(lvls)) if lvls else ((qmin + qmax) // 2 if qmin and qmax else "")
    hunt = {
        "id": hid,
        "url": f"{BASE}/hunt_sessions/{hid}",
        "spawn": html.unescape(title.group(1).strip()) if title else "",
        "hunt_date": date.group(1) if date else "",
        "duration": field("Session Duration"),
        "party_size": len(members) if members else size_fallback,
        "party_comp": "+".join(f"{x['voc']} {x['level']}" for x in members),
        "min_lvl": min(lvls) if lvls else "",
        "max_lvl": max(lvls) if lvls else "",
        "avg_lvl": avg_lvl,
        "xp_gain": num(field("XP Gain")),
        "raw_xp_gain": num(field("Raw XP Gain")),
        "balance": num(field("Balance")),
        "xp_h": num(field("XP/h")),
        "raw_xp_h": num(field("Raw XP/h")),
        "balance_h": num(field("Balance/h")),
        "query_min": qmin,
        "query_max": qmax,
        "query_party": qparty,
    }
    return hunt, members


def fetch_run(level_min: int, level_max: int, vocations: list, member_counts: list, pages: int):
    """Jeden przebieg: lista id + detale. Zwraca (hunts, members)."""
    ids = list_ids(level_min, level_max, vocations, member_counts, pages)
    qparty = member_counts[0] if len(member_counts) == 1 else ""
    hunts, members = [], []
    for k, hid in enumerate(ids):
        try:
            h, m = parse_detail(hid, level_min, level_max, qparty)
            hunts.append(h)
            members.extend(m)
        except Exception as e:
            print(f"detail failed {hid}: {e}")
        if (k + 1) % 10 == 0:
            print(f"details {k + 1}/{len(ids)}", flush=True)
    return hunts, members


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    ap.add_argument("--level-min", type=int, default=None)
    ap.add_argument("--level-max", type=int, default=None)
    ap.add_argument("--vocations", default=None, help="comma separated, pusty string = wszystkie")
    ap.add_argument("--member-counts", default=None, help="comma separated: Solo,Duo / pusty = wszystkie")
    ap.add_argument("--pages", type=int, default=None)
    ap.add_argument("--no-duo-fallback", action="store_true")
    ap.add_argument("--date", default=None)
    a = ap.parse_args()
    import datetime as dt

    cfg = load_config(pathlib.Path(a.config) if a.config else None)
    day = a.date or dt.date.today().isoformat()
    (OUT / day).mkdir(parents=True, exist_ok=True)

    if a.level_min is not None or a.level_max is not None:
        # Tryb pojedynczego przebiegu (CLI nadpisuje config).
        runs = [{
            "min": a.level_min if a.level_min is not None else 50,
            "max": a.level_max if a.level_max is not None else 300,
            "vocations": [v.strip() for v in a.vocations.split(",") if v.strip()] if a.vocations is not None else ["Druid"],
            "party": [m.strip() for m in a.member_counts.split(",") if m.strip()] if a.member_counts is not None else ["Solo"],
            "pages": a.pages or 3,
        }]
        duo_cfg = None if a.no_duo_fallback else None
    else:
        hcfg = cfg["hunts"]
        runs = []
        for b in hcfg["brackets"]:
            b = dict(b)
            if a.pages:
                b["pages"] = a.pages
            runs.append(b)
        duo_cfg = None if a.no_duo_fallback else hcfg.get("duo")

    all_hunts, all_members = [], []
    for r in runs:
        h, m = fetch_run(r["min"], r["max"], r.get("vocations") or [], r.get("party") or [], r.get("pages", 3))
        all_hunts.extend(h)
        all_members.extend(m)
    if duo_cfg:
        h, m = fetch_run(duo_cfg["min"], duo_cfg["max"], duo_cfg.get("vocations") or [],
                         duo_cfg.get("party") or ["Duo"], duo_cfg.get("pages", 3))
        print(f"narrow={len(all_hunts)} duo widened({duo_cfg['min']}-{duo_cfg['max']})={len(h)}")
        all_hunts.extend(h)
        all_members.extend(m)

    merged_h = {r["id"]: r for r in all_hunts}
    new_ids = set(merged_h)
    merged_m = [m for m in all_members if m["hunt_id"] in new_ids]
    hp, mp = OUT / day / "hunts.csv", OUT / day / "members.csv"
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
