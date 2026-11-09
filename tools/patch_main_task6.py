import os
import shutil
import sys

PATH = os.path.join("src", "main.py")
REFERENCE = os.path.join("backups", "main_before_multilingual.py")
BACKUP = os.path.join("backups", "main_before_task6_integration.py")

IMPORT_OLD = "    set_ticket = None\n    start_timeout_checker = None\n"
IMPORT_NEW = IMPORT_OLD + '''try:
    from src.multilingual import bridge as ml_bridge
except Exception:
    ml_bridge = None  # the existing chatbot keeps working if the multilingual layer cannot load
'''

STATE_OLD = 'st.session_state.setdefault("unresolved_files", 0)\n'
STATE_NEW = STATE_OLD + 'st.session_state.setdefault("ml_session_id", "")\n'

SIDEBAR_OLD = (
    "current_settings = (True, knowledge_role, knowledge_region, use_gemini) "
    "if use_knowledge else (False,)\n"
)
SIDEBAR_NEW = SIDEBAR_OLD + '''
# ---------------------------------------------------------------- multilingual
st.sidebar.header("Multilingual")
use_multilingual = st.sidebar.checkbox(
    "Multilingual understanding",
    value=True,
    key="use_multilingual_toggle",
    disabled=ml_bridge is None,
)
use_multilingual = bool(use_multilingual and ml_bridge is not None)
ml_customer_id = st.sidebar.text_input(
    "Customer ID (demo selector, not a login)",
    key="ml_customer_id",
    disabled=not use_multilingual,
).strip()
current_settings = current_settings + (use_multilingual,)
if use_multilingual:
    ml_bridge.sweep()  # ends sessions idle for the configured time; never raises
'''

HELPER_OLD = 'user_question = st.text_input("Ask a question:", key="main_user_question_input")\n'
HELPER_NEW = '''def ask_existing(question):
    """The existing answer code, unchanged."""
    if use_knowledge:
        return answer_with_knowledge(question, knowledge_role, knowledge_region, use_gemini)
    return answer_question(question)


def ml_run_layer(question):
    """Runs the multilingual layer once per distinct question and remembers the result."""
    previous = st.session_state.get("ml_last")
    if previous and previous[0] == question:
        return previous[1]  # a setting change re-asks the same question: do not count it twice
    result = ml_bridge.handle_turn(
        st.session_state.get("ml_session_id", ""), ml_customer_id, text=question
    )
    if result.get("ok"):
        st.session_state["ml_session_id"] = result["session_id"]  # the id changes after expiry or restore
    st.session_state["ml_last"] = (question, result)
    return result


def answer_text_question(question):
    """Answers one text question, through the multilingual layer when it is on."""
    layer = ml_run_layer(question) if use_multilingual else None
    if layer is None or not layer.get("ok"):
        return ask_existing(question)
    kind = layer.get("kind")
    info = {
        "language": layer.get("language"),
        "status": layer.get("status"),
        "notice_text": layer.get("notice_text", ""),
        "notices": list(layer.get("notices") or []),
        "lead": "",
        "kind": kind,
    }
    if kind == "query" and layer.get("query") and not detect_prompt_injection(question):
        answer = ask_existing(layer["query"])  # plain English query built from intent and preserved entities
        info["lead"] = layer.get("text", "")
        answer["question"] = question  # the original text, so reruns reuse this answer
        answer["ml"] = info
        return answer
    if kind in ("clarify", "social", "handoff") and layer.get("text"):
        return {
            "question": question,
            "kind": "answer",
            "text": layer["text"],
            "escalated": bool(layer.get("escalated")),
            "rag_status": "clarify",
            "sources": [],
            "ml": info,
        }
    return ask_existing(question)


''' + HELPER_OLD

FLOW_OLD = (
    "            if use_knowledge:\n"
    "                answer = answer_with_knowledge(user_question, knowledge_role, knowledge_region, use_gemini)\n"
    "            else:\n"
    "                answer = answer_question(user_question)\n"
)
FLOW_NEW = "            answer = answer_text_question(user_question)\n"

DISPLAY_OLD = '    opening = (answer.get("sentiment") or {}).get("opening") or ""\n'
DISPLAY_NEW = '''    ml_info = answer.get("ml")
    if ml_info:
        if ml_info.get("notice_text"):
            st.info(ml_info["notice_text"])
        for line in ml_info.get("notices") or []:
            st.caption(line)
        if ml_info.get("lead") and answer["kind"] == "answer" and answer.get("rag_status") != "clarify":
            st.write(ml_info["lead"])

''' + DISPLAY_OLD

# Bottom-up order.
PLAN = [
    ("display block", DISPLAY_OLD, DISPLAY_NEW),
    ("text flow call", FLOW_OLD, FLOW_NEW),
    ("helper functions", HELPER_OLD, HELPER_NEW),
    ("sidebar block", SIDEBAR_OLD, SIDEBAR_NEW),
    ("session state default", STATE_OLD, STATE_NEW),
    ("import", IMPORT_OLD, IMPORT_NEW),
]

with open(PATH, "rb") as handle:
    raw = handle.read()
crlf = b"\r\n" in raw
text = raw.decode("utf-8").replace("\r\n", "\n")

if "answer_text_question" in text:
    print("already applied, nothing changed")
    sys.exit(0)

if os.path.exists(REFERENCE):
    with open(REFERENCE, "rb") as handle:
        same = handle.read() == raw
    print("main.py is identical to", REFERENCE if same else "NOT identical to " + REFERENCE + " (informational)")

problems = []
for label, old, new in PLAN:
    count = text.count(old)
    if count != 1:
        problems.append("%s: anchor found %d times" % (label, count))
if problems:
    print("nothing written:")
    for item in problems:
        print(" -", item)
    sys.exit(1)

for label, old, new in PLAN:
    text = text.replace(old, new)
try:
    compile(text, PATH, "exec")
except SyntaxError as exc:
    print("nothing written, syntax error:", exc)
    sys.exit(1)

shutil.copyfile(PATH, BACKUP)
out = text.replace("\n", "\r\n") if crlf else text
with open(PATH, "wb") as handle:
    handle.write(out.encode("utf-8"))
print("patched", len(PLAN), "places | line endings:", "CRLF" if crlf else "LF", "| backup:", BACKUP)