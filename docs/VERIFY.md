# Raport weryfikacji API — 16.09.2026, wywołania curl z Windows (curl.exe), bez przeglądarki.
# Ja nie mam przeglądarki — mam tylko fetch HTTP (webfetch) + terminal. Poniższe odtworzysz 1:1 u siebie.

## 1. TibiaData (oficjalny mirror tibia.com, supported fansite, JSON, bez klucza) — DZIAŁA

```powershell
curl.exe -s "https://api.tibiadata.com/v4/world/Nevia"
# -> {"world":{"name":"Nevia","status":"online","players_online":323,...,"pvp_type":"Optional PvP",...}} ✅

curl.exe -s "https://api.tibiadata.com/v4/killstatistics/Nevia"
# -> {"killstatistics":{"world":"Nevia","entries":[{"race":"...","last_day_killed":..,"last_week_killed":..}, ...]}} ✅

curl.exe -s "https://api.tibiadata.com/v4/highscores/Nevia/experience/all/1"
# -> {"highscores":{"world":"Nevia","category":"experience",...,"highscore_list":[{"rank":1,"name":"Ultimate Zoodoo",...,"level":1990}, ...]}} ✅
```

## 2. hunt-analyser.com (promoted fansite) — DZIAŁA, server-rendered HTML

```powershell
curl.exe -s -o NUL -w "%{http_code} %{size_download}`n" -A "Mozilla/5.0" "https://www.hunt-analyser.com/hunt_sessions?hunt_sessions_by=is_public&page=1"
# -> 200 124526 ✅
```

- Filtry istnieją w HTML: `level_min`, `level_max`, `vocations[]`, `member_counts[]`, `sort`, `direction`, paginacja `page=N`.
- Detal `/hunt_sessions/57018` (119 KB) zawiera gotowy dowód na duo:
  `Falcon Castle by Marcelo Almeida, Sep 15 2026, 01:08h, XP Gain 6 991 405, XP/h 6 168 886, Raw XP/h 4 112 731, Balance/h 1 779 810`,
  skład: `Lucius Gelado (ED 536) + Ice Congelante (EK 444)` z osobnym damage/healing/supplies/balance.
- Uwaga: strona główna `/` zwraca pustkę dla prostego curla (prawdopodobnie redirect/Turbo) — wchodzić od razu na `/hunt_sessions?...`.
- Możesz sprawdzić w przeglądarce: https://www.hunt-analyser.com/hunt_sessions?hunt_sessions_by=is_public&level_min=100&level_max=130&page=1

## 3. Ceny Nevia — tibiaprices.com NIE ŻYJE, zamiennik api.tibiamarket.top DZIAŁA

```powershell
curl.exe -s -A "Mozilla/5.0" "https://tibiaprices.com/"
# -> {"status":"error","code":404,"message":"Application not found"} ❌ (projekt skasowany, indeks Google zaległy)

curl.exe -s "https://api.tibiamarket.top/market_values?server=Nevia&limit=3"
# -> [{"id":284,"buy_offer":4,"sell_offer":6,"month_average_sell":5,...,"month_sold":15,...}, ...] ✅
# Pola pokrywają Twój wymóg historii: buy_offer/sell_offer + month_average_* + month_sold/bought + month_highest/lowest + day_*.

curl.exe -s "https://api.tibiamarket.top/item_history?server=Nevia&item_id=284&days=30"
# -> lista snapshotów dziennych (18 KB) ✅ — to jest "ten miesiąc".

curl.exe -s "https://api.tibiamarket.top/item_metadata?item_id=284"
# -> [{"id":284,"category":"Potions","name":"empty potion flask","npc_sell":[],"npc_buy":[...]}] ✅ — mapowanie id->nazwa.

curl.exe -s "https://api.tibiamarket.top/world_data"  # Nevia: last_update 2026-09-14T21:47 ✅ (świeże, 2 dni)
```

Endpointy (z `/openapi.json`): `/market_values`, `/item_history`, `/item_metadata`, `/item_activity`, `/item_comparison`, `/market_board`, `/world_data`, `/events`.
API docs (Swagger UI, wymaga JS w przeglądarce): https://api.tibiamarket.top/docs

## 4. Twoje ceny Rope Belt — jak się mają do pipeline

Nie da się ich porównać 1:1 z trackerem bez mapowania `Rope Belt -> item_id` (metadata nie była jeszcze przeszukana pod tę nazwę).
Twoje liczby (`sell 4991-6400 / buy 4280-4526`) są spójne z modelem trackera (`sell_offer/buy_offer` + miesięczne min/max/avg).
W pipeline Twoje ręczne ceny lądują w `data/manual/rope-belt-nevia.csv` jako ground truth i nadpisują tracker przy re-wycenie (tryb `instant=buy_offer`).
