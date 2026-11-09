import os
import sys
import time
from pathlib import Path

import streamlit as st

# Streamlit puts the script's folder (src) on sys.path, not the project root.
# The multimodal modules import "src.xxx", so the root must be on the path too.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

INDEX_PATH = str(PROJECT_ROOT / "faiss_index")

from langchain_helper import (
    create_vector_db,
    get_vectordb,
    get_qa_chain,
    get_index_version,
    retrieval_confidence,
)
from pipeline.security import mask_sensitive_data, detect_prompt_injection
from pipeline.metrics import record
from src.multimodal.intake import purge_expired
from src.multimodal.orchestrator import RequestOutcome, check_job, handle_request
from src.multimodal.retention import start_sweeper
from src.tickets.chat_bridge import (
    FAILED_FILE_STATUSES,
    UNRESOLVED_FILE_STATUSES,
    bot_turn,
    customer_notice,
    customer_turn,
    file_trigger,
    new_conversation_id,
    submit_to_tickets,
    text_trigger,
)
from src.tickets.workflow import start_reconciler

CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.4"))
HUMAN_FOLLOW_UP_STATUSES = tuple(UNRESOLVED_FILE_STATUSES) + tuple(FAILED_FILE_STATUSES)
MAX_SESSION_TURNS = 60

st.title("Customer Service Chatbot")
ticket_area = st.container()  # the support ticket notice and reply box are drawn here, at the end of the run

if not os.path.exists(INDEX_PATH):
    with st.spinner("Creating vector database..."):
        create_vector_db()


@st.cache_resource(max_entries=1)
def start_retention_sweeper():
    """Starts the background sweep once per server process."""
    return start_sweeper()


@st.cache_resource(max_entries=1)
def start_ticket_reconciler():
    """Starts the background SLA and routing reconciler once per server process."""
    return start_reconciler()


# Delete expired uploads now, then keep sweeping in the background.
purge_expired()
start_retention_sweeper()
try:
    start_ticket_reconciler()
except Exception:
    pass  # a ticket background problem must never stop the chatbot


@st.cache_resource(max_entries=1)
def load_resources(index_version):
    """Loaded once, and reloaded whenever the pipeline activates or rolls back an index."""
    vectordb = get_vectordb()
    return vectordb, get_qa_chain(vectordb)


vectordb, chain = load_resources(get_index_version())

# ---------------------------------------------------------------- ticket session state
st.session_state.setdefault("conversation_id", new_conversation_id())
st.session_state.setdefault("turns", [])
st.session_state.setdefault("unresolved_files", 0)


def add_turn(turn):
    st.session_state["turns"].append(turn)
    del st.session_state["turns"][:-MAX_SESSION_TURNS]


def raise_ticket(trigger):
    """Creates or updates this conversation's ticket and remembers the result for display."""
    result = submit_to_tickets(
        st.session_state["conversation_id"], list(st.session_state["turns"]), trigger
    )
    st.session_state["ticket_result"] = result
    if "error" not in result:
        st.session_state["ticket_open"] = True
    return result


def record_text_exchange(question, answer):
    """Remembers a text exchange for the ticket and raises a ticket when the trigger rules say so."""
    if answer["kind"] == "blocked":
        return  # blocked messages are never stored or ticketed
    exchange = [customer_turn(question), bot_turn(str(answer["text"]))]
    trigger = text_trigger(answer, question)
    ticket_open = st.session_state.get("ticket_open", False)
    if trigger is None and not ticket_open:
        st.session_state["previous_exchange"] = exchange
        return
    if trigger == "customer_unresolved" and not ticket_open and not st.session_state["turns"]:
        for turn in st.session_state.get("previous_exchange", []):
            add_turn(turn)  # so the ticket describes the real problem, not just "this didn't help"
    for turn in exchange:
        add_turn(turn)
    st.session_state["previous_exchange"] = exchange
    if trigger is not None:
        raise_ticket(trigger)


def record_file_result(file_outcome):
    """Remembers a finished file result once, and raises a ticket when the trigger rules say so."""
    sequence = st.session_state.get("file_seq", 0)
    if file_outcome is None or file_outcome.state != "done":
        return
    if st.session_state.get("file_recorded_seq") == sequence:
        return
    st.session_state["file_recorded_seq"] = sequence
    if file_outcome.status == "rejected":
        return  # unsafe files are never stored or ticketed
    attachment = {
        "file_id": f"upload-{sequence}",
        "status": file_outcome.status,
        "kind": st.session_state.get("file_kind", "file"),
    }
    message = st.session_state.get("file_message", "") or "(attached a file)"
    trigger, count = file_trigger(file_outcome.status, st.session_state.get("unresolved_files", 0))
    st.session_state["unresolved_files"] = count
    if file_outcome.status == "confirmed" and not st.session_state.get("ticket_open"):
        st.session_state["turns"] = []  # a confirmed file closes the unresolved stretch
        return
    add_turn(customer_turn(message, attachment=attachment))
    add_turn(bot_turn(file_outcome.reply))
    if trigger is not None:
        raise_ticket(trigger)


def show_ticket_notice():
    result = st.session_state.get("ticket_result")
    if result is None:
        return
    if "error" in result:
        st.warning(customer_notice(result))
    else:
        st.info(customer_notice(result))


def answer_question(question):
    """Run one question through the chain; called once per distinct question."""
    safe_question = mask_sensitive_data(question)
    start = time.time()

    if detect_prompt_injection(question):
        record(
            "query",
            question_chars=len(question),
            latency_ms=round((time.time() - start) * 1000),
            confidence=None,
            failed=False,
            escalated=True,
            reason="injection_blocked",
        )
        return {
            "question": question,
            "kind": "blocked",
            "text": "Your message couldn't be processed. Please rephrase your question.",
            "escalated": True,
        }

    try:
        confidence = retrieval_confidence(vectordb, safe_question)
        response = chain.invoke({"query": safe_question})
        latency_ms = round((time.time() - start) * 1000)
        escalated = confidence < CONFIDENCE_THRESHOLD
        record(
            "query",
            question_chars=len(question),
            latency_ms=latency_ms,
            confidence=confidence,
            failed=False,
            escalated=escalated,
            reason="low_confidence" if escalated else None,
        )
        return {
            "question": question,
            "kind": "answer",
            "text": response.get("result", response),
            "escalated": escalated,
        }
    except Exception:
        record(
            "query",
            question_chars=len(question),
            latency_ms=round((time.time() - start) * 1000),
            confidence=None,
            failed=True,
            escalated=True,
            reason="error",
        )
        return {
            "question": question,
            "kind": "error",
            "text": "Something went wrong while answering. Your question has been flagged for a human agent.",
            "escalated": True,
        }


STATUS_DISPLAY = {
    "confirmed": st.success,
    "conflict": st.warning,
    "needs_confirmation": st.warning,
    "needs_better_file": st.warning,
    "rejected": st.error,
    "busy": st.error,
    "failed": st.error,
    "unavailable": st.error,
}


def show_outcome(outcome):
    """Show one file result in the style that matches its status."""
    STATUS_DISPLAY.get(outcome.status, st.info)(outcome.reply)


# ---------------------------------------------------------------- text flow
user_question = st.text_input("Ask a question:", key="main_user_question_input")

if user_question:
    # Reruns and button clicks reuse the stored answer, so they spend no Gemini quota.
    answer = st.session_state.get("last_answer")
    if answer is None or answer["question"] != user_question:
        with st.spinner("Looking that up..."):
            answer = answer_question(user_question)
        st.session_state["last_answer"] = answer
        record_text_exchange(user_question, answer)  # runs once per new answer

    if answer["kind"] == "answer":
        st.write(answer["text"])
        if answer["escalated"]:
            st.info("This answer had low confidence and has been flagged for a human agent.")
    elif answer["kind"] == "blocked":
        st.warning(answer["text"])
    else:
        st.error(answer["text"])
        if st.button("Try this question again"):
            st.session_state.pop("last_answer", None)
            st.experimental_rerun()

# ---------------------------------------------------------------- file flow
st.markdown("---")
st.subheader("Attach a file")
with st.form("attachment_form"):
    attachment_message = st.text_area(
        "What is the problem with this order? (optional)", key="attachment_message"
    )
    uploaded_file = st.file_uploader(
        "Attach a screenshot, invoice, PDF, or product image",
        type=["png", "jpg", "jpeg", "pdf"],
        key="file_upload_widget",
    )
    submitted = st.form_submit_button("Submit attachment")

if submitted:
    if uploaded_file is None:
        st.warning("Please choose a file first.")
    else:
        with st.spinner("Reading your file..."):
            try:
                outcome = handle_request(
                    attachment_message or "", uploaded_file.name, uploaded_file.getvalue()
                )
            except Exception:
                outcome = RequestOutcome(
                    state="done",
                    status="failed",
                    reply="The file could not be processed. Please try again with a supported, readable file.",
                )
        st.session_state["file_outcome"] = outcome
        st.session_state["file_message"] = attachment_message or ""
        st.session_state["file_kind"] = Path(uploaded_file.name).suffix.lstrip(".").lower() or "file"
        st.session_state["file_seq"] = st.session_state.get("file_seq", 0) + 1
        st.session_state.pop("poll_started", None)

outcome = st.session_state.get("file_outcome")
result_area = st.container()  # the result is drawn here

POLL_SECONDS = 3
POLL_LIMIT_SECONDS = 120
keep_polling = False

if outcome is not None and outcome.state == "queued":
    started = st.session_state.setdefault("poll_started", time.time())
    checked = check_job(outcome.job_id)
    if checked.state == "done":
        # Only replace the background notice once the real result exists.
        outcome = checked
        st.session_state["file_outcome"] = outcome
    keep_polling = outcome.state == "queued" and (time.time() - started) < POLL_LIMIT_SECONDS
    if outcome.state == "queued":
        if keep_polling:
            st.caption("Checking automatically. The result will appear here when it is ready.")
        else:
            st.button("Check result")  # clicking reruns the page, which checks the job again

record_file_result(outcome)  # once per finished file result

if outcome is not None:
    with result_area:
        show_outcome(outcome)
    if (
        outcome.state == "done"
        and outcome.status in HUMAN_FOLLOW_UP_STATUSES
        and not st.session_state.get("ticket_open")
    ):
        if st.button("Ask a human to follow up", key="ask_human_button"):
            raise_ticket("customer_requested")

# ---------------------------------------------------------------- support ticket
with ticket_area:
    notice_slot = st.container()
    if st.session_state.get("ticket_open") and (st.session_state.get("ticket_result") or {}).get("missing"):
        with st.form("ticket_reply_form", clear_on_submit=True):
            ticket_reply = st.text_area(
                "Add details to your ticket (for example your order number or how to reach you):",
                key="ticket_reply_text",
            )
            reply_submitted = st.form_submit_button("Send to support")
        if reply_submitted:
            if not ticket_reply.strip():
                st.warning("Please type a message first.")
            elif detect_prompt_injection(ticket_reply):
                st.warning("Your message couldn't be processed. Please rephrase it.")
            else:
                add_turn(customer_turn(ticket_reply))
                raise_ticket("customer_reply")  # goes to the ticket only; no Gemini call
                st.experimental_rerun()
    with notice_slot:
        show_ticket_notice()

if keep_polling:
    time.sleep(POLL_SECONDS)
    st.experimental_rerun()