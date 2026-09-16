# Tibia Nevia pipeline (114 ED + EK duo) — $0: GitHub Actions + Pages + R2

## Zweryfikowane źródła (16.09.2026, live curlami z tego komputera)

| Dane | Źródło | Status |
|---|---|---|
| World Nevia (online, gracze) | `api.tibiadata.com/v4/world/Nevia` | ✅ 200, JSON bez klucza |
| Kill statistics Nevia (co się bije, day/week) | `api.tibiadata.com/v4/killstatistics/Nevia` | ✅ 200 |
| Highscores exp Nevia | `api.tibiadata.com/v4/highscores/Nevia/experience/all/1` | ✅ 200 |
| Publiczne hunty + filtry lvl/voc/party | `hunt-analyser.com/hunt_sessions?...` | ✅ 200, HTML server-rendered, parsowalne (potwierdzony detal `/hunt_sessions/57018`: `Falcon Castle`, `XP/h 6 168 886`, `Balance/h 1 779 810`, skład `ED 536 + EK 444` — czyli **duo stats istnieją**) |
| Ceny Nevia dzienne + miesięczne | `api.tibiamarket.top/market_values?server=Nevia`, `/item_history?server=Nevia&item_id=..&days=30`, `/item_metadata`, `/world_data` | ✅ 200. Nevia `last_update 2026-09-14` (2 dni temu) |
| `tibiaprices.com` | ❌ MARTWE — `404 {"message":"Application not found"}`. Indeks Google nieaktualny. Nie używać. |

Szczegół: patrz `docs/VERIFY.md`. Szybki test: uruchom `verify_apis.ps1` (Windows) lub `verify_apis.sh` (Linux/macOS/CI).

## Struktura

```
tibia-nevia-pipeline/
  verify_apis.ps1 / .sh     # curle do samodzielnej weryfikacji (Ty też możesz odpalić)
  scripts/
    fetch_tibiadata.py      # bronze: world + killstats + highscores Nevia -> data/raw/<data>/
    fetch_market.py         # bronze: Nevia market_values + item_history + metadata
    fetch_hunts.py          # bronze/silver: hunt-analyser lista 100-130 ED solo + ED+EK duo + detale -> hunts.csv/members.csv
    build_gold.py           # gold: rankingi EXP/h i profit/h + export CSV/XLSX (docs/dashboard)
  data/
    manual/rope-belt-nevia.csv  # Twoje live ceny z gry = ground truth (seed)
    raw/<YYYY-MM-DD>/           # zrzuty z Actions (commitowane do repo)
    gold/                       # ranking_exp.csv, ranking_profit.csv, dashboard.xlsx
  docs/VERIFY.md            # pełny raport weryfikacji
  .github/workflows/daily.yml   # cron 05:00 UTC: fetch -> build -> commit (+ opcjonalny upload R2)
```

## Profit/h — metodologia (Twoje pytanie o 10x drogi vs 1000x tani)

`profit/h Nevia = sum(drop_count/h * nevia_price) - supplies/h`.
`Balance` z hunta NIE wystarcza (policzone po cenach z czasu/innego świata), więc:

1. `fetch_hunts.py` bierze z detalu: `spawn, XP/h, Raw XP/h, Balance/h, duration, party (ED x + EK y)`.
2. `fetch_market.py` bierze ceny Nevii: do szybkiej sprzedaży użyj `buy_offer` (Twój Rope Belt: 4526), do cierpliwej `month_average_sell`. Tracker daje oba + `day_*` i `month_*`.
3. `build_gold.py` joinuje i przewartościowuje. Etap 2 (pełny rozkład `hunt_loot(item, count)`) wymaga doparsowania zakładek `Members Details` w detalu hunta — zostawione jako następny krok, bo lista+summary już dają ranking EXP/h i orientacyjny profit/h.

## Uruchomienie lokalne / CI (zakres 50-300, rozszerzalny)

```powershell
# 1. weryfikacja (Ty też tak możesz):
powershell -ExecutionPolicy Bypass -File verify_apis.ps1
# 2. ETL — kazdy bracket dokleja (--append) do hunts.csv z danego dnia:
pip install -r requirements.txt
python scripts/fetch_tibiadata.py
python scripts/fetch_market.py                       # WSZYSTKIE itemy Nevii (paginacja), TOP_N_HISTORY (default 60, env) z historia 30d
python scripts/fetch_hunts.py --level-min 50 --level-max 100 --vocations Druid --member-counts Solo --pages 3
python scripts/fetch_hunts.py --level-min 100 --level-max 200 --vocations Druid --member-counts Solo --pages 3 --append
python scripts/fetch_hunts.py --level-min 200 --level-max 300 --vocations Druid --member-counts Solo --pages 3 --append
python scripts/fetch_hunts.py --level-min 50 --level-max 300 --vocations "" --member-counts Duo --pages 3 --append
python scripts/build_gold.py --recent-days 90        # ranking_exp[_50_100...].csv + ranking_profit*.csv + dashboard.xlsx
```

Jak rozszerzyć: dopisz bracket (`--level-min 300 --level-max 500 --append`), zwieksz `--pages`,
ustaw `TOP_N_HISTORY=300` dla historii cen wiekszosci loota, zmien `--recent-days 30` po patchach.
`--vocations ""` = wszystkie voc, `--member-counts "Solo,Duo"` = oba naraz.

## Gdzie to stoi online?

Domyslnie NIGDZIE — pipeline zyje w tym folderze. Zeby byl online + sam sie odpalal codziennie:
1. `gh auth login` (jednorazowo, Twoje konto GitHub),
2. `git init` jest juz zrobiony w tym folderze — wykonaj ponizsze, a Actions ruszy samo:

```powershell
cd tibia-nevia-pipeline
gh repo create tibia-nevia --public --source=. --push
# od tej pory: Actions (zakladka Actions na github.com) robi cron 05:00 UTC,
# dane ladują w data/raw/<data>/, rankingi w data/gold/, a dashboard.xlsx sciagasz z repo.
# Podglad online bez sciagania: GitHub Pages (Settings -> Pages -> Deploy from branch, /docs)
# lub Streamlit Community Cloud podpięty pod data/gold/*.csv — oba za $0.
```

## Koszt: $0

Publiczne repo GitHub = nielimitowane minuty Actions. R2 (10 GB free, zero egress) opcjonalne jako druga kopia zrzutów — secrets `R2_*` nie są wymagane do startu.
