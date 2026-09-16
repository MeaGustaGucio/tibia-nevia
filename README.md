# Tibia Nevia pipeline (ED + EK duo, zakres 50-300) — $0: GitHub Actions + Pages

## Zrodla (zweryfikowane 16.09.2026 live curlami z tego komputera)

| Dane | Zrodlo | Status |
|---|---|---|
| World Nevia (online, gracze) | `api.tibiadata.com/v4/world/Nevia` | OK 200, JSON bez klucza |
| Kill statistics Nevia (co sie bije, day/week) | `api.tibiadata.com/v4/killstatistics/Nevia` | OK 200 |
| Highscores exp Nevia | `api.tibiadata.com/v4/highscores/Nevia/experience/all/1` | OK 200 |
| Publiczne hunty + filtry lvl/voc/party | `hunt-analyser.com/hunt_sessions?...` | OK 200, HTML parsowalne; detal `/hunt_sessions/57018`: Falcon Castle, XP/h 6 168 886, sklad ED 536 + EK 444 (duo stats istnieja) |
| Ceny Nevia dzienne + miesieczne | `api.tibiamarket.top/market_values?server=Nevia`, `/item_history`, `/item_metadata`, `/world_data` | OK 200; Nevia last_update 2026-09-14 |
| `tibiaprices.com` | MARTWE — `404 Application not found`. Nie uzywac. |

Szczegol: `docs/VERIFY.md`. Szybki test: `verify_apis.ps1` (Windows) lub `verify_apis.sh`.

## Struktura

```
tibia-nevia-pipeline/
  config.yaml               # JEDYNE miejsce konfiguracji: brackety lvl, voc, pages, recent_days, top_n, historia
  verify_apis.ps1 / .sh     # curle do samodzielnej weryfikacji
  scripts/
    common.py               # ladowanie config.yaml
    fetch_tibiadata.py      # bronze: world + killstatistics + highscores Nevia -> data/raw/<data>/
    fetch_market.py         # bronze: WSZYSTKIE itemy Nevii (market_values) + historia 30d dla top-N + metadata
    fetch_hunts.py          # bronze/silver: brackety z configu + duo z poszerzonego zakresu -> hunts.csv/members.csv
    build_gold.py           # gold: rankingi EXP/h i profit/h (overall + per bracket) + kopia do docs/data/
  data/
    manual/*.csv            # Twoje live ceny z gry = ground truth, nadpisuja tracker (wzor: rope-belt-nevia.csv)
    raw/<YYYY-MM-DD>/       # zrzuty z Actions (commitowane do repo)
    gold/                   # ranking_exp[_<bracket>].csv, ranking_profit[_<bracket>].csv, dashboard.xlsx
  docs/                     # FRONTEND (GitHub Pages serwuje ten folder)
    index.html + app.js     # dashboard: bracket / EXP-profit toggle / solo-duo / szukaj + wykres top 15
    data/                   # kopia rankingow (uzupelniana przez build_gold.py)
    VERIFY.md               # pelny raport weryfikacji zrodel
  serve-dashboard.ps1       # lokalny podglad dashboardu: odpal i otworz http://localhost:8080/
  .github/workflows/daily.yml   # cron 05:00 UTC: fetch -> build -> commit
```

## Profit/h — metodologia (10x drogi vs 1000x tani przedmiot)

`profit/h Nevia = sum(drop_count/h * nevia_price) - supplies/h`.
`Balance` z hunta NIE wystarcza (policzone po cenach z czasu/innego swiata), wiec:

1. `fetch_hunts.py` bierze z detalu: `spawn, XP/h, Raw XP/h, Balance/h, duration, party (ED x + EK y)` + flage `has_creature_stats` (rozbicie loota uzupelnia tylko czesc graczy).
2. `fetch_market.py` bierze ceny Nevii: szybka sprzedaz = `buy_offer` (Twoj Rope Belt: 4526), cierpliwa = `month_average_sell` (+ `day_*`, `month_*`).
3. `build_gold.py` daje rankingi; pelna re-wycena `drop/h x cena Nevii` (etap 2) wlaczy sie na podzbiorze z `has_creature_stats=1`.

## Uruchomienie lokalne / CI — wszystko z config.yaml

```powershell
pip install -r requirements.txt
powershell -ExecutionPolicy Bypass -File verify_apis.ps1  # szybki test zrodel
python scripts/fetch_tibiadata.py   # world/killstats/highscores Nevia
python scripts/fetch_market.py      # wszystkie itemy + historia (top_n z configu)
python scripts/fetch_hunts.py       # brackety + duo z configu
python scripts/build_gold.py        # rankingi + dashboard.xlsx + kopia do docs/data/
powershell -ExecutionPolicy Bypass -File serve-dashboard.ps1  # podglad: http://localhost:8080/
```

Jak zwezic/rozszerzyc: edytuj `config.yaml` (brackety, `pages`, `recent_days`, `top_n_history`,
`history_days`) albo nadpisz jednorazowo z CLI, np.
`python scripts/fetch_hunts.py --level-min 300 --level-max 500 --pages 2`.
Czestotliwosc: tylko w `.github/workflows/daily.yml`, linia `cron: "0 5 * * *"`.

## Gdzie to stoi online? + GitHub auth

Domyslnie NIGDZIE — pipeline zyje w tym folderze (git lokalny juz jest).
**Nie podawaj mi zadnych loginow/hasel/tokenow.** Bezpieczna sciezka (3 komendy u Ciebie):

```powershell
cd tibia-nevia-pipeline
gh auth login                                        # logowanie na TWOIM koncie, w Twoim terminalu
gh repo create tibia-nevia --public --source=. --push   # public = za darmo Actions + Pages
```

Dlaczego public a nie private: na darmowym koncie GitHub **Pages dziala tylko z publicznym repo**
(private wymaga platnego planu), a w tych danych nie ma nic wrazliwego (publiczne statystyki
gry + publiczne ceny marketu). Prywatne repo tez zadziala z Actions, ale wtedy dashboard
ogladalbys lokalnie przez `serve-dashboard.ps1`.

Po pushu, zeby wizualizacje byly pod `https://TWOJ-NICK.github.io/tibia-nevia/`:
repo na github.com → Settings → Pages → Deploy from branch → branch `main`, folder `/docs`.
Darmowej *wlasnej* domeny (typu .tk/.ml) juz nie ma — padly lata temu; realne $0 to subdomeny
`github.io / pages.dev / streamlit.app`. Wlasna domena to ~50 zl/rok, podepniesz ja pozniej
jednym wpisem DNS w Pages.

## Koszt: $0

Publiczne repo GitHub = nielimitowane minuty Actions (daily run to ~5 min). R2 (10 GB free,
zero egress) opcjonalne jako druga kopia zrzutow — secrety `R2_*` nie sa wymagane do startu.
