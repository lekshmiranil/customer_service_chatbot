"""Ticket workflow configuration (Task 3).

One JSON file holds every business rule the ticket workflow uses: timezone, business
hours, holidays, SLA targets, priority points, routing teams and agents, mandatory
fields and duplicate thresholds. The file is read on every get_config() call and the
parsed result is reused only while the file content is unchanged, so an edit takes
effect on the next call without restarting the app. A broken edit never takes the
workflow down: the last good configuration stays active and the problem is reported
by last_config_error().
"""
import copy
import hashlib
import json
import os
import threading
from datetime import date, time
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "ticket_config.json"

PRIORITY_LEVELS = ("low", "medium", "high", "critical")
SEVERITIES = ("low", "medium", "high", "critical")
BASES = ("business", "calendar")
AFTER_HOURS_POLICIES = ("queue_until_open", "route_anyway")
MANDATORY_FIELD_NAMES = (
    "customer_name",
    "customer_id",
    "contact",
    "order_id",
    "product",
    "issue_description",
)

DEFAULT_CONFIG = {
    "timezone": "Asia/Kolkata",
    "business_hours": {"start": "09:00", "end": "18:00", "working_days": [0, 1, 2, 3, 4]},
    "holidays": [
        {"date": "2026-12-25", "name": "Sample holiday: Christmas Day"},
        {"date": "2027-01-26", "name": "Sample holiday: Republic Day"},
    ],
    "after_hours": {"policy": "queue_until_open", "critical_uses_on_call": True},
    "fallback_queue": "unassigned_queue",
    "urgent_priorities": ["critical", "high"],
    "mandatory_fields": {
        "default": ["order_id", "contact", "issue_description"],
        "by_category": {"general": ["contact", "issue_description"]},
    },
    "sla": {
        "warning_fraction": 0.75,
        "policies": {
            "critical": {"target_minutes": 240, "basis": "calendar"},
            "high": {"target_minutes": 480, "basis": "business"},
            "medium": {"target_minutes": 1080, "basis": "business"},
            "low": {"target_minutes": 2700, "basis": "business"},
        },
        "overrides": [
            {"issue_category": "payment", "priority": "high", "target_minutes": 240, "basis": "business"}
        ],
    },
    "priority": {
        "severity_points": {"low": 0, "medium": 15, "high": 30, "critical": 45},
        "impact_points": {
            "single_customer": 0,
            "multiple_orders": 8,
            "account_wide": 15,
            "widespread": 20,
        },
        "sentiment_points": {"positive": 0, "neutral": 0, "negative": 5, "very_negative": 10},
        "waiting_points": [
            {"min_hours": 4, "points": 5},
            {"min_hours": 24, "points": 10},
            {"min_hours": 48, "points": 15},
        ],
        "sla_points": [
            {"min_consumed": 0.5, "points": 5},
            {"min_consumed": 0.75, "points": 12},
            {"min_consumed": 1.0, "points": 20},
        ],
        "sla_class_thresholds": {"critical": 60, "high": 35, "medium": 15},
        "thresholds": {"critical": 70, "high": 45, "medium": 20},
        "floors": {
            "critical_severity_min": "high",
            "sla_warning_min": "medium",
            "sla_breached_min": "high",
        },
        "sentiment_max_levels_raise": 1,
    },
    "duplicates": {"window_hours": 72, "min_similarity": 0.6, "related_min_similarity": 0.3},
    "routing": {
        "teams": ["orders", "billing", "product_support", "technical", "general_support"],
        "categories": {
            "order": {"team": "orders", "skills": ["orders"]},
            "delivery": {"team": "orders", "skills": ["orders"]},
            "payment": {"team": "billing", "skills": ["billing"]},
            "refund": {"team": "billing", "skills": ["billing"]},
            "product": {"team": "product_support", "skills": ["product"]},
            "technical": {"team": "technical", "skills": ["technical"]},
            "account": {"team": "general_support", "skills": ["general"]},
            "general": {"team": "general_support", "skills": ["general"]},
        },
        "agents": [
            {"id": "agent_orders_1", "team": "orders", "skills": ["orders", "general"],
             "available": True, "max_open": 5, "on_call": False},
            {"id": "agent_orders_2", "team": "orders", "skills": ["orders"],
             "available": True, "max_open": 5, "on_call": False},
            {"id": "agent_billing_1", "team": "billing", "skills": ["billing"],
             "available": True, "max_open": 4, "on_call": False},
            {"id": "agent_product_1", "team": "product_support", "skills": ["product"],
             "available": True, "max_open": 5, "on_call": False},
            {"id": "agent_tech_1", "team": "technical", "skills": ["technical"],
             "available": True, "max_open": 4, "on_call": True},
            {"id": "agent_general_1", "team": "general_support", "skills": ["general", "product"],
             "available": True, "max_open": 5, "on_call": False},
            {"id": "agent_general_2", "team": "general_support", "skills": ["general"],
             "available": True, "max_open": 5, "on_call": False},
        ],
    },
}


class ConfigError(ValueError):
    """The configuration file is missing, unreadable or invalid."""


def _check(condition, message):
    if not condition:
        raise ConfigError(message)


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_name_list(value):
    return isinstance(value, list) and all(isinstance(item, str) and item for item in value)


def _check_policy(policy, name):
    _check(_is_number(policy["target_minutes"]) and policy["target_minutes"] > 0,
           f"{name}.target_minutes must be a positive number")
    _check(policy["basis"] in BASES, f"{name}.basis must be one of {BASES}")


def _check_ascending_rows(rows, field, name):
    _check(isinstance(rows, list), f"{name} must be a list")
    last = -1
    for row in rows:
        _check(_is_number(row[field]) and _is_number(row["points"]) and row["points"] >= 0,
               f"{name} rows need numeric {field} and non-negative points")
        _check(row[field] > last, f"{name} rows must be in strictly ascending {field} order")
        last = row[field]


def _check_descending_levels(levels, name):
    critical, high, medium = levels["critical"], levels["high"], levels["medium"]
    _check(all(_is_number(v) for v in (critical, high, medium)), f"{name} values must be numbers")
    _check(critical > high > medium >= 0, f"{name} must satisfy critical > high > medium >= 0")


def _validate_sections(data):
    _check(isinstance(data, dict), "the top level of the configuration must be an object")

    zone_name = data["timezone"]
    try:
        ZoneInfo(zone_name)
    except Exception as error:
        raise ConfigError(f"unknown timezone: {zone_name!r}") from error

    hours = data["business_hours"]
    start = time.fromisoformat(hours["start"])
    end = time.fromisoformat(hours["end"])
    _check(start < end, "business_hours.start must be earlier than business_hours.end")
    days = hours["working_days"]
    _check(
        isinstance(days, list) and len(days) > 0
        and all(isinstance(d, int) and not isinstance(d, bool) and 0 <= d <= 6 for d in days),
        "business_hours.working_days must be a non-empty list of integers 0 (Monday) to 6 (Sunday)",
    )
    for holiday in data["holidays"]:
        _check(isinstance(holiday, dict), "each holiday must be an object with a date")
        date.fromisoformat(holiday["date"])

    after_hours = data["after_hours"]
    _check(after_hours["policy"] in AFTER_HOURS_POLICIES, f"after_hours.policy must be one of {AFTER_HOURS_POLICIES}")
    _check(isinstance(after_hours["critical_uses_on_call"], bool), "after_hours.critical_uses_on_call must be true or false")
    _check(isinstance(data["fallback_queue"], str) and data["fallback_queue"], "fallback_queue must be a non-empty name")
    _check(set(data["urgent_priorities"]) <= set(PRIORITY_LEVELS), "urgent_priorities must use known priority levels")

    sla = data["sla"]
    fraction = sla["warning_fraction"]
    _check(_is_number(fraction) and 0 < fraction < 1, "sla.warning_fraction must be between 0 and 1")
    for level in PRIORITY_LEVELS:
        _check_policy(sla["policies"][level], f"sla.policies.{level}")
    for item in sla["overrides"]:
        _check(isinstance(item["issue_category"], str) and item["issue_category"], "sla.overrides need an issue_category")
        _check(item["priority"] in PRIORITY_LEVELS, "sla.overrides priority must be a known level")
        _check_policy(item, "sla.overrides entry")

    priority = data["priority"]
    for severity in SEVERITIES:
        _check(_is_number(priority["severity_points"][severity]) and priority["severity_points"][severity] >= 0,
               "priority.severity_points must cover every severity with non-negative numbers")
    for key in ("impact_points", "sentiment_points"):
        table = priority[key]
        _check(isinstance(table, dict) and len(table) > 0 and all(_is_number(v) and v >= 0 for v in table.values()),
               f"priority.{key} must be a non-empty table of non-negative numbers")
    _check_ascending_rows(priority["waiting_points"], "min_hours", "priority.waiting_points")
    _check_ascending_rows(priority["sla_points"], "min_consumed", "priority.sla_points")
    _check_descending_levels(priority["sla_class_thresholds"], "priority.sla_class_thresholds")
    _check_descending_levels(priority["thresholds"], "priority.thresholds")
    for key in ("critical_severity_min", "sla_warning_min", "sla_breached_min"):
        _check(priority["floors"][key] in PRIORITY_LEVELS, f"priority.floors.{key} must be a known level")
    raise_limit = priority["sentiment_max_levels_raise"]
    _check(isinstance(raise_limit, int) and not isinstance(raise_limit, bool) and raise_limit >= 0,
           "priority.sentiment_max_levels_raise must be an integer of 0 or more")

    duplicates = data["duplicates"]
    _check(_is_number(duplicates["window_hours"]) and duplicates["window_hours"] > 0, "duplicates.window_hours must be positive")
    for key in ("min_similarity", "related_min_similarity"):
        _check(_is_number(duplicates[key]) and 0 <= duplicates[key] <= 1, f"duplicates.{key} must be between 0 and 1")
    _check(duplicates["related_min_similarity"] <= duplicates["min_similarity"],
           "duplicates.related_min_similarity must not exceed duplicates.min_similarity")

    routing = data["routing"]
    teams = routing["teams"]
    _check(_is_name_list(teams) and len(teams) > 0, "routing.teams must be a non-empty list of names")
    categories = routing["categories"]
    _check(isinstance(categories, dict) and len(categories) > 0, "routing.categories must be a non-empty table")
    for name, rule in categories.items():
        _check(rule["team"] in teams, f"routing.categories.{name}.team is not in routing.teams")
        _check(_is_name_list(rule["skills"]), f"routing.categories.{name}.skills must be a list of names")
    seen = set()
    for agent in routing["agents"]:
        _check(isinstance(agent["id"], str) and agent["id"], "every agent needs an id")
        _check(agent["id"] not in seen, f"duplicate agent id: {agent['id']}")
        seen.add(agent["id"])
        _check(agent["team"] in teams, f"agent {agent['id']} has a team that is not in routing.teams")
        _check(_is_name_list(agent["skills"]), f"agent {agent['id']} skills must be a list of names")
        _check(isinstance(agent["available"], bool) and isinstance(agent["on_call"], bool),
               f"agent {agent['id']} available and on_call must be true or false")
        _check(isinstance(agent["max_open"], int) and not isinstance(agent["max_open"], bool) and agent["max_open"] >= 1,
               f"agent {agent['id']} max_open must be an integer of 1 or more")

    mandatory = data["mandatory_fields"]
    field_lists = [mandatory["default"]] + list(mandatory["by_category"].values())
    for fields in field_lists:
        _check(isinstance(fields, list) and all(f in MANDATORY_FIELD_NAMES for f in fields),
               f"mandatory_fields may only use: {', '.join(MANDATORY_FIELD_NAMES)}")
    for category in mandatory["by_category"]:
        _check(category in categories, f"mandatory_fields.by_category names an unknown category: {category}")


def _validate(data):
    try:
        _validate_sections(data)
    except ConfigError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise ConfigError(f"configuration is malformed: {type(error).__name__}: {error}") from error


def _merge(base, override):
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()[:16]


class TicketConfig:
    """A validated, read-only view of one configuration file version."""

    def __init__(self, data):
        self.data = data
        self.tz = ZoneInfo(data["timezone"])
        hours = data["business_hours"]
        self.work_start = time.fromisoformat(hours["start"])
        self.work_end = time.fromisoformat(hours["end"])
        self.working_days = frozenset(hours["working_days"])
        self.holidays = frozenset(date.fromisoformat(h["date"]) for h in data["holidays"])
        self.fingerprint = _digest(data)
        # Changes only when something that moves an SLA clock or target changes.
        self.calendar_fingerprint = _digest(
            {key: data[key] for key in ("timezone", "business_hours", "holidays", "sla")}
        )

    def is_working_day(self, day):
        return day.weekday() in self.working_days and day not in self.holidays

    def sla_target(self, priority, category=None):
        """The SLA target that applies to a priority and issue category."""
        sla = self.data["sla"]
        for item in sla["overrides"]:
            if item["priority"] == priority and item["issue_category"] == category:
                return {
                    "target_minutes": item["target_minutes"],
                    "basis": item["basis"],
                    "source": f"override:{category}:{priority}",
                }
        if priority not in sla["policies"]:
            raise ValueError(f"unknown priority: {priority!r}")
        policy = sla["policies"][priority]
        return {
            "target_minutes": policy["target_minutes"],
            "basis": policy["basis"],
            "source": f"policy:{priority}",
        }


_lock = threading.Lock()
_cache = {}
_last_error = {}


def config_path(path=None):
    if path is not None:
        return Path(path)
    from_env = os.getenv("TICKET_CONFIG_PATH")
    return Path(from_env) if from_env else DEFAULT_CONFIG_PATH


def write_default_config(path):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")


def reset_cache():
    with _lock:
        _cache.clear()
        _last_error.clear()


def last_config_error(path=None):
    """The reason the last edit was ignored, or None when the file is in use as written."""
    with _lock:
        return _last_error.get(str(config_path(path)))


def get_config(path=None):
    """Returns the current configuration, re-reading the file so edits apply at once."""
    target = config_path(path)
    key = str(target)
    with _lock:
        if not target.exists():
            if key == str(DEFAULT_CONFIG_PATH):
                write_default_config(target)
            elif key in _cache:
                _last_error[key] = "configuration file is missing; the last good copy is in use"
                return _cache[key][1]
            else:
                raise ConfigError(f"configuration file not found: {target.name}")
        try:
            raw = target.read_bytes()
        except OSError as error:
            if key in _cache:
                _last_error[key] = f"configuration file could not be read: {type(error).__name__}"
                return _cache[key][1]
            raise ConfigError(f"configuration file could not be read: {type(error).__name__}") from error
        digest = hashlib.sha256(raw).hexdigest()
        cached = _cache.get(key)
        if cached is not None and cached[0] == digest:
            _last_error.pop(key, None)
            return cached[1]
        try:
            loaded = json.loads(raw.decode("utf-8-sig"))
            _check(isinstance(loaded, dict), "the top level of the configuration must be an object")
            data = _merge(DEFAULT_CONFIG, loaded)
            _validate(data)
            config = TicketConfig(data)
        except (ValueError, KeyError, TypeError) as error:
            if cached is not None:
                _last_error[key] = str(error)
                return cached[1]
            if isinstance(error, ConfigError):
                raise
            raise ConfigError(f"configuration is invalid: {error}") from error
        _cache[key] = (digest, config)
        _last_error.pop(key, None)
        return config