import os
import shutil
import sys

NOTES = r"""# Task 6: Multilingual understanding and sessions

## What was built
A plain-Python package, src\multilingual. It has no Streamlit, no model and uses only the standard library. The clock is an argument, and the bridge never raises (it sets LAST_ERROR instead). Languages: English, Hindi, Malayalam, Tamil, Telugu, Kannada, in native script and Roman transliteration.

Modules: config, lexicon, lexicon_cues, languages, intents, entities, summary, session_store, replies, dialogue, bridge.

## How one message is handled
1. bridge.handle_turn resolves the session: active, restored from a summary, or new.
2. dialogue.handle_message extracts entities (order IDs, product codes, dates, names) exactly as typed and masks them.
3. The language is detected. A short low-confidence message keeps the session language. A clear message in another language switches it. A mixed message keeps both languages. Low confidence or an unsupported script asks the customer to choose a language.
4. Intents are found per clause (up to max_requests). Spelling errors and transliterated words are tolerated.
5. Short follow-ups ("and the refund?", "and ORD-123?") are resolved from the last intents or a pending request. A correction replaces the remembered value and is reported.
6. If an intent needs an order ID and none is known, the customer is asked for it and the request stays pending.
7. Low intent confidence or two competing intents asks a clarifying question.
8. Otherwise an English query is built from the intent plus the preserved entities and passed to the existing answer code. The lead line and notices are in the customer's language. The answer body stays English because the knowledge base search is English only.

## Sessions
- Ends after inactivity_minutes (30) without a message.
- If the same customer returns within restore_window_hours (24), the conversation summary is restored. Otherwise a new session starts and the customer is told.
- Sessions are isolated by session id. The Customer ID box in the sidebar is a demo selector, not a login. Without a customer ID only the same session id can be restored.
- At least context_min_turns (10) messages are kept. store_max_turns (40) turns are stored per session.
- Data: session_data\sessions.db. Customer messages are stored as typed.

## Configuration
config\multilingual_config.json merged over defaults. Keys: languages, default_language, session (inactivity_minutes, restore_window_hours, context_min_turns, store_max_turns), thresholds (language_confidence, intent_confidence, intent_margin, fuzzy_cutoff, followup_max_words, mixed_second_share, general_question_min_words), max_requests, intents_need_order, entities (order_prefixes, product_prefixes). Optional thresholds.inherit_confidence (default 0.75) is read by dialogue.py.
Environment variables: MULTILINGUAL_CONFIG_PATH, MULTILINGUAL_DB_PATH, MULTILINGUAL_NOW (simulated clock).

## Checks
Close Streamlit first. No test uses the model or the Gemini quota.
python test_multilingual_languages.py
python test_multilingual_entities.py
python test_multilingual_dialogue.py
python test_multilingual_extra.py
python test_multilingual_session.py
python eval_multilingual_run.py   (writes eval_results_multilingual.md)

## Evaluation
Two separate scores are reported. The assistant-written set (15 conversations) was written after the code existed, so it is not a blind result. On 2026-11-03 it scored 15/15 conversations and 42/42 turn checks. The user-written set is in eval_user_conversations.json and is the unseen set. Its score is recorded in eval_results_multilingual.md and has not been copied here.

## Known limits
- The cue lists for Hindi, Malayalam, Tamil, Telugu and Kannada and all replies in those languages were written by an AI and have not been reviewed by a native speaker.
- Order ID and product code formats are assumptions (prefix lists in the config).
- Months in dates are recognised in English only.
- Names are found only after a marker phrase such as "my name is" or "mera naam".
- Correction detection uses marker words. Rule-based intent matching misses subtle phrasing.
- Four-letter words are matched with a stricter spelling rule to avoid false hits, so some four-letter typos are missed.
- Knowledge answers stay English.
- Sentiment analysis (Task 5) detects language by script as en, hi or ml, so Tamil, Telugu and Kannada messages are not analysed in their own language.
- Old session rows are not purged by this task.
"""

README_SECTION = r"""
## Task 6: Multilingual understanding and sessions

### How it works
src\multilingual understands English, Hindi, Malayalam, Tamil, Telugu and Kannada (native script and Roman transliteration), including mixed-language messages and language switching in one conversation. It keeps names, order IDs, dates and product codes as typed, remembers the conversation, asks for clarification when language or intent confidence is low, and handles spelling errors, multiple requests and corrected information. Sessions end after 30 minutes of inactivity. A customer who returns within 24 hours gets the conversation summary back. Otherwise a new session starts. Non-English questions are turned into a plain English query for the existing answer code, so the answer text stays English.

### Known limits
Cue lists and replies in five languages are AI-written and not reviewed by a native speaker. ID formats are assumptions. See TASK6_NOTES.md.

### Configuration
config\multilingual_config.json. Optional environment variables: MULTILINGUAL_CONFIG_PATH, MULTILINGUAL_DB_PATH, MULTILINGUAL_NOW.

### Checks
python test_multilingual_languages.py, test_multilingual_entities.py, test_multilingual_dialogue.py, test_multilingual_extra.py, test_multilingual_session.py, then python eval_multilingual_run.py (writes eval_results_multilingual.md).
"""

ENV_LINES = """# Task 6: multilingual understanding and sessions. All optional.
# MULTILINGUAL_CONFIG_PATH=config\\multilingual_config.json
# MULTILINGUAL_DB_PATH=session_data\\sessions.db
# MULTILINGUAL_NOW=2026-11-03T10:00:00+00:00
"""


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def append(path, marker, addition, backup):
    text = read(path)
    if marker in text:
        print("already present:", path)
        return
    if not os.path.exists(backup):
        shutil.copyfile(path, backup)
    if not text.endswith("\n"):
        text += "\n"
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text + addition)
    print("appended:", path)


if os.path.exists("TASK6_NOTES.md"):
    print("already present: TASK6_NOTES.md")
else:
    with open("TASK6_NOTES.md", "w", encoding="utf-8", newline="\n") as handle:
        handle.write(NOTES)
    print("created: TASK6_NOTES.md")

append("README.md", "## Task 6:", README_SECTION, os.path.join("backups", "README_before_task6.md"))
append(".env.example", "# Task 6:", "\n" + ENV_LINES, os.path.join("backups", "env_example_before_task6.txt"))
sys.exit(0)