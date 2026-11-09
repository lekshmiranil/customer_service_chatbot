"""Five-factor ticket priority (Task 3).

Factors and how each one counts (all numbers come from the "priority" section of the config):
  1. severity     - points per severity label.
  2. impact       - points per impact label.
  3. sentiment    - points per sentiment label. Small, and capped: it can raise the result by at
                    most sentiment_max_levels_raise levels above what the other factors give,
                    and it can never lower anything or override a floor.
  4. waiting time - hours since the ticket was created, measured on the SAME clock as the ticket's
                    SLA (business time for business SLAs, calendar time for calendar SLAs), so the
                    two never disagree. Highest matching row of waiting_points applies.
  5. SLA          - share of the SLA time already used; highest matching row of sla_points applies.

The SLA policy itself is chosen from severity + impact only (the "sla class"), which avoids a
circle between priority and SLA. Floors then guarantee a minimum level: critical severity,
SLA warning, SLA breach. Everything is deterministic; ties in a queue are broken by queue_sort_key.
"""
from src.tickets.business_time import evaluate_sla

LEVELS = ("low", "medium", "high", "critical")
LEVEL_INDEX = {name: position for position, name in enumerate(LEVELS)}
FRACTION_TOLERANCE = 1e-9


def level_from_score(score, thresholds):
    if score >= thresholds["critical"]:
        return "critical"
    if score >= thresholds["high"]:
        return "high"
    if score >= thresholds["medium"]:
        return "medium"
    return "low"


def _points_from_rows(rows, field, value):
    points = 0
    for row in rows:
        if value >= row[field]:
            points = row["points"]
        else:
            break
    return points


def _at_least(level, floor, rule_name, rules, reasons):
    if LEVEL_INDEX[level] >= LEVEL_INDEX[floor]:
        return level
    rules.append(rule_name)
    reasons.append(f"rule {rule_name}: raised {level} to {floor}")
    return floor


def compute_priority(cfg, severity, impact, sentiment, issue_category, created_at, now):
    """Priority, score, per-factor points and the reasons behind the decision."""
    settings = cfg.data["priority"]
    if severity not in settings["severity_points"]:
        raise ValueError(f"unknown severity: {severity!r}")
    reasons = []
    rules = []

    severity_points = settings["severity_points"][severity]
    impact_points = settings["impact_points"].get(impact)
    if impact_points is None:
        impact_points = 0
        reasons.append(f"impact {impact!r} is not in the configured table; counted as 0")
    sentiment_points = settings["sentiment_points"].get(sentiment)
    if sentiment_points is None:
        sentiment_points = 0
        reasons.append(f"sentiment {sentiment!r} is not in the configured table; counted as 0")

    objective = severity_points + impact_points
    sla_class = level_from_score(objective, settings["sla_class_thresholds"])
    target = cfg.sla_target(sla_class, issue_category)
    sla = evaluate_sla(cfg, created_at, target, now)
    waiting_hours = sla["elapsed_seconds"] / 3600.0

    waiting_points = _points_from_rows(settings["waiting_points"], "min_hours", waiting_hours)
    sla_points = _points_from_rows(
        settings["sla_points"], "min_consumed", sla["consumed_fraction"] + FRACTION_TOLERANCE
    )

    total = severity_points + impact_points + sentiment_points + waiting_points + sla_points
    thresholds = settings["thresholds"]
    level_full = level_from_score(total, thresholds)
    level_plain = level_from_score(total - sentiment_points, thresholds)
    allowed_raise = settings["sentiment_max_levels_raise"]
    level = level_full
    if LEVEL_INDEX[level_full] > LEVEL_INDEX[level_plain] + allowed_raise:
        level = LEVELS[LEVEL_INDEX[level_plain] + allowed_raise]
        rules.append("sentiment_cap")
        reasons.append(f"rule sentiment_cap: sentiment may raise the level by at most {allowed_raise}; "
                       f"{level_full} reduced to {level}")

    floors = settings["floors"]
    if severity == "critical":
        level = _at_least(level, floors["critical_severity_min"], "critical_severity_floor", rules, reasons)
    if sla["state"] == "breached":
        level = _at_least(level, floors["sla_breached_min"], "sla_breached_floor", rules, reasons)
    elif sla["state"] == "warning":
        level = _at_least(level, floors["sla_warning_min"], "sla_warning_floor", rules, reasons)

    basis = target["basis"]
    reasons[:0] = [
        f"severity {severity}: +{severity_points}",
        f"impact {impact}: +{impact_points}",
        f"sentiment {sentiment}: +{sentiment_points}",
        f"waiting {waiting_hours:.1f} h on the {basis} clock: +{waiting_points}",
        f"SLA {sla['state']}: {sla['consumed_fraction'] * 100:.0f}% of the {target['target_minutes']} "
        f"minute {basis} target used ({target['source']}): +{sla_points}",
        f"score {total} maps to {level_full}",
    ]
    return {
        "priority": level,
        "score": total,
        "points": {
            "severity": severity_points,
            "impact": impact_points,
            "sentiment": sentiment_points,
            "waiting": waiting_points,
            "sla": sla_points,
        },
        "sla_class": sla_class,
        "sla_target": target,
        "sla": sla,
        "waiting_hours": round(waiting_hours, 4),
        "rules_applied": rules,
        "reasons": reasons,
    }


def queue_sort_key(priority, score, created_at_iso, ticket_id):
    """Sort key for work queues: higher priority, higher score, older ticket, then ticket id.

    created_at_iso must be a UTC ISO-8601 string so that string order is time order.
    """
    return (-LEVEL_INDEX[priority], -score, created_at_iso, ticket_id)