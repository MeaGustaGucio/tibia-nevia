"""Wybiera najbardziej substantive komentarze/watki (liczby + znane spawny)."""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1] / "research" / "blocks" / "01_reddit"
SPAWNS = ["quara", "werehyena", "cults", "tiger", "spectre", "vampire", "asura", "demon",
          "roshamuul", "medusa", "lizard", "hero", "banuta", "oramond", "glooth", "lava",
          "reaper", "edron", "darashia", "feyrist", "werelion", "carnivor", "pirate",
          "naga", "falcon", "cobra", "library", "soul war", "ingol", "bashmu", "gazers",
          "burster", "ripper", "werefox", "werebadger", "werebear", "grimvale", "carlin",
          "yalahar", "port hope", "ankrahmun", "krailos", "wreckoning", "nag", "court",
          "ros", "feru", "prison", "catacombs", "wildlife", "corym", "stonerefiner",
          "scarabs", "wyrms", "dragons", "heroes", "tomb", "crypt"]
NUM = re.compile(r"\d[\d.,]*\s*(kk?/h|k/h|k\b|kk\b|gp|gold)", re.I)


def score(text):
    t = text.lower()
    s = sum(1 for sp in SPAWNS if sp in t)
    s += 2 * len(NUM.findall(text))
    s += 1 if re.search(r"\b(1[0-9]{2}|[2-9][0-9]{2}|1000)\b.*\b(lvl|level|ek|ed|rp|ms|ek)\b", t) else 0
    return s


items = []
for line in (ROOT / "posts.jsonl").read_text(encoding="utf-8").splitlines():
    p = json.loads(line)
    body = f"{p.get('title', '')}\n{p.get('selftext', '') or ''}"
    if len(body.strip()) > 80:
        items.append(("POST", p.get("score", 0), p.get("title", ""), body,
                      f"https://www.reddit.com{p.get('permalink', '')}"))
for line in (ROOT / "comments.jsonl").read_text(encoding="utf-8").splitlines():
    c = json.loads(line)
    body = c.get("body", "") or ""
    if len(body) > 120:
        items.append(("COMM", c.get("score", 0), body[:90].replace("\n", " "), body, ""))

ranked = sorted(items, key=lambda x: (score(x[3]), x[1]), reverse=True)
out = []
for kind, sc, title, body, url in ranked[:70]:
    out.append(f"=== [{kind} score={sc}] {title[:100]}")
    out.append(body[:1200])
    if url:
        out.append(url)
    out.append("")
(ROOT / "top_read.txt").write_text("\n".join(out), encoding="utf-8")
print(f"zapisano {len(ranked[:70])} pozycji, max score check OK")
print(f"watki+komcie z score>0 zawierajace liczby: {sum(1 for x in ranked if score(x[3]) >= 3)}")
