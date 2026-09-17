"""Blok 1b: komentarze do top watkow (score + dyskusja). Wyjscie: comments.jsonl."""
import json
import pathlib
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1] / "research" / "blocks" / "01_reddit"
API = "https://arctic-shift.photon-reddit.com/api"
UA = {"User-Agent": "nevia-research/0.1 (hunting corpus)"}
TOP_N = 60


def get(path, params, retries=4):
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
    return {"data": []}


def main() -> None:
    posts = [json.loads(l) for l in (ROOT / "posts.jsonl").read_text(encoding="utf-8").splitlines()]
    posts.sort(key=lambda p: (p.get("score", 0) or 0) + 2 * (p.get("num_comments", 0) or 0), reverse=True)
    top = posts[:TOP_N]
    print(f"top: {[p['title'][:60] for p in top[:5]]}")
    done = set()
    cf = ROOT / "comments.jsonl"
    if cf.exists():
        for line in cf.read_text(encoding="utf-8").splitlines():
            try:
                done.add(json.loads(line)["link_id"])
            except Exception:
                pass
    out = open(cf, "a", encoding="utf-8")
    n = 0
    for p in top:
        link_id = p["id"] if str(p["id"]).startswith("t3_") else "t3_" + str(p["id"])
        if link_id in done:
            continue
        try:
            data = get("/comments/search", {"link_id": link_id, "sort": "desc", "limit": 25}).get("data", [])
        except Exception:
            continue
        for c in data:
            out.write(json.dumps({k: c.get(k) for k in (
                "id", "link_id", "author", "score", "body", "created_utc", "parent_id")}, ensure_ascii=False) + "\n")
            n += 1
        done.add(link_id)
        print(f"{p['title'][:50]}: {len(data)} kom.", flush=True)
    out.close()
    print(f"DONE komentarze: {n}")


if __name__ == "__main__":
    main()
