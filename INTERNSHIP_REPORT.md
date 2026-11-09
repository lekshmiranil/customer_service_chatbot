# Elevance Skills Technology Data Science Internship Report

**Project Title:** Learn To Build A Real-Time GenAI Customer Service Bot  
**Internship Role:** Data Science & AI/ML Engineering Intern  
**Internship Organization:** Elevance Skills Technology / NullClass E-Learning  
**Date of Submission:** November 2026  

---

## 1. Introduction

Customer service operations represent one of the most operationally demanding functions in digital e-learning and software platforms. Modern e-learning platforms such as NullClass interact with thousands of concurrent learners across multiple communication channels including Discord servers, web portals, and email. The primary operational bottleneck stems from repetitive inquiries concerning admissions, course syllabi, refund policies, payment verification, and technical troubleshooting.

This project delivers an enterprise-ready, real-time Generative AI Customer Service Bot. Built upon Google Gemini, LangChain, FAISS, and Streamlit, the system extends beyond a simple question-and-answering bot by incorporating six production-grade engineering modules:
1. **Knowledge Base Pipeline:** Automated document ingestion, quarantine, snapshot versioning, quality gating, scheduled updates, and health-monitored rollbacks.
2. **Multimodal Customer Support:** Tesseract OCR and PyMuPDF document ingestion to extract and corroborate evidence from customer screenshots, invoices, and receipts.
3. **Structured Support Tickets:** An automated ticket lifecycle engine with five-factor dynamic priority scoring, business-hours calendar SLA monitoring, workload-balanced agent routing, and PII-redacted handoff summaries.
4. **Secure RAG Knowledge Assistant:** A deterministic, multi-tenant knowledge assistant with pre-retrieval role-based access control, temporal policy conflict resolution, citation tracking, and unsupported-claim verification.
5. **Multilingual Sentiment and Escalation:** Real-time sentiment, frustration, and sarcasm detection across English, Hindi, and Malayalam, paired with calm high-risk issue detection and after-hours queue orchestration.
6. **Multilingual and Session Management:** Language identification, entity preservation, and multi-turn state persistence across six Indic languages with 30-minute inactivity timeouts and 24-hour summary restoration.

---

## 2. Background

The baseline project began as an educational LangChain and Google PaLM/Gemini question-answering prototype designed to ingest a single FAQ CSV file into a local FAISS vector store. While sufficient for proof-of-concept demonstrations, real-world customer service environments demand strict guarantees:
- Knowledge bases frequently evolve; unverified updates can poison responses or introduce hallucinated policy statements.
- Customers frequently supply visual evidence (bank SMS screenshots, payment receipts, error dialogs) that must be cross-checked against their written claims.
- Complex or unresolved complaints require deterministic escalation into support ticketing systems without violating service level agreements (SLAs).
- Information access must enforce regional policies, role permissions, and historical effective dates.
- Multilingual and regional language queries must be understood without leaking sensitive Personally Identifiable Information (PII) into persistent storage.

To meet these production requirements, six specialized assignments were engineered and integrated into the primary application framework.

---

## 3. Learning Objectives

The internship pursued the following technical and domain competencies:
1. **LLM Orchestration & Grounding:** Architecting retrieval-augmented generation (RAG) pipelines that enforce strict factual grounding, citation traceability, and deterministic hallucination detection.
2. **Production Pipeline Engineering:** Implementing automated document ingestion pipelines featuring SHA-256 deduplication, quarantine isolation, regression quality gating, and rollback capabilities.
3. **Computer Vision & Multimodal Extraction:** Utilizing Optical Character Recognition (OCR) and PDF object inspection to extract structured order entities while mitigating visual prompt-injection attacks.
4. **Algorithmic Workflow & SLA Design:** Constructing deterministic business-hours calendars, multi-factor priority algorithms, and queue assignment state machines.
5. **Security & Data Privacy:** Implementing constant-time HMAC access control, PII redaction across logs and SQLite stores, and safe deserialization practices.
6. **Natural Language Understanding (NLU):** Constructing rule-based multilingual sentiment and clause-level intent parsers resilient to spelling variations, transliteration, and code-switching.

---

## 4. Activities and Tasks

### Task 1: Production Knowledge Base Pipeline
- Engineered `src/pipeline/ingestion.py` to ingest raw documents (`.csv`, `.txt`, `.md`). Utilized SHA-256 content hashing to ensure unchanged files and duplicate documents under distinct names are skipped.
- Integrated automated quarantine for 0-byte files, unsupported file formats, and documents containing adversarial prompt injections.
- Implemented `faiss_versions/` snapshot management and automated rollback functions in `src/pipeline/scheduler.py`.
- Developed `src/pipeline/evaluator.py` to run pre-activation quality checks against `dataset/eval_qa.json`, blocking any release that scores under 70% accuracy or below the deployed baseline in `dataset/quality_baseline.json`.
- Implemented `src/pipeline/maintenance.py` to hold approved updates until the configured maintenance window (e.g., 02:00–04:00) before activating into `faiss_index/`.
- Built post-activation health checks (5-minute observation window) and token-authenticated admin CLI commands (`src/pipeline/admin.py`).

### Task 2: Multimodal Customer Support
- Built `src/multimodal/intake.py` to validate image (PNG, JPG) and PDF attachments up to 5MB. PyMuPDF inspects object dictionaries to neutralize active content (JavaScript, launch actions, URI hooks) and pixel bombs.
- Created `src/multimodal/ocr.py` and `src/multimodal/fields.py` utilizing Tesseract OCR with adaptive rotation and contrast thresholding to extract Order IDs, dates, monetary amounts, and error codes without hallucination.
- Implemented `src/multimodal/compare.py` to cross-validate customer claims against extracted invoice values, returning `confirmed`, `conflict`, or `needs_better_file` statuses.
- Engineered `src/multimodal/injection.py` with visual faint-text analysis to identify and quarantine adversarial instructions embedded in images.
- Designed an asynchronous `ThreadPoolExecutor` budget worker in `src/multimodal/orchestrator.py` that shifts processing taking longer than 30 seconds to the background and notifies the customer.
- Implemented an automated background sweeper in `src/multimodal/retention.py` to delete files and metadata sidecars past the 24-hour retention window.

### Task 3: Structured Support Ticket Automation
- Created `src/tickets/chat_bridge.py` and `src/tickets/extract.py` to convert unresolved conversations into structured support tickets, extracting customer name, order number, product, issue, and contact details while categorizing entries as stated or inferred.
- Formulated a 5-factor priority scoring algorithm in `src/tickets/priority.py` integrating severity, impact, sentiment, waiting time, and SLA consumption with strict priority floors.
- Implemented business-hours routing in `src/tickets/routing.py`, distributing tickets to available agents based on skill sets, active schedules, and capacity load ratios.
- Developed `src/tickets/business_time.py` to exclude weekends and configured company holidays from SLA targets, triggering warnings at 75% elapsed time and escalating upon breaches.
- Built duplicate linking and incident grouping algorithms in `src/tickets/duplicates.py` and implemented PII masking in `src/tickets/handoff.py`.

### Task 4: Secure RAG Knowledge Assistant
- Constructed `src/rag/corpus_loader.py` and `src/rag/index.py` over 22 versioned synthetic policy, FAQ, product, and troubleshooting documents.
- Enforced strict metadata sidecar validation (`<doc_id>.meta.json`) and implemented pre-retrieval role filtering (`public < customer < internal < restricted`) in `src/rag/metadata.py` and `src/rag/policy_select.py`.
- Formulated conflict resolution logic giving priority to regional documents over global policies, followed by latest effective date and version.
- Handled natural language historical date questions (`src/rag/dates_nl.py`), retrieving policies in force on specified dates while rejecting future policy queries.
- Engineered `src/rag/verify.py` to verify every generated line against cited evidence, mandating 80% word support, number preservation, and negation consistency.

### Task 5: Multilingual Sentiment and Escalation
- Developed `src/sentiment/classify.py` to classify messages into six sentiment classes (positive, neutral, negative, frustrated, urgent, sarcastic) across English, Hindi, and Malayalam.
- Implemented multi-turn history tracking in `src/sentiment/history.py` to identify sarcasm when praise follows repeated complaints.
- Created `src/sentiment/risk.py` to detect high-risk scenarios (account compromise, duplicate payment, legal threats) independent of sentiment scores.
- Implemented tone modulation in `src/sentiment/tone.py`, prepending empathetic greetings without modifying underlying factual answers.
- Built queue management in `src/sentiment/escalation.py`, routing urgent complaints outside business hours to `on_call` queues, scheduling normal complaints for the next working day, and escalating conversations unresolved past 15 minutes.

### Task 6: Multilingual and Session Management
- Engineered `src/multilingual/languages.py` supporting English, Hindi, Malayalam, Tamil, Telugu, and Kannada in native and Roman script.
- Developed clause-level intent recognition in `src/multilingual/intents.py` capable of handling up to three requests per turn.
- Built entity preservation in `src/multilingual/entities.py` to retain names, order numbers, dates, and SKUs exactly as entered.
- Implemented SQLite session persistence (`src/multilingual/session_store.py`) enforcing 30-minute inactivity timeouts, 24-hour summary restoration, and multi-tenant session isolation.
- Created `src/multilingual/packs.py` enabling dynamic external language pack loading from `config/languages/`.

---

## 5. Skills and Competencies

| Competency Domain | Specific Technologies & Methodologies Applied |
|---|---|
| **AI/ML & NLP** | LangChain, RetrievalQA, Google Gemini API, HuggingFace Transformers, PyTorch, FAISS vector indexing, BM25 text retrieval, difflib fuzzy matching. |
| **Multimodal Processing** | PyMuPDF structural PDF parsing, Tesseract OCR, Pillow image filtering, Laplacian variance sharpness evaluation, visual faint-text extraction. |
| **Software Architecture** | Streamlit state machine design, SQLite WAL-mode schema design, multi-threaded concurrency, thread pools, daemon schedulers, micro-package modularity. |
| **Security & Privacy** | Regular expression PII redaction, HMAC constant-time token validation, PDF active-content sanitization, adversarial prompt injection filtering, safe deserialization. |
| **Testing & Quality Assurance** | Automated regression testing, simulated clock time manipulation, synthetic evaluation set generation, boundary condition fuzzing. |

---

## 6. Feedback and Evidence

The project was evaluated using automated test scripts and evaluation suites across all functional domains:
- **Comprehensive Standalone Test Suite:** 51 standalone test scripts executed with a **100% pass rate (51/51 passed, 0 failures)**.
- **Multimodal Evaluation Suite (`eval_run.py`):** **11/11 scenarios passed**, verifying clear invoices, blurred images, mismatched dates, delayed asynchronous queue transitions, expired file deletions, and visual prompt injection rejections.
- **Support Ticket Evaluation Suite (`eval_tickets_run.py`):** **20/20 scenarios passed**, verifying duplicate detection, mandatory field prompting, priority floors, SLA business-hour exclusions, 75% warning thresholds, and runtime configuration updates.
- **RAG Knowledge Evaluation Suite (`eval_rag_run.py`):** **48/48 scenarios passed**, verifying multi-tier access rank enforcement, regional conflict overrides, historical date lookups, expired policy exclusions, and citation-to-evidence validation.
- **Sentiment & Escalation Evaluation Suite (`eval_sentiment_run.py`):** **34/34 scenarios passed**, verifying sarcasm detection from history, calm legal threat escalations, after-hours on-call queue routing, and 15-minute unresolved timeouts.
- **Multilingual Evaluation Suite (`eval_multilingual_run.py`):** Verified across assistant-written sets (15/15 passed), multi-customer concurrency tests, and language pack auto-loaders.

---

## 7. Challenges and Solutions

1. **Unreachable Pipeline Completion Marker:**  
   *Challenge:* In `src/pipeline/scheduler.py`, the completion logic was indented after a `continue` statement within a failure block. Consequently, `_clear_marker()` was never invoked, causing subsequent runs to trigger an unintended crash recovery and rollback.  
   *Solution:* Corrected the indentation block, ensuring `_clear_marker()` and `commit_quality_baseline()` execute strictly following successful health check observation.

2. **Premature Production Index Overwriting:**  
   *Challenge:* The pipeline initially built vector updates directly into `faiss_index/` before quality tests and maintenance windows were verified.  
   *Solution:* Re-architected `create_vector_db()` to accept a target path, building updates into an isolated staging directory (`faiss_candidate/`). The active production index is updated via an atomic copy only after quality gates pass and the maintenance window opens.

3. **Adversarial Instructions in Visual Media:**  
   *Challenge:* Attackers can embed low-contrast or faint text instructions inside uploaded receipts to bypass text-based system prompts.  
   *Solution:* Integrated a dual-pass OCR pipeline in `src/multimodal/injection.py`. The secondary pass applies contrast thresholding to amplify faint text along background boundaries, subjecting the extracted tokens to adversarial verb-target regex matching.

4. **Circular Dependencies Between Priority and SLA:**  
   *Challenge:* SLA deadlines influence ticket priority points, but ticket priority determines the assigned SLA target.  
   *Solution:* Designed an objective "SLA class" computed solely from severity and customer impact points, decoupling the initial policy target from dynamic priority scoring.

5. **Indic Language Code-Switching & Entity Corruption:**  
   *Challenge:* Transliterated Hindi and Malayalam queries frequently incorporate English nouns ("refund", "order"), causing naive language detectors to misclassify sentences. Additionally, regex cleaners risked mangling numeric Order IDs.  
   *Solution:* Pre-extracted entities prior to language parsing and weighted Roman Indic cue words higher than common English function words, preserving Order IDs verbatim.

---

## 8. Outcomes and Impact

- **End-to-End Operational Automation:** Transformed a static Q&A demo into an automated customer support platform capable of resolving inquiries, processing visual evidence, and managing support tickets.
- **Guaranteed Factual Grounding:** Eliminated hallucinations through deterministic sentence verification, requiring 80% source word support and verifiable citations for all knowledge base answers.
- **Strict SLA & Regulatory Adherence:** Ensured customer support commitments are met through automated business-hours calculation, proactive 75% warning notifications, and automatic escalations.
- **Zero-Trust Data Protection:** Redacted PII (payment cards, phone numbers, email addresses) across logs, persistent SQLite tables, and agent summaries, minimizing data exposure risks.

---

## 9. Conclusion

The Elevance Skills Technology Data Science Internship project successfully achieved all specified technical requirements and learning objectives. By integrating production-grade pipeline monitoring, multimodal verification, SLA-governed support ticketing, secure RAG retrieval, sentiment analysis, and multilingual session management into a single cohesive Streamlit application, the system demonstrates how Generative AI can be reliably deployed in real-world enterprise environments.
