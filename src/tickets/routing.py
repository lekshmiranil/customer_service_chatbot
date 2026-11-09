"""Ticket routing rules (Task 3).

Selection rule (documented and deterministic):
  1. The ticket's issue category picks a team and the skills required (routing.categories).
  2. Eligible agents belong to that team, have every required skill and are marked available.
  3. Outside business hours, with the "queue_until_open" policy, nobody is assigned and the ticket
     waits for the next opening, EXCEPT critical or escalated tickets, which may go to on-call agents
     when after_hours.critical_uses_on_call is true. The "route_anyway" policy ignores business hours.
  4. An agent at capacity (open assigned tickets >= max_open) is skipped.
  5. Among the rest, the agent with the lowest load ratio (open / max_open) wins; ties go to the agent
     with fewer open tickets, then to the lowest agent id.
  6. If nobody is eligible the ticket is NOT marked assigned: it goes to the configured fallback queue
     with a reason code: no_matching_agent, team_unavailable, after_hours or all_at_capacity.
Only agents of the category's own team are considered.
"""
from src.tickets.business_time import is_business_open, next_business_open
from src.tickets.store import iso


def category_rule(cfg, category):
    categories = cfg.data["routing"]["categories"]
    if category in categories:
        return categories[category]
    if "general" in categories:
        return categories["general"]
    return next(iter(categories.values()))


def matching_agents(cfg, category):
    """(rule, agents of the rule's team that have every required skill)."""
    rule = category_rule(cfg, category)
    required = set(rule["skills"])
    members = [
        agent for agent in cfg.data["routing"]["agents"]
        if agent["team"] == rule["team"] and required <= set(agent["skills"])
    ]
    return rule, members


def agent_is_valid(cfg, agent_id, category):
    """True while the agent still exists, matches the category's team and skills, and is available."""
    _, members = matching_agents(cfg, category)
    return any(agent["id"] == agent_id and agent["available"] for agent in members)


def decide_route(cfg, category, priority, escalated, now, counts):
    """Chooses an agent or a reasoned fallback. counts maps agent id to open assigned tickets."""
    rule, members = matching_agents(cfg, category)
    team = rule["team"]
    required = sorted(rule["skills"])
    queue = cfg.data["fallback_queue"]

    def queued(code, reason, until=None):
        return {"outcome": "queued", "code": code, "reason": reason, "team": team,
                "agent": None, "queue": queue, "queued_until": until}

    if not members:
        return queued("no_matching_agent", f"no agent in {team} has the required skills: {', '.join(required)}")
    available = [agent for agent in members if agent["available"]]
    if not available:
        return queued("team_unavailable", f"every matching agent in {team} is marked unavailable")

    pool = available
    policy = cfg.data["after_hours"]
    if policy["policy"] == "queue_until_open" and not is_business_open(cfg, now):
        urgent = priority == "critical" or escalated
        if urgent and policy["critical_uses_on_call"]:
            pool = [agent for agent in available if agent["on_call"]]
            why = "no on-call agent is available for this urgent ticket"
        else:
            pool = []
            why = "non-urgent tickets wait for the next opening"
        if not pool:
            reopens = iso(next_business_open(cfg, now))
            return queued("after_hours", f"outside business hours; {why}; queued until {reopens}", reopens)

    with_room = [agent for agent in pool if counts.get(agent["id"], 0) < agent["max_open"]]
    if not with_room:
        return queued("all_at_capacity", f"every eligible agent in {team} is at capacity")
    chosen = min(
        with_room,
        key=lambda agent: (counts.get(agent["id"], 0) / agent["max_open"], counts.get(agent["id"], 0), agent["id"]),
    )
    load = counts.get(chosen["id"], 0)
    return {
        "outcome": "assigned",
        "code": "assigned",
        "reason": f"lowest workload ({load} of {chosen['max_open']} open) among {len(with_room)} eligible agent(s) in {team}",
        "team": team,
        "agent": chosen["id"],
        "queue": None,
        "queued_until": None,
    }