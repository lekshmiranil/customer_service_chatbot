import os
import time
import uuid
import streamlit as st

from langchain_helper import (
    INDEX_PATH,
    create_vector_db,
    get_vectordb,
    get_qa_chain,
    get_index_version,
    retrieval_confidence,
)
from pipeline.security import mask_sensitive_data, detect_prompt_injection
from pipeline.metrics import record
from multimodal.service import accept_and_submit
from multimodal.intake import UploadRejected, UploadUnavailable, purge_expired

# Below this retrieval confidence, the answer is flagged for a human agent.
# The default is a starting point: calibrate it against real questions.
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.4"))

st.title("Customer Service Chatbot")

# Retention cleanup runs as the app is used; get_upload also checks expiry
# immediately before background processing, so queued expired files are refused.
purge_expired()

if not os.path.exists(INDEX_PATH):
    with st.spinner("Creating vector database..."):
        create_vector_db()


@st.cache_resource(max_entries=1)
def load_resources(index_version):
    """Loaded once, and reloaded whenever the pipeline activates or rolls back an index."""
    vectordb = get_vectordb()
    return vectordb, get_qa_chain(vectordb)


vectordb, chain = load_resources(get_index_version())

user_question = st.text_input("Ask a question:")

uploaded_file = st.file_uploader("Attach a screenshot, invoice, PDF, or product image", type=["png", "jpg", "jpeg", "pdf"])
if st.button("Submit attachment", disabled=uploaded_file is None):
    message = user_question or ""
    try:
        stored, future = accept_and_submit(uploaded_file.name, uploaded_file.getvalue(), message)
        job_id = uuid.uuid4().hex[:8]
        st.session_state.setdefault("upload_jobs", {})[job_id] = {
            "future": future,
            "started": time.monotonic(),
        }
        st.session_state["latest_upload_job"] = job_id
        st.info(f"File accepted. Processing reference: {job_id}.")
    except UploadRejected as error:
        st.error(error.customer_message)
    except Exception:
        st.error("The file could not be accepted. Please upload a supported, readable file.")

job_id = st.session_state.get("latest_upload_job")
job = st.session_state.get("upload_jobs", {}).get(job_id) if job_id else None
if job:
    future = job["future"]
    if future.done():
        try:
            st.write(future.result())
        except UploadUnavailable as error:
            st.info(error.customer_message)
        except UploadRejected as error:
            st.error(error.customer_message)
        except Exception:
            st.error("File processing could not be completed. Please try again with a clearer file.")
        st.caption(f"Processing reference: {job_id}")
    elif time.monotonic() - job["started"] >= 30:
        st.info(f"Your file is still processing in the background. Check status with reference {job_id}.")
        if st.button("Refresh processing status"):
            st.experimental_rerun()
    else:
        st.info(f"Your file is being processed. Reference: {job_id}.")

if user_question:
    # Masked text is what gets sent to the LLM and what gets logged
    safe_question = mask_sensitive_data(user_question)
    start = time.time()

    if detect_prompt_injection(user_question):
        record(
            "query",
            question=safe_question[:200],
            latency_ms=round((time.time() - start) * 1000),
            confidence=None,
            failed=False,
            escalated=True,
            reason="injection_blocked",
        )
        st.error("Your message couldn't be processed. Please rephrase your question.")
    else:
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
            st.write(response.get("result", response))
            if escalated:
                st.info("I'm not fully confident in this answer, so your question has been flagged for a human agent.")
        except Exception as e:
            record(
                "query",
                question=safe_question[:200],
                latency_ms=round((time.time() - start) * 1000),
                confidence=None,
                failed=True,
                escalated=True,
                reason="error",
            )
            st.error("Something went wrong while answering. Your question has been flagged for a human agent.")
