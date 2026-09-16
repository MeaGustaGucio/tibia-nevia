"""Cache potworow z TibiaData (mirror tibia.com): exp + loot_list per creature.

Wejscie: data/raw/*/hunt_kills.csv (unia nazw). Wyjscie: data/raw/<dzis>/creatures.json:
  {name: {experience_points, loot_list, ...}} + data/raw/<dzis>/creatures_missing.txt
Resume: istniejacy cache z poprzednich dni jest doczytywany (nie bombardujemy API).
Stdlib + pyyaml (config).
"""
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


def get_creature(name: str, retries: int = 4):
    url = "https://api.tibiadata.com/v4/creature/" + urllib.parse.quote(name)
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                time.sleep(0.4)
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (404, 400):
                return None  # brak takiej rasy w API (np. zla odmiana nazwy)
            if e.code == 502:
                # TibiaData 502 = padl scrap tej rasy; uporczywe i zwykle stale.
                # Jedna szybka proba i odpuszczamy (nazwa laduje w rejestrze).
                if a >= 1:
                    return "GIVEUP"
                time.sleep(3)
                continue
            if a < retries - 1:
                time.sleep(3 * (a + 1))
                continue
            raise


def main() -> None:
    names: set[str] = set()
    for p in glob.glob(str(ROOT / "data" / "raw" / "*" / "hunt_kills.csv")):
        with open(p, encoding="utf-8") as f:
            import csv
            for row in csv.DictReader(f):
                if row.get("creature"):
                    names.add(row["creature"].strip())
    print(f"creatures in kills: {len(names)}")

    # cache z poprzednich dni (resume)
    cache: dict = {}
    for p in sorted(glob.glob(str(ROOT / "data" / "raw" / "*" / "creatures.json"))):
        try:
            cache.update(json.loads(pathlib.Path(p).read_text(encoding="utf-8")))
        except Exception:
            pass
    todo = sorted(n for n in names if n not in cache)
    print(f"cached={len(cache)} todo={len(todo)}")
    # Rejestr trwale-blednych nazw (globalny, nie per-dzien): nie meczymy API w kolko.
    # Ponawiamy tylko jesli ostatnia proba starsza niz 7 dni.
    failed_path = ROOT / "data" / "raw" / "creatures_failed.json"
    failed: dict = {}
    if failed_path.exists():
        try:
            failed = json.loads(failed_path.read_text(encoding="utf-8"))
        except Exception:
            failed = {}
    today = dt.date.today().isoformat()
    fresh_fail = {n for n, d in failed.items()
                  if (dt.date.today() - dt.date.fromisoformat(d)).days < 7} if failed else set()
    todo = [n for n in todo if n not in fresh_fail]
    print(f"skip fresh-failed={len(fresh_fail & set(names))}, real todo={len(todo)}")
    missing = []
    for i, name in enumerate(todo):
        try:
            data = get_creature(name)
            if data == "GIVEUP" or data is None:
                missing.append(name)
                failed[name] = today
            elif data.get("creature"):
                c = data["creature"]
                cache[name] = {"experience_points": c.get("experience_points"),
                               "loot_list": c.get("loot_list") or [],
                               "hitpoints": c.get("hitpoints")}
            else:
                missing.append(name)
                failed[name] = today
        except Exception as e:
            print(f"creature failed {name}: {e}")
            missing.append(name)
            failed[name] = today
        if (i + 1) % 25 == 0:
            (OUT / "creatures.json").write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
            failed_path.write_text(json.dumps(failed, ensure_ascii=False), encoding="utf-8")
            print(f"creatures {i + 1}/{len(todo)} (flush)", flush=True)
    (OUT / "creatures.json").write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    (OUT / "creatures_missing.txt").write_text("\n".join(sorted(set(missing))), encoding="utf-8")
    failed_path.write_text(json.dumps(failed, ensure_ascii=False), encoding="utf-8")
    with_loot = sum(1 for v in cache.values() if v.get("loot_list"))
    print(f"DONE creatures={len(cache)} with_loot={with_loot} missing={len(set(missing))}")


if __name__ == "__main__":
    main()
