# Task 4 notes: knowledge assistant

## Scope
RAG assistant over product documents, FAQs, policies and troubleshooting guides. It runs beside the existing text flow, switched by a sidebar checkbox. A synthetic corpus of 22 documents is used because no real corpus exists.

## Design
- Retrieval, authorisation, date selection, conflict resolution, refusal and unsupported-claim checks are deterministic. No model and no key are needed to run any test.
- Filter order: access, product, date window, region.
- Conflict order per (topic, product): region-specific over GLOBAL, latest effective date, highest version. A full tie is refused.
- Expiry date is the last day in force (inclusive).
- Historical dates are parsed from the question (ISO, "12 March 2025", relative dates, month/year, year periods). A period is evaluated at both ends, and the bot asks for an exact date if the policy changed inside it.
- Injection: instruction-like chunks are quarantined whole, including HTML comments. Instruction-like sentences are removed from the question.
- Verification per answer line: valid citation to a chunk in the evidence set, at least 80 percent content-word support, all numbers present in the source, no added or dropped negation, no injection text.
- Constants in `answer.py`: MIN_COVERAGE 0.5, RELATIVE_SCORE 0.7, RELATIVE_COVERAGE 0.75, MAX_EVIDENCE_CHUNKS 3.

## Evaluation
`python eval_rag_run.py` runs 48 scenarios at the fixed date 2026-10-24 and writes `eval_results_rag.md`. Result on the development machine: 48 of 48 passed. Scenario counts: conflicting 5, clarification 5, ambiguous 1, historical 6, expired 3, future-dated 4, restricted 10, prompt-injected 6, missing evidence 3, unsupported claim 2, plain 3 (48 in total).

## Known limits
- Keyword BM25 search, no semantic matching.
- The verifier checks words, numbers, negation and citations, not meaning.
- English only.
- Region and role are demo selectors, not authentication.
- The Gemini phraser is checked only by the deterministic verifier and a daily cap.
- Refused answers raise a Task 3 support ticket whose first question uses generic wording. The ticket keyword rule treats the verb "escalate" as a request for a human, so a question about how to escalate also raises a ticket.