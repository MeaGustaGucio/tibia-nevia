"""Feed eventow 2x exp/loot/skill (wykluczane z median — pompowalyby wyniki).

Zrodlo: archiwum newsow TibiaData (/v4/news/archive) — newsy o double XP/loot
zawsze podaja dokladny okres ("between the server saves of September 4 and
September 7"). Bezposredni kalendarz tibia.com blokuje boty (403).
Reczne daty: config.yaml -> events.extra_dates.
Wyjscie: data/raw/<dzis>/events.json: [{date, name}].
Stdlib + pyyaml.
"""
import datetime as dt
import json
import pathlib
import re
import urllib.request

from common import ROOT, load_config

OUT = ROOT / "data" / "raw" / dt.date.today().isoformat()
OUT.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "nevia-pipeline/0.1"}
API = "https://api.tibiadata.com/v4"
KEYWORDS = ("double xp", "double exp", "double loot", "double skill", "rapid respawn",
            "double experience", "2x xp", "2x exp")
MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"])}


def get(path: str):
    req = urllib.request.Request(API + path, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def daterange(text: str, year: int) -> list:
    """'between the server saves of September 4 and September 7' -> [09-04..09-07].
    Fallback: pojedyncze daty 'September 4' -> ten dzien + weekend (pt-pn)."""
    days: set = set()
    for m in re.finditer(
            r"between the server saves of ([A-Z][a-z]+) (\d{1,2}) and ([A-Z][a-z]+)? ?(\d{1,2})", text):
        m1, d1, m2, d2 = m.group(1).lower(), int(m.group(2)), (m.group(3) or m.group(1)).lower(), int(m.group(4))
        try:
            a, b = dt.date(year, MONTHS[m1], d1), dt.date(year, MONTHS[m2], d2)
        except (KeyError, ValueError):
            continue
        d = a
        while d <= b:
            days.add(d.isoformat())
            d += dt.timedelta(days=1)
    if not days:
        for m in re.finditer(r"(January|February|March|April|May|June|July|August|September|October|November|December) (\d{1,2})", text):
            try:
                days.add(dt.date(year, MONTHS[m.group(1).lower()], int(m.group(2))).isoformat())
            except (KeyError, ValueError):
                pass
    return sorted(days)


def main() -> None:
    cfg = load_config()
    events: dict[str, str] = {}
    archive = []
    for days in (120, 90, 60, 30):
        try:
            archive = get(f"/news/archive/{days}").get("news", [])
            print(f"news archive {days}d: {len(archive)}")
            break
        except Exception as e:
            print(f"archive/{days} failed: {e}")
    cands = [n for n in archive if any(k in f'{n.get("news", "")}'.lower() for k in KEYWORDS)]
    print(f"news: {len(archive)}, kandydaci na event: {len(cands)}")
    for n in cands:
        try:
            full = get(f'/news/id/{n["id"]}')
            content = json.dumps(full)
            year = int(str(n.get("date", "2026"))[:4])
            for d in daterange(content, year):
                events.setdefault(d, str(n.get("news", ""))[:80])
        except Exception as e:
            print(f"news {n.get('id')} failed: {e}")
    for d in (cfg.get("events", {}) or {}).get("extra_dates", []) or []:
        events.setdefault(str(d)[:10], "manual")
    (OUT / "events.json").write_text(
        json.dumps([{"date": d, "name": n} for d, n in sorted(events.items())], indent=1),
        encoding="utf-8")
    print(f"DONE events={len(events)}")


if __name__ == "__main__":
    main()
