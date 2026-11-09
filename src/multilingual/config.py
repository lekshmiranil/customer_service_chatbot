"""Settings for the multilingual layer. Plain Python, no Streamlit. Every value can be changed in
config\\multilingual_config.json; a missing or broken file falls back to the defaults below."""
import copy
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = ROOT / "config" / "multilingual_config.json"
DEFAULT_DB_PATH = ROOT / "session_data" / "sessions.db"

DEFAULTS = {
    "languages": ["en", "hi", "ml", "ta", "te", "kn"],
    "default_language": "en",
    "session": {
        "inactivity_minutes": 30,
        "restore_window_hours": 24,
        "context_min_turns": 10,
        "store_max_turns": 40,
    },
    "thresholds": {
        "language_confidence": 0.60,
        "intent_confidence": 0.50,
        "intent_margin": 0.15,
        "fuzzy_cutoff": 0.80,
        "followup_max_words": 5,
        "mixed_second_share": 0.25,
        "general_question_min_words": 4,
    },
    "max_requests": 3,
    "intents_need_order": ["order_status", "cancel_order", "refund", "return_exchange", "delivery_issue"],
    "entities": {
        "order_prefixes": ["ORD", "OD", "ODR", "INV", "BKG"],
        "product_prefixes": ["SKU", "PRD", "PROD", "MDL", "CRS"],
    },
}


def _merge(base, extra):
    result = copy.deepcopy(base)
    if not isinstance(extra, dict):
        return result
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _number(value, fallback, minimum=None):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float(fallback)
    if minimum is not None and number < minimum:
        return float(fallback)
    return number


def normalise(cfg):
    """Makes a configuration safe to use: wrong types and impossible values fall back to the defaults."""
    languages = [str(item) for item in (cfg.get("languages") or []) if str(item)]
    cfg["languages"] = languages or list(DEFAULTS["languages"])
    if cfg.get("default_language") not in cfg["languages"]:
        cfg["default_language"] = cfg["languages"][0]
    session, base = cfg["session"], DEFAULTS["session"]
    session["inactivity_minutes"] = _number(session.get("inactivity_minutes"), base["inactivity_minutes"], 0.01)
    session["restore_window_hours"] = _number(session.get("restore_window_hours"), base["restore_window_hours"], 0.0)
    session["context_min_turns"] = int(_number(session.get("context_min_turns"), base["context_min_turns"], 1))
    session["store_max_turns"] = int(max(
        _number(session.get("store_max_turns"), base["store_max_turns"], 1), 2 * session["context_min_turns"]
    ))
    thresholds = cfg["thresholds"]
    for key, default in DEFAULTS["thresholds"].items():
        thresholds[key] = _number(thresholds.get(key), default, 0.0)
    thresholds["followup_max_words"] = int(thresholds["followup_max_words"])
    thresholds["general_question_min_words"] = int(thresholds["general_question_min_words"])
    cfg["max_requests"] = int(_number(cfg.get("max_requests"), DEFAULTS["max_requests"], 1))
    return cfg


def get_config(path=None):
    """The configuration, with the file merged over the defaults. Never raises."""
    target = path or os.getenv("MULTILINGUAL_CONFIG_PATH", "").strip() or str(DEFAULT_CONFIG_PATH)
    data = {}
    try:
        with open(target, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        data = {}
    return normalise(_merge(DEFAULTS, data))


def db_path(path=None):
    return str(path or os.getenv("MULTILINGUAL_DB_PATH", "").strip() or DEFAULT_DB_PATH)