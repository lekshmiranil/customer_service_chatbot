# Task 5 evaluation: sentiment, risk and escalation

Fixed clock in October 2026, Indian business hours from the ticket configuration. No model and no network were used. Scenarios: 34. Passed: 34.

| Scenario | Category | Expected (escalations / queues / label) | Actual | Pass |
|---|---|---|---|---|
| sarcasm-strong-phrase | sarcasm | [] / [] / sarcastic | [] / [] | yes |
| sarcasm-praise-with-failure | sarcasm | [] / [] / sarcastic | [] / [] | yes |
| sarcasm-thanks-for-nothing | sarcasm | [] / [] / sarcastic | [] / [] | yes |
| sarcasm-hindi | sarcasm | [] / [] / sarcastic | [] / [] | yes |
| sarcasm-with-risk | sarcasm | ['high_risk:duplicate_payment'] / ['priority_support'] / sarcastic | ['high_risk:duplicate_payment'] / ['priority_support'] | yes |
| sarcasm-from-history | sarcasm | ['repeated_negative'] / ['priority_support'] / sarcastic | ['repeated_negative'] / ['priority_support'] | yes |
| genuine-praise-not-sarcasm | sarcasm | [] / [] / positive | [] / [] | yes |
| calm-duplicate-payment | calm high-risk | ['high_risk:duplicate_payment'] / ['priority_support'] / neutral | ['high_risk:duplicate_payment'] / ['priority_support'] | yes |
| calm-account-compromise | calm high-risk | ['high_risk:account_compromise'] / ['priority_support'] / neutral | ['high_risk:account_compromise'] / ['priority_support'] | yes |
| calm-legal-threat | calm high-risk | ['high_risk:legal_threat'] / ['priority_support'] / neutral | ['high_risk:legal_threat'] / ['priority_support'] | yes |
| calm-hindi-account | calm high-risk | ['high_risk:account_compromise'] / ['priority_support'] | ['high_risk:account_compromise'] / ['priority_support'] | yes |
| calm-roman-hindi-duplicate | calm high-risk | ['high_risk:duplicate_payment'] / ['priority_support'] | ['high_risk:duplicate_payment'] / ['priority_support'] | yes |
| calm-malayalam-legal | calm high-risk | ['high_risk:legal_threat'] / ['priority_support'] | ['high_risk:legal_threat'] / ['priority_support'] | yes |
| after-hours-urgent | after hours | [] / ['on_call'] | [] / ['on_call'] | yes |
| after-hours-normal | after hours | [] / ['next_working_day'] | [] / ['next_working_day'] | yes |
| after-hours-weekend | after hours | [] / ['next_working_day'] | [] / ['next_working_day'] | yes |
| after-hours-plain-question | after hours | [] / [] | [] / [] | yes |
| after-hours-calm-high-risk | after hours | ['high_risk:duplicate_payment'] / ['on_call'] | ['high_risk:duplicate_payment'] / ['on_call'] | yes |
| after-hours-upgrade-to-urgent | after hours | [] / ['next_working_day', 'on_call'] | [] / ['next_working_day', 'on_call'] | yes |
| business-hours-single-complaint | after hours | [] / [] | [] / [] | yes |
| timeout-before-15 | time change | [] / [] | [] / [] | yes |
| timeout-exactly-15 | time change | [] / [] | [] / [] | yes |
| timeout-after-16 | time change | ['unresolved_timeout'] / ['priority_support'] | ['unresolved_timeout'] / ['priority_support'] | yes |
| timeout-only-once | time change | ['unresolved_timeout'] / ['priority_support'] | ['unresolved_timeout'] / ['priority_support'] | yes |
| timeout-human-reply | time change | [] / [] | [] / [] | yes |
| timeout-solved | time change | [] / [] | [] / [] | yes |
| timeout-crosses-closing | time change | ['unresolved_timeout'] / ['next_working_day'] | ['unresolved_timeout'] / ['next_working_day'] | yes |
| timeout-urgent-crosses-closing | time change | ['unresolved_timeout'] / ['on_call'] | ['unresolved_timeout'] / ['on_call'] | yes |
| timeout-weekend | time change | ['unresolved_timeout'] / ['next_working_day'] | ['unresolved_timeout'] / ['next_working_day'] | yes |
| repeated-three | repeated negative | ['repeated_negative'] / ['priority_support'] | ['repeated_negative'] / ['priority_support'] | yes |
| repeated-two-only | repeated negative | [] / [] | [] / [] | yes |
| repeated-reset-by-thanks | repeated negative | [] / [] | [] / [] | yes |
| repeated-after-hours | repeated negative | ['repeated_negative'] / ['next_working_day'] | ['repeated_negative'] / ['next_working_day'] | yes |
| repeated-and-timeout | repeated negative | ['repeated_negative', 'unresolved_timeout'] / ['priority_support'] | ['repeated_negative', 'unresolved_timeout'] / ['priority_support'] | yes |
