"""One-off: dokoncz metadata dla top-N (krotki run, resume z dysku)."""
import json
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import ROOT, load_config

cfg = load_config()
API = "https://api.tibiamarket.top"
OUT = ROOT / "data" / "raw" / "2026-09-16"
vals = json.loads((OUT / "market_values_nevia.json").read_text(encoding="utf-8"))
top_n = int(cfg.get("market", {}).get("top_n_history", 150))
ranked = sorted(vals, key=lambda r: (r.get("month_sold", 0) or 0) + (r.get("month_bought", 0) or 0), reverse=True)
top_ids = [r["id"] for r in ranked[:top_n] if r.get("id")]
meta_path = OUT / "market_metadata_top.json"
meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
todo = [i for i in top_ids if str(i) not in meta]
print(f"metadata todo={len(todo)}", flush=True)


def get(item_id, retries=5):
    url = f"{API}/item_metadata?{urllib.parse.urlencode({'item_id': item_id})}"
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "nevia-pipeline/0.1"})
            with urllib.request.urlopen(req, timeout=30) as r:
                time.sleep(0.5)
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429 and a < retries - 1:
                time.sleep(4 * (a + 1))
                continue
            raise


for i, item_id in enumerate(todo):
    try:
        meta[str(item_id)] = get(item_id)
    except Exception as e:
        print(f"failed {item_id}: {e}", flush=True)
    if (i + 1) % 10 == 0:
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
        print(f"{i + 1}/{len(todo)}", flush=True)
meta_path.write_text(json.dumps(meta), encoding="utf-8")
print(f"DONE metadata={len(meta)}", flush=True)
