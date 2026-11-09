"""One-time script: appends a dated section to TASK6_NOTES.md. Append only, backs up first,
refuses if the heading already exists or the file is missing."""
import os
import shutil
import sys
import time

TARGET = "TASK6_NOTES.md"
HEADING = "## Language packs, configuration fixes and evaluation status (2026-11-07)"

SECTION = r'''
## Language packs, configuration fixes and evaluation status (2026-11-07)
Name marker. entities.py now also finds a name after "I am" or "I'm", but only when the words are capitalised and are not in a small stop list, so "I am waiting" gives no name and "I am Anitha Menon" gives "Anitha Menon". Lowercase "i am anitha" is deliberately not captured (known limit). Test: test_multilingual_iam_name.py (14 checks). The unseen_06 conversation passes because of this marker; that case was written to match it, so the pass is fitted, not independent.
Configuration of languages. languages.supported_languages() falls back to English when no configured code is usable, and detect() checks default_language against the supported list. Before this fix a list such as ["xx"] raised ValueError in detect (found by test_multilingual_language_config.py, confirmed by test_multilingual_zero_languages.py, then fixed). A force_language that is not in the configured list is ignored (dialogue.py); normal detection runs instead. Test: test_multilingual_force_language.py. Switching a language off through config\multilingual_config.json was tested by removing Tamil: Tamil script is then reported unknown and the customer is asked to clarify.
Language packs. src\multilingual\packs.py loads one JSON file per language from config\languages (or the folder in MULTILINGUAL_PACKS_DIR) when dialogue.py is imported. A pack can add a new language code or replace fields of an existing one: name, reply texts, intent labels, Roman words, intent cues, marker words, person-request words, name markers, name stop words, names the customer may use for the language, and a script range. A pack is validated completely first (unknown fields, missing reply keys or labels for a new language, reply placeholders that differ from the English template, an overlapping script range, broken JSON). An invalid pack is rejected as a whole and reported by load_packs(); the other packs still load. A new language also has to be listed in "languages" in the configuration; a pack file alone does not switch it on (checked: a language in the configuration without a pack is not used). The folder config\languages does not exist yet, so no real pack is installed.
Tests: test_multilingual_packs.py (32 checks, a synthetic language "zz" with invented words) and test_multilingual_packs_autoload.py (fresh processes through bridge.handle_turn: automatic load, no pack, loading three times). These tests show that the mechanism works. They say nothing about the quality of any language's wording. Not tested: a new language written in its own script (the test pack uses Roman words only), several processes at the same time, the Streamlit page. Packs are read only when dialogue.py is imported; code that imports only languages.py does not see them. If applying a valid pack fails part way, that one language may be partly applied (it is reported as rejected).
Person requests and vocabulary (from the handoff, verified by the tests named there). Roman Malayalam requests for a person are recognised by co-occurrence cues in lexicon_person.py (test_multilingual_person_requests.py, test_multilingual_person_flow.py). Known false positive: "ente phone repair cheyyaamo?" is handed off. intents._gapped allows one extra word inside a cue phrase of three or more words (test_multilingual_phrase_gap.py); two-word phrases are excluded on purpose. Roman Malayalam words were added to the language detection list (test_multilingual_ml_vocab.py). Tamil, Telugu and Kannada have no Roman cues for asking for a person, and person-request rules exist for Malayalam only.
Concurrency. test_multilingual_concurrency.py runs 8 customers as threads in one process on one database file: no failed turn, no leaked order ID, no lost turn, no lock error. Several processes and the Streamlit page are untested.
Evaluation status. Three sets, reported separately. Assistant-written (15 conversations): 15/15, 42/42 turn checks. User-written (eval_user_conversations.json, 8 conversations): 6/8; the first run of this set scored 5/8, and the sixth conversation passes only after the expectation of user_02 was corrected (see EXPECTATION_LOG.md); user_06 and user_08 were fitted afterwards, so they are not unseen. Unseen-set (eval_unseen_conversations.json, 18 conversations, 42 turns): 16/18, 40/42. It was written by the assistant after the code existed, so it is not blind.
Open failures, not hidden. user_04 (billing) and user_05 (device fault) are outside the ten intents (capability gaps). unseen_04 (Hindi and English mixed sentence, reported as en with mixed True, expected hi) and unseen_07 ("and that one?" with one order in context resolves to that order, expected a clarification) are open expectation questions: neither expectation was changed.
Known limits added or confirmed. Wording for Hindi, Tamil, Telugu and Kannada is AI-written and has no native review or blind test; only the Malayalam phrasings come from the user. "where is my package" is ambiguous between order_status and delivery_issue and is not resolved. Billing and device-fault intents are not added. The assistant-written sets show regressions, not generalisation.
'''

if not os.path.isfile(TARGET):
    print("REFUSED: " + TARGET + " not found; nothing was written")
    sys.exit(1)
with open(TARGET, "r", encoding="utf-8", newline="") as handle:
    source = handle.read()
if HEADING in source:
    print("REFUSED: the section already exists; nothing was written")
    sys.exit(1)

newline = "\r\n" if "\r\n" in source else "\n"
text = SECTION.replace("\r\n", "\n").replace("\n", newline)
if not source.endswith(newline):
    text = newline + text

os.makedirs("backups", exist_ok=True)
backup = os.path.join("backups", TARGET + ".before_2026-11-07_" + time.strftime("%H%M%S") + ".bak")
shutil.copy2(TARGET, backup)
with open(TARGET, "w", encoding="utf-8", newline="") as handle:
    handle.write(source + text)
print("ok: appended to " + TARGET)
print("ok: backup " + backup)