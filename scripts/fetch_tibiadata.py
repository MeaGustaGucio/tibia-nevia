"""Bronze: TibiaData (mirror tibia.com) -> data/raw/<date>/tibiadata_*.json. Stdlib only."""
import datetime as dt
import json
import pathlib
import urllib.request

from common import ROOT, load_config

cfg = load_config()
BASE = "https://api.tibiadata.com/v4"
WORLD = cfg.get("world", "Nevia")
OUT = ROOT / "data" / "raw" / dt.date.today().isoformat()
OUT.mkdir(parents=True, exist_ok=True)

ENDPOINTS = {
    "tibiadata_world": f"{BASE}/world/{WORLD}",
    "tibiadata_killstats": f"{BASE}/killstatistics/{WORLD}",
    "tibiadata_highscores_exp": f"{BASE}/highscores/{WORLD}/experience/all/1",
}


def get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "nevia-pipeline/0.1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


for name, url in ENDPOINTS.items():
    data = get(url)
    (OUT / f"{name}.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
    print(f"saved {name} ({len(json.dumps(data))} chars)")
