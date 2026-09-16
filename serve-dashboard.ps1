# Lokalny podglad dashboardu (bez GitHuba).
# file:// nie pozwala stronie czytac CSV (CORS), wiec startujemy mikro-serwer:
#   powershell -ExecutionPolicy Bypass -File serve-dashboard.ps1
# potem otworz http://localhost:8080/
python -m http.server 8080 --directory docs
