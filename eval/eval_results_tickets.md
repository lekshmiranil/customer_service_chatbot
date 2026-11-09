# Task 3 evaluation results

Run: 2026-11-09 12:51. Synthetic conversations only; no customer values.

| Scenario | Brief requirement | Expected | Observed | Result |
|---|---|---|---|---|
| Duplicate request and repeated processing | Detect duplicate requests | linked to the open ticket; repeats unchanged | second conversation linked_duplicate onto TKT-000001; tickets=1; repeats unchanged | PASS |
| Same order, different issue | Separate unrelated issues | own ticket, no incident | created TKT-000002; incident=None; tickets=2 | PASS |
| Related and unrelated issues | Group related issues, separate unrelated ones | related share an incident; unrelated stays apart | related incident=1; unrelated incident=None; tickets=3 | PASS |
| Missing mandatory information | Request missing mandatory information | follow-up asked once; cleared after the reply | asked for ['order_id', 'contact']; after the reply status=assigned, missing=[] | PASS |
| Priority recalculation | Priority from waiting time and SLA | low, then medium, then high after breach | low at creation, medium while waiting, high after breach | PASS |
| Agent unavailable: reassignment | Route by availability and workload | tickets move to the available agent | reassigned ['TKT-000001', 'TKT-000003']; owners=['agent_orders_2', 'agent_orders_2', 'agent_orders_2'] | PASS |
| Team unavailable: fallback queue | Route when a team is unavailable | queued in the fallback queue, team kept | queued ['TKT-000001', 'TKT-000002', 'TKT-000003'] in unassigned_queue (team_unavailable) | PASS |
| Team returns: queued tickets assigned | Capacity returning | queued tickets assigned and spread | assigned ['TKT-000001', 'TKT-000002', 'TKT-000003']; owners=['agent_orders_1', 'agent_orders_2', 'agent_orders_1'] | PASS |
| No agent with the required skill | Route by agent skills | queued with no_matching_agent | status=queued, code=no_matching_agent | PASS |
| Capacity limit and priority order | Route by workload and priority | freed slot goes to the higher priority | freed slot went to ['TKT-000003']; TKT-000002 still queued | PASS |
| After-hours request | Respect business hours | queued until reopening, then assigned | queued until Mon 09:00 (after_hours), assigned to agent_orders_1 at opening | PASS |
| Critical request after hours | Critical tickets may use on-call agents | on-call agent, or queue naming the gap | with on-call: agent_general_2; without: queued (after_hours) | PASS |
| SLA warning at 75 percent | Warn when 75 percent of the time is used | one warning, no repeats | warned at 75 percent (2026-10-23T09:00:00+00:00), not repeated | PASS |
| SLA breach escalation | Escalate automatically after a breach | one escalation, no repeats | escalated once at the deadline; events=['sla_warning', 'sla_breached', 'escalated'] | PASS |
| Runtime change: holiday added | Runtime changes to SLA conditions | deadline moves, no false breach | deadline moved Mon 26 to Tue 27; no false breach; one escalation at the new deadline | PASS |
| Runtime change: shorter target | Runtime changes to SLA conditions | recalculated and escalated | target cut to 360 min; escalated on the next reconcile; deadline 2026-10-21T10:30:00+00:00 | PASS |
| Runtime change: longer target | Runtime changes to SLA conditions | warning reset, warns again later | target raised to 3000 min; warning cleared, then re-issued at the new 75 percent point | PASS |
| Masked handoff summary | Generate a masked handoff summary | contact details and secrets masked | name and order kept; email, phone, card and password masked or removed; text unchanged by masking again | PASS |
| Masked log | No sensitive data in logs | no raw values in the log | 49 log lines, none contain raw contact details, card numbers or passwords | PASS |
| Real files untouched | Evaluation does not use real data | real log, database and config unchanged | real log, database and configuration were not modified | PASS |

20/20 scenarios passed.
