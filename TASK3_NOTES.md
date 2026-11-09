# Task 3 notes: support ticket automation

## Design choices
- **One ticket per conversation.** A conversation that reaches a trigger creates or updates one ticket. Repeated processing of the same text changes nothing.
- **Duplicates.** Same category plus a shared order number, or the same customer with similarity of at least 0.6, or a shared error code, within 72 hours: linked to the open ticket, not a new one.
- **Related issues.** Same category with a shared error code, or a shared product or order with similarity of at least 0.3: each gets its own ticket in a shared incident. Different categories never link.
- **Priority.** Points for severity, impact, sentiment, waiting time and SLA consumption. The SLA class is chosen from severity and impact only, which avoids a circular dependency with the priority. Sentiment can raise the level by at most one.
- **Routing.** Team and skills come from the category. Candidates are available agents under capacity; lowest load ratio wins, then fewer open tickets, then agent id. If none qualify the ticket goes to `unassigned_queue` with a code: `no_matching_agent`, `team_unavailable`, `after_hours` or `all_at_capacity`. Queued tickets are retried in priority order and reassigned when an agent becomes unavailable.
- **SLA.** Targets: critical 240 calendar minutes; high 480, medium 1080 and low 2700 business minutes; payment tickets with high priority 240 business minutes. Weekends and holidays are excluded. One warning at 75 percent and one escalation per ticket. Flags reset only after a policy, calendar or holiday change leaves the ticket below the threshold, or by an explicit reset. A late detection records the real crossing time.
- **Runtime changes.** The configuration is re-read when the file changes. The next reconcile recalculates open tickets (holidays, targets, thresholds, availability).
- **Privacy.** The database keeps only masked conversation text. Contact fields are kept structured and masked again in handoffs. Logs hold ids, statuses and codes only.

## Evidence
- `eval_tickets_run.py`: 20 of 20 scenarios pass (see `eval_results_tickets.md`).
- Detailed tests: calendar 68 checks, extract and priority 104, store and service 86, routing and SLA 89, handoff and workflow 53, plus the chat bridge test.
- Live app check on a Saturday: a ticket was created from a low-confidence question, updated from the reply box, queued after hours with the next business deadline, and two blurred uploads raised the file trigger on the same ticket.

## Known limits
- Category, severity, impact and sentiment come from English keyword lists. Inferred fields are labelled as inferred.
- Order-ID and error-code patterns are separate from the Task 2 comparison code.
- Routing only uses agents of the category's own team.
- The SLA clock keeps running while a ticket waits for the customer.
- A duplicate conversation's inferred severity replaces the earlier one.
- Text questions asked after a ticket exists are added to the conversation but reach the ticket only on the next trigger or reply-box message.
- Troubleshooting steps in the handoff come from the transcript and are not independently verified.
- The low-confidence trigger also fires on meaningless input such as "I don't know."
- There is no email or SMS push, and the background reconciler runs only while the app runs.
- The teams, agents and holidays in the default configuration are placeholders.