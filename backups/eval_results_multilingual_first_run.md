# Multilingual evaluation

Simulated clock, temporary databases, no model, no quota. Two separate scores.

## Scores

| Set | Conversations passed | Turn checks passed |
|-----|------|------|
| Assistant-written (written after seeing the code, NOT blind) | 15/15 | 42/42 |
| User-written (unseen by the assistant) | 2/5 | 2/5 |

User file: 5 of 5 conversations usable

Expectations in the assistant-written set were chosen by the assistant, so a high score there does not show how the layer behaves on unseen conversations. The user-written set is the meaningful one.

## Assistant-written conversations

### en_basic: English: greeting, order status, short follow-up - PASS

| # | message | result |
|---|---------|--------|
| 1 | hello | ok |
| 2 | where is my order ORD-12345 | ok |
| 3 | and the refund? | ok |

### hi_mixed: Hindi and English in one message - PASS

| # | message | result |
|---|---------|--------|
| 1 | mera order ORD-12345 refund chahiye please | ok |

### ml_pending: Malayalam roman: missing order id, then supplied - PASS

| # | message | result |
|---|---------|--------|
| 1 | ente order evide | ok |
| 2 | ORD-77777 | ok |

### ta_native_to_en: Tamil native script, then switch to English - PASS

| # | message | result |
|---|---------|--------|
| 1 | என் ஆர்டர் எங்கே | ok |
| 2 | where is my order ORD-31415 | ok |

### te_kn_switch: Telugu roman, then Kannada roman - PASS

| # | message | result |
|---|---------|--------|
| 1 | naa order ekkada undi ORD-20202 | ok |
| 2 | nanna order yelli ide ORD-30303 | ok |

### multiple_requests: Two requests in one message - PASS

| # | message | result |
|---|---------|--------|
| 1 | cancel my order ORD-40404 and give me a refund | ok |

### spelling: Spelling errors - PASS

| # | message | result |
|---|---------|--------|
| 1 | i want refnd for ORD-50505 | ok |
| 2 | wher is my ordr | ok |

### correction: Corrected order id - PASS

| # | message | result |
|---|---------|--------|
| 1 | where is my order ORD-60606 | ok |
| 2 | sorry, the order number is ORD-60607 | ok |

### entities_preserved: Name, order id and date kept as typed - PASS

| # | message | result |
|---|---------|--------|
| 1 | my name is Anu Menon, where is my order ORD-70707, I was told delivery on 12/11/2026 | ok |

### ambiguous_followup: Short follow-ups resolved from the last request - PASS

| # | message | result |
|---|---------|--------|
| 1 | where is my order ORD-80808 | ok |
| 2 | and the refund? | ok |
| 3 | and ORD-80809? | ok |

### low_confidence: Unrecognised text asks for clarification - PASS

| # | message | result |
|---|---------|--------|
| 1 | xyz qwerty asdf | ok |
| 2 | refund for ORD-90909 | ok |

### human_handoff: Request for a human agent - PASS

| # | message | result |
|---|---------|--------|
| 1 | I want to talk to a human agent | ok |

### context_12_messages: Context kept over 12 messages - PASS

| # | message | result |
|---|---------|--------|
| 1 | where is my order ORD-66666 | ok |
| 2 | hello | ok |
| 3 | thanks | ok |
| 4 | and the refund? | ok |
| 5 | hello | ok |
| 6 | thanks | ok |
| 7 | mera order kab aayega | ok |
| 8 | hello | ok |
| 9 | thanks | ok |
| 10 | where is my order | ok |
| 11 | hello | ok |
| 12 | and the refund? | ok |

### expiry_restore_new: 30-minute expiry, restore within 24 hours, new session after 24 hours - PASS

| # | message | result |
|---|---------|--------|
| 1 | where is my order ORD-11111 | ok |
| 2 | and the refund? | ok |
| 3 | hello | ok |
| 4 | hello | ok |

### isolation: Two customers at the same time - PASS

| # | message | result |
|---|---------|--------|
| 1 | where is my order ORD-10001 | ok |
| 2 | where is my order ORD-20002 | ok |
| 3 | and the refund? | ok |
| 4 | and the refund? | ok |

## User-written conversations

### user_01: order status inquiry - PASS

| # | message | result |
|---|---------|--------|
| 1 | where is my order ORD-12345 | ok |

### user_02: return apeksha - FAIL

| # | message | result |
|---|---------|--------|
| 1 | enikk return venam as soon as possible | kind: expected 'query', got 'clarify'; intent 'return_request' missing, got ['return_exchange'] |

### user_03: product information query - PASS

| # | message | result |
|---|---------|--------|
| 1 | kidhar hai is product ka features? | ok |

### user_04: billing inquiry - FAIL

| # | message | result |
|---|---------|--------|
| 1 | intha order ka bill njan kodukkano? | kind: expected 'query', got 'clarify'; intent 'billing_info' missing, got [] |

### user_05: technical support request - FAIL

| # | message | result |
|---|---------|--------|
| 1 | davice work aavathilla and off button cant find | intent 'technical_support' missing, got [] |

