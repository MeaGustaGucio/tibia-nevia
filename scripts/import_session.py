"""Import Waszych logow sesji: data/manual/sessions/*.csv -> data/gold/session_loot.csv.

Format (config.yaml -> sessions.schema): spawn,date,minutes,item,count,note
  Cults Yalahar,2026-09-16,68,rope belt,11,wieczorny hunt z bratem
To JEDYNE zrodlo DOKLADNYCH countow loota per sesja (API tego nie daje).
Plik laduje tez na strone (docs/data/session_loot.csv), a formularz w docs/log.html
dopisuje wiersze w tym samym formacie (localStorage + export CSV).
Uruchamiane PRZED build_gold.py (workflow) albo jawnie po dopisaniu logow.
"""
import csv
import glob
import pathlib

from common import ROOT

OUT = ROOT / "data" / "gold" / "session_loot.csv"
FIELDS = ["spawn", "date", "minutes", "item", "count", "note"]


def main() -> None:
    rows: list[dict] = []
    for p in sorted(glob.glob(str(ROOT / "data" / "manual" / "sessions" / "*.csv"))):
        with open(p, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if not (r.get("spawn") and r.get("item")):
                    continue
                rows.append({k: (r.get(k, "") or "").strip() for k in FIELDS})
    seen, uniq = set(), []
    for r in rows:
        key = tuple(r.values())
        if key not in seen:
            seen.add(key)
            uniq.append(r)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(uniq)
    n_sessions = len({(r["spawn"], r["date"], r["minutes"]) for r in uniq})
    print(f"DONE session_loot rows={len(uniq)} sessions~{n_sessions} -> {OUT}")


if __name__ == "__main__":
    main()
