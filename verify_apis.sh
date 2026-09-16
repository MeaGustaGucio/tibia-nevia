#!/usr/bin/env bash
# Linux/macOS/CI — to samo co verify_apis.ps1
set -u
check() { code=$(curl -s -o /dev/null -w "%{http_code}" -A "Mozilla/5.0" "$2"); echo "$1 -> HTTP $code : $2"; }
check "TibiaData world Nevia"           "https://api.tibiadata.com/v4/world/Nevia"
check "TibiaData killstats Nevia"       "https://api.tibiadata.com/v4/killstatistics/Nevia"
check "TibiaData highscores exp"        "https://api.tibiadata.com/v4/highscores/Nevia/experience/all/1"
check "Hunt-analyser lista public"      "https://www.hunt-analyser.com/hunt_sessions?hunt_sessions_by=is_public&page=1"
check "Hunt-analyser filtr 100-130"     "https://www.hunt-analyser.com/hunt_sessions?hunt_sessions_by=is_public&level_min=100&level_max=130&page=1"
check "Hunt-analyser detal (duo ED+EK)" "https://www.hunt-analyser.com/hunt_sessions/57018"
check "Market world_data"               "https://api.tibiamarket.top/world_data"
check "Market Nevia sample"             "https://api.tibiamarket.top/market_values?server=Nevia&limit=3"
check "Market openapi"                  "https://api.tibiamarket.top/openapi.json"
check "tibiaprices (oczekiwane 404)"    "https://tibiaprices.com/"
echo; echo "Nevia w world_data:"; curl -s "https://api.tibiamarket.top/world_data" | grep -o '"name": *"Nevia"[^}]*'
