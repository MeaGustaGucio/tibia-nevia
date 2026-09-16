"""Wspolne: ladowanie config.yaml z domyslnymi wartosciami awaryjnymi."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.yaml"

DEFAULTS = {
    "world": "Nevia",
    "hunts": {
        "brackets": [
            {"min": 50, "max": 100, "vocations": ["Druid"], "party": ["Solo"], "pages": 3},
            {"min": 100, "max": 200, "vocations": ["Druid"], "party": ["Solo"], "pages": 3},
            {"min": 200, "max": 300, "vocations": ["Druid"], "party": ["Solo"], "pages": 3},
        ],
        "duo": {"min": 50, "max": 300, "vocations": [], "party": ["Duo"], "pages": 3},
    },
    "market": {"top_n_history": 150, "history_days": 30},
    "gold": {"recent_days": 90, "brackets": ["50-100", "100-200", "200-300"]},
}


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
