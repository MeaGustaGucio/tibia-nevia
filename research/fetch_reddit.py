"""Blok 1 korpusu: r/TibiaMMO (+ poboczne) przez Arctic Shift API (publiczne, bez klucza).

Wyszukuje watki 2026 po tematach (hunting/profit/duo/...), paginuje do limitu,
dociaga top komentarze per watek. Resume po plikach (urls.jsonl per query).
Wyjscie: research/blocks/01_reddit/{posts.jsonl, comments.jsonl, urls.txt}
Stdlib only. Delikatnie: 0.5 s miedzy requestami.
"""
import datetime as dt
import json
import pathlib
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1] / "research" / "blocks" / "01_reddit"
ROOT.mkdir(parents=True, exist_ok=True)
API = "https://arctic-shift.photon-reddit.com/api"
UA = {"User-Agent": "nevia-research/0.1 (hunting corpus)"}
AFTER = "2026-01-01"

QUERIES = [
    "hunting spot level", "where to hunt", "best exp", "exp per hour",
    "best profit", "profit per hour", "money making", "duo hunt",
    "ek hunting", "druid hunting", "paladin hunting", "monk hunting",
    "imbuement cost", "market price", "nerf rebalance patch",
    "werehyena quara spectre cults", "mana leech void", "vampirism",
    "delivery task", "prey system", "hazard gnomprona", "boosted creature",
]
SUBS = ["TibiaMMO"]
SMALL_SUBS = ["TibiaMMO_Spanish", "rookgaard", "SolvingTibia"]


def get(path: str, params: dict, retries: int = 4):
    url = f"{API}{path}?{urllib.parse.urlencode(params)}"
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                time.sleep(0.5)
                return json.loads(r.read().decode())
        except Exception as e:
            print(f"retry {a + 1}: {e}")
            time.sleep(3 * (a + 1))
    raise RuntimeError(f"FAILED {path} {params}")


def main() -> None:
    seen: set = set()
    up = ROOT / "posts.jsonl"
    if up.exists():
        for line in up.read_text(encoding="utf-8").splitlines():
            try:
                seen.add(json.loads(line)["id"])
            except Exception:
                pass
    print(f"znane watki: {len(seen)}")
    out = open(up, "a", encoding="utf-8")
    urls = open(ROOT / "urls.txt", "a", encoding="utf-8")
    total_new = 0
    for sub in SUBS:
        for q in QUERIES:
            after = None
            # paginacja wstecz po created_utc (API: sort=desc, before=)
            params = {"subreddit": sub, "query": q, "after": AFTER,
                      "sort": "desc", "limit": 100}
            for _ in range(5):  # max 500 na query (wystarczy z zapasem)
                if after:
                    params["before"] = after
                try:
                    data = get("/posts/search", params).get("data", [])
                except RuntimeError:
                    break
                if not data:
                    break
                for p in data:
                    if p.get("id") in seen:
                        continue
                    seen.add(p["id"])
                    keep = {k: p.get(k) for k in (
                        "id", "title", "selftext", "author", "score", "num_comments",
                        "created_utc", "permalink", "link_flair_text", "subreddit")}
                    out.write(json.dumps(keep, ensure_ascii=False) + "\n")
                    urls.write(f"https://www.reddit.com{p.get('permalink', '')}\n")
                    total_new += 1
                after = min(p.get("created_utc", 0) for p in data)
                if len(data) < 100:
                    break
            print(f"{sub} | {q}: +{total_new} (razem {len(seen)})", flush=True)
    out.close()
    urls.close()
    # dedup urls.txt
    lines = sorted(set(ROOT.joinpath("urls.txt").read_text(encoding="utf-8").splitlines()))
    ROOT.joinpath("urls.txt").write_text("\n".join(l for l in lines if l.strip()) + "\n", encoding="utf-8")
    print(f"DONE watki razem: {len(seen)}, nowe w tym runie: {total_new}")


if __name__ == "__main__":
    main()
