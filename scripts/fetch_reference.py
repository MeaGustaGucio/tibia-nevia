"""Dane referencyjne POPYTU (rzadko zmieniane, wersjonowane w repo):
1. imbuing_items.csv — materialy do imbuementow (zrodlo: TibiaWiki/Fandom API, strona Imbuing).
   Np. Vampire Teeth -> Powerful Vampirism 25x; Rope Belt -> Powerful Void 25x.
2. delivery_items.csv — weekly/daily delivery (zrodlo: community Google Sheet, export CSV).
   Kolumny: item, creatures (dropi z), npc, npc_price, qty.
3. delivery_npc.csv — j.w. z TibiaPal (/deliveries, tabele per NPC: cena NPC + band rynkowy).
Uruchamiane recznie przy zmianach w grze (nie codziennie).
Stdlib only.
"""
import csv
import json
import pathlib
import re
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
REF = ROOT / "data" / "reference"
REF.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (nevia-pipeline/0.1)"}


def get(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_imbuing() -> list[dict]:
    url = ("https://tibia.fandom.com/api.php?action=query&titles=Imbuing"
           "&prop=revisions&rvprop=content&format=json")
    data = json.loads(get(url).decode("utf-8"))
    pages = data.get("query", {}).get("pages", {})
    text = next(iter(pages.values()))["revisions"][0]["*"]
    rows = []
    # Wiersz tabeli: | [[Basic Void]]\n| '''3%'''\n| 25 [[Rope Belt]]s, ...\n| ...
    for m in re.finditer(
            r"\|\s*\[\[(Basic|Intricate|Powerful)\s+([^\]|]+)(?:\|[^\]]+)?\]\][^\n]*\n"
            r"\|[^\n]*\n\|\s*([^\n]+)", text):
        tier, base, sources = m.group(1), m.group(2).strip(), m.group(3)
        for qty, item in re.findall(r"(\d+)\s*\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", sources):
            rows.append({"item": item.strip(), "imbuement": base,
                         "tier": tier, "qty": int(qty)})
    # dedup
    seen, out = set(), []
    for r in rows:
        k = (r["item"], r["imbuement"], r["tier"])
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def fetch_delivery_sheet() -> list[dict]:
    url = ("https://docs.google.com/spreadsheets/d/"
           "1Q5tnOMLzNpxmMtiicxArBAicAgwJ6syUok0rygYDM4s/export?format=csv")
    text = get(url).decode("utf-8", "replace")
    rows = []
    for r in csv.DictReader(text.splitlines()):
        if not (r.get("Item") or "").strip():
            continue
        price = re.sub(r"[^\d]", "", r.get("Preço", "") or "")
        rows.append({"item": r["Item"].strip(), "creatures": (r.get("Dropa de") or "").strip(),
                     "npc": (r.get("Vende Para") or "").strip(),
                     "npc_price": int(price) if price else "",
                     "qty": (r.get("Quantidade aproximada") or "").strip()})
    return rows


def fetch_tibiapal() -> list[dict]:
    html = get("https://tibiapal.com/deliveries", timeout=90).decode("utf-8", "replace")
    rows = []
    parts = re.split(r'<div id="(RashidTab|Djinn|Yasir|Telas|Gladys|Esrik|Flint|Others|Everything)"', html)
    # parts: [pre, tab1, body1, tab2, body2, ...]
    for i in range(1, len(parts) - 1, 2):
        npc, body = parts[i], parts[i + 1]
        for m in re.finditer(
                r"<td><a[^>]*>([^<]+)</a></td>\s*<td>([\d\s]+)</td>\s*<td[^>]*><b>(\w+(?: \w+)?)</b>",
                body):
            rows.append({"item": m.group(1).strip(), "npc": npc,
                         "npc_price": int(m.group(2).replace(" ", "")),
                         "market_band": m.group(3).strip()})
    return rows


def write(name: str, rows: list[dict], fields: list[str]):
    with open(REF / name, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"{name}: {len(rows)} rows")


def main() -> None:
    imb = fetch_imbuing()
    write("imbuing_items.csv", imb, ["item", "imbuement", "tier", "qty"])
    dsheet = fetch_delivery_sheet()
    write("delivery_items.csv", dsheet, ["item", "creatures", "npc", "npc_price", "qty"])
    try:
        tpal = fetch_tibiapal()
        write("delivery_npc.csv", tpal, ["item", "npc", "npc_price", "market_band"])
    except Exception as e:
        print(f"tibiapal failed (niekrytyczne): {e}")


if __name__ == "__main__":
    main()
