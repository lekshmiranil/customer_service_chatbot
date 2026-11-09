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


# Delete expired uploads now, then keep sweeping in the background.

CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.4"))

st.title("Customer Service Chatbot")

if not os.path.exists(INDEX_PATH):
    with st.spinner("Creating vector database..."):
        create_vector_db()

@st.cache_resource(max_entries=1)
def start_retention_sweeper():
    """Starts the background sweep once per server process."""
    return start_sweeper()


# Delete expired uploads now, then keep sweeping in the background.
purge_expired()
start_retention_sweeper()


@st.cache_resource(max_entries=1)
def load_resources(index_version):
    """Loaded once, and reloaded whenever the pipeline activates or rolls back an index."""
    vectordb = get_vectordb()
    return vectordb, get_qa_chain(vectordb)


vectordb, chain = load_resources(get_index_version())


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

outcome = st.session_state.get("file_outcome")
result_area = st.container()  # the result is drawn here, above the Check result button

if outcome is not None and outcome.state == "queued":
    if st.button("Check result"):
        outcome = check_job(outcome.job_id)
        st.session_state["file_outcome"] = outcome

if outcome is not None:
    with result_area:
        show_outcome(outcome)