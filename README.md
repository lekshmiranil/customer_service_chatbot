# Real-Time GenAI Customer Service Bot
**Elevance Skills Technology Data Science Internship Project**  
*Built with LangChain, Google Gemini, FAISS, Streamlit, and Multi-Modal Orchestration*

This project provides an end-to-end, enterprise-ready GenAI Customer Service Chatbot designed to assist learners and customers with instant, grounded, and verified support. It combines retrieval-augmented generation (RAG) with a production knowledge pipeline, multimodal image/PDF order verification, structured SLA-aware ticketing, multilingual sentiment escalation, and context-aware session management across six Indic languages.

---

## Quick Start & Usage

### 1. Installation
Clone the repository and install required dependencies in a Python 3.11 environment:

```bash
git clone https://github.com/lekshmiranil/customer_service_chatbot.git
cd customer_service_chatbot_LLM
pip install -r requirements.txt
```

### 2. Environment Configuration
Create a `.env` file in the root folder with your Google Gemini API key and optional configurations (see `.env.example` for all defaults):

```bash
GOOGLE_API_KEY="your_api_key_here"
```

### 3. Launching the Chatbot
Start the Streamlit application from the project root:

```bash
streamlit run src/main.py
```

The web application opens automatically in your browser. On first startup, if no vector index exists, it automatically initializes the knowledge base from `dataset/staging/`.

---

## Project Architecture & Package Structure

```
customer_service_chatbot_LLM/
├── src/
│   ├── main.py                       # Streamlit UI & integrated orchestration engine
│   ├── langchain_helper.py           # FAISS index builder, QA chain, confidence scoring
│   ├── calibrate_threshold.py        # Confidence threshold calibration tool
│   ├── pipeline/                     # Task 1: Production Knowledge Base Pipeline
│   ├── multimodal/                   # Task 2: Multimodal Image, OCR & PDF Analysis
│   ├── tickets/                      # Task 3: Structured Support Ticket Automation
│   ├── rag/                          # Task 4: Secure RAG Knowledge Assistant
│   ├── sentiment/                    # Task 5: Multilingual Sentiment & Escalation
│   └── multilingual/                 # Task 6: Multilingual Sessions & Understanding
├── config/                           # SLA, routing, language & threshold configurations
├── dataset/                          # Staging, raw, quarantine, and quality evaluation sets
├── rag_corpus/                       # 22 versioned policy, FAQ & troubleshooting documents
├── uploads/                          # Temporary customer attachments (time-limited)
├── logs/                             # System metrics, access audit, and ticket event logs
└── tests/ & evaluation runners       # 51 standalone unit/integration test scripts + 5 eval runners
```

---

## Task 1: Production Knowledge Base Pipeline

The pipeline in `src/pipeline` maintains, monitors, and updates the chatbot's vector database automatically with strict quality gating, access control, and rollback guarantees.

### Key Capabilities
- **Incremental Staging & Deduplication:** Computes SHA-256 hashes of incoming documents in `dataset/raw/`. Unchanged documents and identical content under different filenames are skipped.
- **Sanitization & Quarantine:** Empty documents, unsupported file formats, and documents containing prompt-injection attempts are automatically isolated in `dataset/quarantine/` without disrupting the pipeline. Sensitive PII (emails, cards, phones) is masked before staging.
- **Snapshot Versioning & Rollback:** Before any update, the active index is snapshotted under `faiss_versions/v{N}`. The system supports one-command CLI rollback to any historical snapshot.
- **Pre-Activation Quality Gate:** Updates are built into a candidate index (`faiss_candidate`) and tested against `dataset/eval_qa.json`. Updates scoring below 70% accuracy or lower than `dataset/quality_baseline.json` are rejected and rolled back immediately.
- **Maintenance Window Enforcement:** Approved updates are held until the configured maintenance window (`MAINTENANCE_WINDOW_START` to `MAINTENANCE_WINDOW_END`, e.g., 02:00–04:00) before atomic activation into `faiss_index/`.
- **Health Check & Auto-Rollback:** Following activation, the pipeline monitors health queries for 300 seconds. If an infrastructure or index error is detected, it automatically restores the previous version.
- **Access Control & Telemetry:** CLI commands require role tokens (`admin`, `pipeline`, `viewer`). Metrics (latencies, p95, confidence, failure rate, escalations) are logged to `logs/metrics.jsonl`.

### CLI Admin & Verification
```bash
# Check pipeline status and available versions
python src/pipeline/admin.py status --token <token>

# Manually trigger a pipeline update attempt
python src/pipeline/admin.py run --token <token>

# Roll back the active index to a specific snapshot
python src/pipeline/admin.py rollback 1 --token <token>

# View performance summary metrics
python src/pipeline/admin.py report --token <token>
```

---

## Task 2: Multimodal Customer Support

Located in `src/multimodal`, this layer allows customers to upload receipts, order screenshots, delivery invoices, and PDFs to corroborate support inquiries.

### Key Capabilities
- **Format Inspection & Sanitization:** Accepts PNG, JPG, JPEG, and PDF (up to 5MB). PyMuPDF inspects PDF object tables to block active content (JavaScript, launch actions, URI redirects), password-protected PDFs, and pixel bombs. Images are normalized and stripped of EXIF metadata.
- **OCR Field Extraction:** Uses Tesseract OCR with adaptive rotation and contrast thresholding (`fields.py`) to extract Order IDs, transaction dates, monetary amounts, and error codes without hallucination.
- **Evidence Cross-Validation:** `compare.py` cross-checks extracted values against customer message statements. If values conflict or image quality is degraded, the bot requests clarification or a clearer screenshot instead of guessing.
- **Visual Injection Screening:** A secondary faint-text pass inspects contrast boundaries to detect and reject hidden adversarial instructions embedded in images.
- **30-Second Processing Budget:** If processing exceeds `PROCESSING_BUDGET_SECONDS` (30s), requests move to a background `ThreadPoolExecutor`, notifying the customer with non-blocking progress checks.
- **Auto-Retention Sweep:** Files and JSON metadata sidecars expire after `UPLOAD_RETENTION_HOURS` (24h) and are purged automatically by a background sweeper.

### Checks
```bash
python eval_run.py
```
*Executes all 11 evaluation scenarios (blurred, mismatched, delayed, expired, injection) and outputs `eval_results.md`.*

---

## Task 3: Support Ticket Automation

Located in `src/tickets`, unresolved customer issues are converted into structured, SLA-monitored support tickets stored in SQLite (`ticket_data/tickets.db`).

### Key Capabilities
- **Automated Triggers:** Raised on low model confidence, QA errors, repeated failed file processing, customer explicit request, or unresolved sentiment timeout.
- **Field Extraction:** Gathers customer name, order ID, issue category, stated vs. inferred details, and contact method. Renders an interactive form in Streamlit when mandatory details are missing.
- **5-Factor Dynamic Priority:** Calculates priority points across severity, impact, sentiment, waiting time, and SLA consumption with guaranteed floors for critical issues and SLA breaches.
- **Intelligent Routing & Availability:** Assigns tickets to agents based on required skills, active business hours, on-call status, and workload balance.
- **Business-Hours SLA Engine:** Computes deadlines skipping configured weekends and holidays. Emits automated warnings at 75% consumed time and escalates on breaches.
- **Duplicate & Group Detection:** Links repeated customer inquiries within 72 hours; groups related incidents sharing orders, products, or error codes.
- **Redacted Handoffs:** Outputs sanitized, agent-ready markdown summaries with masked PII.

### Checks
```bash
python eval_tickets_run.py
```
*Runs 20 end-to-end scenarios and updates `eval_results_tickets.md`.*

---

## Task 4: Secure RAG Knowledge Assistant

Located in `src/rag`, provides grounded, cited answers over product documents, FAQs, policies, and troubleshooting guides.

### Key Capabilities
- **Strict Sidecar Metadata:** Requires `<doc_id>.meta.json` defining versions, products, regions, access levels, and effective/expiry date ranges.
- **Access Control & Multi-Tenancy:** Pre-filters documents by access rank (`public`, `customer`, `internal`, `restricted`). Refusal responses are identical to prevent permission probing.
- **Temporal & Conflict Resolution:** Specific regional documents take precedence over GLOBAL documents, followed by latest effective date and version. Expired or future policies are ignored for current questions; historical questions retrieve policies active on the specified date.
- **Unsupported-Claim Detection:** Deterministic verifier checks every sentence for citation validity, 80% word support in source chunks, number preservation, and negation alignment.
- **Prompt Injection Quarantine:** Quarantines adversarial document chunks and strips instruction sentences from incoming queries.

### Checks
```bash
python make_rag_corpus.py
python eval_rag_run.py
```
*Evaluates 48 scenarios across conflicts, historical dates, access boundaries, and injections.*

---

## Task 5: Multilingual Sentiment & Escalation

Located in `src/sentiment`, analyzes tone, history, and urgency to adjust chatbot demeanor and manage escalations.

### Key Capabilities
- **6-Label Classifier:** Flags positive, neutral, negative, frustrated, urgent, and sarcastic tones in English, Hindi, and Malayalam (native script and Roman transliteration).
- **History Context & Sarcasm:** Flags sarcasm when praise follows repeated complaint messages. Repeated negative messages dynamically raise frustration scores.
- **Calm High-Risk Detection:** Immediately escalates account compromise, double charges, and legal threats even when phrased politely.
- **Policy Preservation:** Sentiment adjustments only modify opening empathetic greetings; core policy answers and sources remain strictly unmodified.
- **Queue Orchestration:** Urgent after-hours complaints enter `on_call`; normal complaints schedule for `next_working_day`. Unresolved negative conversations past 15 minutes trigger automatic escalation.

### Checks
```bash
python eval_sentiment_run.py
```
*Evaluates 34 scenarios and outputs `eval_results_sentiment.md`.*

---

## Task 6: Multilingual Understanding & Sessions

Located in `src/multilingual`, delivers customer support across 6 Indic languages (English, Hindi, Malayalam, Tamil, Telugu, Kannada) in both native script and Roman transliteration.

### Key Capabilities
- **Entity Preservation:** Preserves order IDs (`ORD-12345`), product SKUs, dates, and customer names exactly as typed.
- **Clause-Level Intent Parsing:** Deconstructs complex inputs into up to 3 distinct intents, handling spelling errors and transliterated vernacular.
- **Session Lifecycle:** Active sessions time out after 30 minutes of inactivity. Returning within 24 hours restores conversation summaries; returning after 24 hours starts a fresh session.
- **Multi-Tenant Session Isolation:** Simultaneous customer sessions are isolated in SQLite (`session_data/sessions.db`).
- **Dynamic Language Packs:** Supports hot-loading new language configurations from `config/languages/` without modifying core code.

### Checks
```bash
python eval_multilingual_run.py
```
*Executes evaluation across assistant-written, user-written, and unseen conversation suites.*

---

## Running the Complete Automated Test Suite

To run all 51 standalone unit and regression tests:

```bash
# Run individual test files:
python test_tickets_calendar.py
python test_compare.py
python test_rag_verify.py
python test_sentiment_classify.py
python test_multilingual_session.py

# Or run all evaluation suites:
python eval_run.py
python eval_tickets_run.py
python eval_rag_run.py
python eval_sentiment_run.py
python eval_multilingual_run.py
```
