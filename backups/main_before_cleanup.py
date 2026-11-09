import os
import sys
import time
from pathlib import Path
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.multimodal.intake import purge_expired
from src.multimodal.orchestrator import RequestOutcome, check_job, handle_request

import streamlit as st

# Streamlit puts the script's folder (src) on sys.path, not the project root.
# The multimodal modules import "src.xxx", so the root must be on the path too.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

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
from customer_service_chatbot_LLM.src.orchestrator import RequestOutcome, check_job, handle_request
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.4"))

st.title("Customer Service Chatbot")

if not os.path.exists(INDEX_PATH):
    with st.spinner("Creating vector database..."):
        create_vector_db()
# Delete uploads past the retention period when the app starts.
# A scheduled sweep is added in the next step.
purge_expired()

@st.cache_resource(max_entries=1)
def load_resources(index_version):
    """Loaded once, and reloaded whenever the pipeline activates or rolls back an index."""
    vectordb = get_vectordb()
    return vectordb, get_qa_chain(vectordb)


vectordb, chain = load_resources(get_index_version())

user_question = st.text_input("Ask a question:", key="main_user_question_input")

if user_question:
    st.session_state.messages.append({"role": "user", "content": user_question})
    
    with st.chat_message("user"):
        st.write(user_question)

    with st.chat_message("assistant"):
        # Check if we have an uploaded file to process through the orchestrator
        if uploaded_file is not None and not st.session_state.get("file_processed", False):
            # Pass message and file data to local orchestrator pipeline
            outcome = handle_request(user_question, uploaded_file.name, uploaded_file.getvalue())
            response_text = outcome.reply
            st.session_state.file_processed = True
            if outcome.status in ["needs_confirmation", "conflict"]:
                st.session_state.awaiting_confirmation = True
        elif st.session_state.get("awaiting_confirmation", False) and uploaded_file is not None:
            # Handle confirmation response with the orchestrator
            outcome = handle_request(user_question, uploaded_file.name, uploaded_file.getvalue())
            response_text = outcome.reply
            st.session_state.awaiting_confirmation = False
        else:
            # Fall back to standard RAG vector search
            ans = answer_question(user_question)
            response_text = ans["text"]

        st.write(response_text)
        st.session_state.messages.append({"role": "assistant", "content": response_text})

def answer_question(question):
    """Run one question through the chain; called once per distinct question."""
    safe_question = mask_sensitive_data(question)
    start = time.time()

    if detect_prompt_injection(question):
        record(
            "query",
            question=safe_question[:200],
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
            question=safe_question[:200],
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
            question=safe_question[:200],
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


# 1. File uploader widget definition (usually higher up in your sidebar or main layout)
uploaded_file = st.file_uploader("Upload a file", type=["png", "jpg", "jpeg", "pdf"], key="file_upload_widget")

# Track if a new file was uploaded
if uploaded_file is not None:
    # Check if this is a new file compared to what we last processed
    if st.session_state.get("last_uploaded_file") != uploaded_file.name:
        st.session_state.last_uploaded_file = uploaded_file.name
        st.session_state.file_processed = False
        st.session_state.awaiting_confirmation = False

# 2. Inside your user input submission block:
if user_question:
    st.session_state.messages.append({"role": "user", "content": user_question})
    
    with st.chat_message("user"):
        st.write(user_question)

    with st.chat_message("assistant"):
        orch = st.session_state.get("orchestrator")
        
        # Route based on conversation state
        if st.session_state.get("awaiting_confirmation", False) and orch:
            response = orch.handle_response(user_question)
            st.session_state.awaiting_confirmation = False
        elif uploaded_file is not None and not st.session_state.get("file_processed", False) and orch:
            # Pass the uploaded file object or its bytes/path to the orchestrator
            response = orch.handle_request(user_question, uploaded_file)
            st.session_state.file_processed = True
            st.session_state.awaiting_confirmation = True
        else:
            response = get_qa_chain(user_question)
            
        st.write(response)
        st.session_state.messages.append({"role": "assistant", "content": response})
st.markdown("---")
st.subheader("Attach a file")
attachment_message = st.text_area("What is the problem with this order? (optional)", key="attachment_message")
uploaded_file = st.file_uploader(
    "Attach a screenshot, invoice, PDF, or product image",
    type=["png", "jpg", "jpeg", "pdf"],
)

if uploaded_file is not None and st.button("Submit attachment"):
    with st.spinner("Reading your file..."):
        try:
            outcome = handle_request(attachment_message or "", uploaded_file.name, uploaded_file.getvalue())
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