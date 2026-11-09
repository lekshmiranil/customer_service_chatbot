# Task 4 evaluation: knowledge assistant

Fixed date: 2026-10-24. No model and no network were used. Scenarios: 48. Passed: 48.

| Scenario | Category | Role | Region | Expected | Actual | Reason | Cited | Pass |
|---|---|---|---|---|---|---|---|---|
| conflict-current-us | conflicting | public | US | answered | answered | ok | POL-REF-GL v2 | yes |
| conflict-region-override | conflicting | public | IN | answered | answered | ok | POL-REF-IN v1 | yes |
| conflict-eu-uses-global | conflicting | public | EU | answered | answered | ok | POL-REF-GL v2 | yes |
| conflict-region-unknown | clarification | public | GLOBAL | clarify | clarify | needs_region | - | yes |
| conflict-tie | ambiguous | public | US | refused | refused | ambiguous_sources | - | yes |
| conflict-warranty-current | conflicting | public | US | answered | answered | ok | POL-WAR-GL v2 | yes |
| conflict-troubleshooting-current | conflicting | public | US | answered | answered | ok | TS-WIFI-GL v2 | yes |
| history-refund-2024 | historical | public | US | answered | answered | ok | POL-REF-GL v1 | yes |
| history-refund-before-india-doc | historical | public | IN | answered | answered | ok | POL-REF-GL v2 | yes |
| history-refund-india-start-day | historical | public | IN | answered | answered | ok | POL-REF-IN v1 | yes |
| history-warranty-2025 | historical | public | US | answered | answered | ok | POL-WAR-GL v1 | yes |
| history-last-day-of-version | historical | public | US | answered | answered | ok | POL-REF-GL v1 | yes |
| history-period-unchanged | historical | public | US | answered | answered | ok | POL-WAR-GL v1 | yes |
| history-period-changed | clarification | public | US | clarify | clarify | policy_changed_in_period | - | yes |
| history-date-missing | clarification | public | US | clarify | clarify | date_unresolved | - | yes |
| history-date-ambiguous | clarification | public | US | clarify | clarify | date_ambiguous | - | yes |
| history-two-dates | clarification | public | US | clarify | clarify | date_ambiguous | - | yes |
| expired-no-successor | expired | public | US | refused | refused | not_in_force | - | yes |
| expired-asked-historically | expired | public | US | answered | answered | ok | POL-TRD-GL v1 | yes |
| expired-day-after | expired | public | US | refused | refused | not_in_force | - | yes |
| future-version-ignored | future-dated | public | US | answered | answered | ok | POL-REF-GL v2 | yes |
| future-careplus-ignored | future-dated | public | US | answered | answered | ok | POL-CP-GL v1 | yes |
| future-date-question | future-dated | public | US | refused | refused | future_date | - | yes |
| future-month-question | future-dated | public | US | refused | refused | future_date | - | yes |
| restricted-hidden-from-public | restricted | public | US | refused | refused | no_evidence | - | yes |
| restricted-hidden-from-internal | restricted | internal | US | refused | refused | no_evidence | - | yes |
| restricted-visible-to-restricted | restricted | restricted | US | answered | answered | ok | RST-DISC-GL v1 | yes |
| restricted-footer-cannot-downgrade | restricted | public | US | refused | refused | no_evidence | - | yes |
| internal-hidden-from-public | restricted | public | US | refused | refused | no_evidence | - | yes |
| internal-visible-to-internal | restricted | internal | US | answered | answered | ok | TS-FW-INT v1 | yes |
| customer-hidden-from-public | restricted | public | US | refused | refused | no_evidence | - | yes |
| customer-visible-to-customer | restricted | customer | US | answered | answered | ok | FAQ-ORD-GL v1 | yes |
| region-doc-hidden-from-india | restricted | public | IN | refused | refused | not_applicable | - | yes |
| region-doc-visible-to-eu | restricted | public | EU | answered | answered | ok | FAQ-EU-EU v1 | yes |
| injection-shipping-answered | prompt-injected | public | US | answered | answered | ok | FAQ-SHIP-GL v1 | yes |
| injection-claim-not-repeated | prompt-injected | public | US | refused | refused | no_evidence | - | yes |
| injection-password-answered | prompt-injected | public | US | answered | answered | ok | FAQ-PWD-GL v1 | yes |
| injection-comment-leak | prompt-injected | public | US | refused | refused | question_blocked | - | yes |
| injection-in-question-blocked | prompt-injected | public | US | refused | refused | question_blocked | - | yes |
| injection-in-question-ignored | prompt-injected | public | US | answered | answered | ok | POL-REF-GL v2 | yes |
| missing-evidence-offtopic | missing evidence | public | US | refused | refused | no_evidence | - | yes |
| missing-evidence-product-fact | missing evidence | public | US | refused | refused | no_evidence | - | yes |
| missing-evidence-unknown-product | missing evidence | public | US | refused | refused | no_evidence | - | yes |
| unsupported-premise | unsupported claim | public | US | answered | answered | ok | POL-REF-GL v2 | yes |
| unsupported-term-noted | unsupported claim | public | US | answered | answered | ok | PRD-HH-GL v1 | yes |
| plain-faq | plain | public | US | answered | answered | ok | FAQ-SETUP-GL v1 | yes |
| plain-product | plain | public | US | answered | answered | ok | PRD-HH-GL v1 | yes |
| plain-careplus-price | plain | public | US | answered | answered | ok | POL-CP-GL v1 | yes |
