# PowerShell (Windows) — weryfikacja API bez instalowania czegokolwiek.
# Uruchom: powershell -ExecutionPolicy Bypass -File verify_apis.ps1
$ErrorActionPreference = "Continue"
function Check($name, $url) {
  $code = curl.exe -s -o NUL -w "%{http_code}" -A "Mozilla/5.0" $url
  Write-Output "$name -> HTTP $code : $url"
}
Check "TibiaData world Nevia"        "https://api.tibiadata.com/v4/world/Nevia"
Check "TibiaData killstats Nevia"    "https://api.tibiadata.com/v4/killstatistics/Nevia"
Check "TibiaData highscores exp"     "https://api.tibiadata.com/v4/highscores/Nevia/experience/all/1"
Check "Hunt-analyser lista public"   "https://www.hunt-analyser.com/hunt_sessions?hunt_sessions_by=is_public&page=1"
Check "Hunt-analyser filtr 100-130"  "https://www.hunt-analyser.com/hunt_sessions?hunt_sessions_by=is_public&level_min=100&level_max=130&page=1"
Check "Hunt-analyser detal (duo ED+EK)" "https://www.hunt-analyser.com/hunt_sessions/57018"
Check "Market world_data (Nevia?)"   "https://api.tibiamarket.top/world_data"
Check "Market Nevia sample"          "https://api.tibiamarket.top/market_values?server=Nevia&limit=3"
Check "Market openapi (endpoints)"   "https://api.tibiamarket.top/openapi.json"
Check "tibiaprices (oczekiwane 404)" "https://tibiaprices.com/"
Write-Output ""
Write-Output "Podglad Nevia world_data (szukaj Nevia + last_update):"
curl.exe -s "https://api.tibiamarket.top/world_data" | Select-String -Pattern "Nevia" -Context 0,1
Write-Output ""
Write-Output "Podglad TibiaData world (pierwsze 400 znakow):"
$r = curl.exe -s "https://api.tibiadata.com/v4/world/Nevia"
$r.Substring(0, [Math]::Min(400, $r.Length))
