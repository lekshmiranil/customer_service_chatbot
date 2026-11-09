
# Expectation log (2026-11-07)

- user_02: EXPECTATION ERROR, corrected after seeing the result. Original expectation: kind query, intent
  return_request. Problems: return_request is not one of the ten intents, and the message has no order ID, so the
  layer correctly asks for it (kind clarify, intent return_exchange). Counted as an expectation error, not a pass:
  user-written 5/8 as first run, 6/8 only after this correction.
- user_04 (billing) and user_05 (device fault): real capability gaps, outside the ten intents. Not changed.
- unseen_04: OPEN. Hindi and English mixed sentence reported as en with mixed True; expected hi. Which language the
  reply should use is undecided. Expectation not changed.
- unseen_07: OPEN. 'and that one?' with one order in context resolves to that order; expected clarify. Whether that
  is acceptable is undecided. Expectation not changed.
- unseen_04 and unseen_07 were written by the assistant, not blind.
- customer role, manual Streamlit check: EXPECTATION ERROR (mine). Expected no ticket for 'order details of ORD-12345' at role customer. The first customer run showed 'This matches your earlier request, so it was added to ticket TKT-000019' because the page had not been reloaded after the public run, so the session still had an open ticket (main.py record_text_exchange keeps adding exchanges while ticket_open is set; the rest of that function was not seen). Two runs in fresh sessions raised no ticket. Not a defect of the retrieval_query patch.
- Order-details gap and retrieval gaps (findings 1 to 6 in TASK6_NOTES.md): found by manual use and probes, not by any evaluation set. No expectation in the evaluation sets was added or changed; the sets still do not exercise the knowledge-assistant step.
- test_multilingual_retrieval_query.py: the canonical order_status wording is fitted to one FAQ (FAQ-ORD-GL) on purpose. The check 'customer: no nothing-about note' was vacuous while that answer was refused and is meaningful now that the FAQ answers.
- Process: the fallback tests were not shown failing first (see TASK6_NOTES.md).
