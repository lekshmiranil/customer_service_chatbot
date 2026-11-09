# Task 2 evaluation results

Run: 2026-11-07 23:46. Synthetic files only; no customer values.

| Scenario | Brief requirement | Expected | Observed | Result |
|---|---|---|---|---|
| Matching invoice (baseline) | Compare OCR fields with the message | done / confirmed | done / confirmed | PASS |
| Blurred image | Low quality: ask for another file | done / needs_better_file | done / needs_better_file | PASS |
| Mismatched invoice | Conflict: request clarification | done / conflict | done / conflict | PASS |
| Delayed processing: customer wait | Over budget: move to background queue and notify | queued, wait under 4 s | queued, wait 2.0 s | PASS |
| Delayed processing: final result | Customer gets the result later | done / confirmed | done / confirmed | PASS |
| Expired file: stored | Upload is kept during retention | stored (image + sidecar) | 2 files | PASS |
| Expired file: access | Expired file cannot be used | refused after 25 h | refused | PASS |
| Expired file: deletion | Delete after retention period | upload folder empty | 0 files left | PASS |
| Prompt-injection image: verdict | Reject hidden instructions | done / rejected | done / rejected | PASS |
| Prompt-injection image: file | Rejected file is deleted | upload folder empty | 0 files left | PASS |
| Real log untouched | Evaluation does not write to the real log | no evaluation events added | none added | PASS |

11/11 checks passed.
