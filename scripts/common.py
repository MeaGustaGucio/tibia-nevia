"""Wspolne: ladowanie config.yaml z domyslnymi wartosciami awaryjnymi."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.yaml"

DEFAULTS = {
    "world": "Nevia",
    "hunts": {
        "brackets": [
            {"min": 50, "max": 100, "vocations": [], "party": ["Solo"], "pages": 5},
            {"min": 100, "max": 200, "vocations": [], "party": ["Solo"], "pages": 5},
            {"min": 200, "max": 300, "vocations": [], "party": ["Solo"], "pages": 5},
        ],
        "duo": {"min": 50, "max": 300, "vocations": [], "party": ["Duo"], "pages": 3},
        # Celowane zbiory per spawn (Twoje expowiska): search po nazwie spawna.
        "spawn_targets": [
            {"search": "quara", "pages": 3},
            {"search": "werehyena", "pages": 3},
            {"search": "werelion", "pages": 3},
            {"search": "tiger", "pages": 3},
            {"search": "spectre", "pages": 3},
            {"search": "cults", "pages": 3},
            {"search": "lizard", "pages": 2},
            {"search": "vampire", "pages": 2},
        ],
    },
    "market": {"top_n_history": 150, "history_days": 90},
    "gold": {"recent_days_profit": 60, "recent_days_exp": 365, "brackets": ["50-100", "100-200", "200-300"]},
}

# Kody voc z hunt-analysera. EM = Exalted MONK (nowa voc od 2025) — stad "Party = EM".
# Bonus share liczy rozne voc: 1:+20% 2:+30% 3:+60% 4-5:+100% (Monk to pelnoprawna 5. voc).
VOC_NAMES = {
    "ED": "Elder Druid",
    "EK": "Elite Knight",
    "RP": "Royal Paladin",
    "MS": "Master Sorcerer",
    "EM": "Exalted Monk",
}


def parse_duration(s: str):
    """'01:08h'->68, '00:28h'->28, '1d 02:00h'->1560. None gdy nieparsowalne."""
    import re

    if not s:
        return None
    m = re.match(r"(?:(\d+)\s*d\s*)?(\d+):(\d+)\s*h", s.strip())
    if not m:
        return None
    d, h, mi = (int(x) if x else 0 for x in m.groups())
    return d * 1440 + h * 60 + mi


def load_config(path: pathlib.Path | None = None) -> dict:
    import yaml  # pyyaml, patrz requirements.txt

    cfg = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULTS.items()}
    p = path or CONFIG_PATH
    if p.exists():
        with open(p, encoding="utf-8") as f:
            user = yaml.safe_load(f) or {}
        for k, v in user.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k] = {**cfg[k], **v}
            else:
                cfg[k] = v
    cfg["_path"] = str(p)
    return cfg
