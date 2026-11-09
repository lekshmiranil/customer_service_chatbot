# Multilingual evaluation

Simulated clock, temporary databases, no model, no quota. Two separate scores.

## Scores

| Set | Conversations passed | Turn checks passed |
|-----|------|------|
| Assistant-written (written after seeing the code, NOT blind) | 15/15 | 42/42 |
| User-written (unseen by the assistant) | 6/8 | 6/8 |
| Assistant-written unseen set (written after the code, NOT blind) | 16/18 | 40/42 |

User file: 8 of 8 conversations usable

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

### user_02: return apeksha - PASS

| # | message | result |
|---|---------|--------|
| 1 | enikk return venam as soon as possible | ok |

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

### user_06: malayalam request for a person - PASS

| # | message | result |
|---|---------|--------|
| 1 | enikk oru manushyanodu samsarikkanam | ok |

### user_07: malayalam request for a person, different wording - PASS

| # | message | result |
|---|---------|--------|
| 1 | enikk oru agent nod samsarikkanam | ok |

### user_08: malayalam request for a person, another wording - PASS

| # | message | result |
|---|---------|--------|
| 1 | vilich samsarikkaan pattumo? | ok |

## Assistant-written unseen set (NOT blind; 18 of 18 conversations usable)

### unseen_01: roman hindi with spelling errors - PASS

| # | message | result |
|---|---------|--------|
| 1 | mera ordr kab ayega ORD-48213 | ok |

### unseen_02: roman tamil delivery problem - PASS

| # | message | result |
|---|---------|--------|
| 1 | enoda order innum varala ORD-52077 | ok |

### unseen_03: roman malayalam cancel - PASS

| # | message | result |
|---|---------|--------|
| 1 | ente order ORD-70415 cancel cheyyanam | ok |

### unseen_04: hindi and english mixed - FAIL

| # | message | result |
|---|---------|--------|
| 1 | mujhe refund chahiye for order ORD-33902 please | language: expected 'hi', got 'en' |

### unseen_05: language switches across three messages - PASS

| # | message | result |
|---|---------|--------|
| 1 | hello | ok |
| 2 | mera refund kab milega ORD-61188 | ok |
| 3 | ente order vannilla | ok |

### unseen_06: name, id and date kept for a follow-up - PASS

| # | message | result |
|---|---------|--------|
| 1 | I am Anitha Menon, my order ORD-84120 placed on 3 March 2026 needs a refund | ok |
| 2 | and when will it arrive? | ok |

### unseen_07: ambiguous follow-up with no clear referent - FAIL

| # | message | result |
|---|---------|--------|
| 1 | where is my order ORD-19001 | ok |
| 2 | and that one? | kind: expected 'clarify', got 'query' |

### unseen_08: two requests in roman malayalam - PASS

| # | message | result |
|---|---------|--------|
| 1 | refund venam, pinne delivery late aanu ORD-45550 | ok |

### unseen_09: corrected order id - PASS

| # | message | result |
|---|---------|--------|
| 1 | cancel my order ORD-27001 | ok |
| 2 | sorry, wrong number, it is ORD-27002 | ok |

### unseen_10: out of scope twice, then handoff - PASS

| # | message | result |
|---|---------|--------|
| 1 | mujhe GST bill chahiye | ok |
| 2 | meri screen kaam nahi kar rahi | ok |

### unseen_11: malayalam person request, new wording - PASS

| # | message | result |
|---|---------|--------|
| 1 | enikk oru manushyanumayi samsarikkanam | ok |

### unseen_12: product code kept - PASS

| # | message | result |
|---|---------|--------|
| 1 | SKU-4521 ki keemat kya hai | ok |

### unseen_13: long context, 12 messages - PASS

| # | message | result |
|---|---------|--------|
| 1 | mera order ORD-90321 kab aayega | ok |
| 2 | hello | ok |
| 3 | thanks | ok |
| 4 | hello | ok |
| 5 | thanks | ok |
| 6 | hello | ok |
| 7 | thanks | ok |
| 8 | hello | ok |
| 9 | thanks | ok |
| 10 | hello | ok |
| 11 | thanks | ok |
| 12 | and the refund? | ok |

### unseen_14: two customers at the same time - PASS

| # | message | result |
|---|---------|--------|
| 1 | where is my order ORD-11111 | ok |
| 2 | where is my order ORD-22222 | ok |
| 3 | and the refund? | ok |
| 4 | and the refund? | ok |

### unseen_15: return after 31 minutes, summary restored - PASS

| # | message | result |
|---|---------|--------|
| 1 | where is my order ORD-50101 | ok |
| 2 | hello | ok |

### unseen_16: return after 23 hours, still restored - PASS

| # | message | result |
|---|---------|--------|
| 1 | where is my order ORD-50202 | ok |
| 2 | hello | ok |

### unseen_17: return after 25 hours, new session - PASS

| # | message | result |
|---|---------|--------|
| 1 | where is my order ORD-50303 | ok |
| 2 | hello | ok |

### unseen_18: return after 20 minutes, same session - PASS

| # | message | result |
|---|---------|--------|
| 1 | where is my order ORD-50404 | ok |
| 2 | hello | ok |

