
# Generatve AI Q&A: Question and Answer System Based on Google Palm LLM and Langchain for E-learning company  

This is an end to end LLM project based on Google Palm and Langchain. We are building a Q&A system for an e-learning company called Nullclass.Nullclass sells data related courses and virtual internships. They have thousands of learners who uses discord server or email to ask questions. This system will provide a streamlit based user interface for students where they can ask questions and get answers. 


## Project Highlights

- Use a real CSV file of FAQs that Nullclass company is using right now. 
- Their human staff will use this file to assist their course learners.
- We will build an LLM based question and answer system that can reduce the workload of their human staff.
- Students should be able to use this system to ask questions directly and get answers within seconds



## Installation

1.Clone this repository to your local machine using:

```bash
  git clone https://github.com/aslin72/customer_service_chatbot_LLM.git
```
2.Navigate to the project directory:

```bash
  cd customer_service_chatbot_LLM
```
3. Install the required dependencies using pip:

```bash
  pip install -r requirements.txt
```
4.Acquire an api key through makersuite.google.com and put it in .env file

```bash
  GOOGLE_API_KEY="your_api_key_here"
```
## Usage

1. Run the Streamlit app by executing:
```bash
streamlit run main.py

```

2.The web app will open in your browser.

- To create a knowledebase of FAQs, click on Create Knolwedge Base button. It will take some time before knowledgebase is created so please wait.

- Once knowledge base is created you will see a directory called faiss_index in your current folder

- Now you are ready to ask questions. Type your question in Question box and hit Enter

## Sample Questions
  - Do you guys provide internship and also do you offer EMI payments?
  - Do you have javascript course?
  - Should I learn power bi or tableau?
  - I've a MAC computer. Can I use powerbi on it?
  - I don't see power pivot. how can I enable it?

## Project Structure

- main.py: The main Streamlit application script.
- langchain_helper.py: This has all the langchain code
- requirements.txt: A list of required Python packages for the project.
- .env: Configuration file for storing your Google API key.

## Task 3: Support ticket automation

Unresolved conversations become structured support tickets, are prioritised, routed to agents and tracked against business-hours SLAs. Everything lives in the `src/tickets` package and is wired into `src/main.py`.

### How it works
- **Triggers.** A ticket is created when a text answer has low confidence or errors, when the customer says the issue is not solved or asks for a human, when a file result stays unresolved on the second attempt, when a file job fails, or when the customer clicks "Ask a human to follow up". Blocked messages and rejected files never create tickets. One ticket per conversation.
- **Extraction.** Customer, order, product, issue, evidence and contact details are extracted from customer turns only. Each field is tagged stated or inferred. Missing mandatory fields (default: order number, contact, issue description) are asked for, and a "Send to support" box appears while something is missing.
- **Priority.** Points for severity, customer impact, sentiment, waiting time and SLA consumption, with floors (critical severity is at least high, an SLA warning is at least medium, a breach is at least high). All thresholds are in the configuration.
- **Routing.** Each category maps to a team and skills. An agent must be on that team, have the skills, be available and be under capacity; the lowest workload wins. After hours only critical or escalated tickets may use on-call agents. Otherwise the ticket waits in the fallback queue with a reason code.
- **SLA.** Deadlines skip configured weekends and holidays. One warning at 75 percent of the allowed time, one automatic escalation after a breach, no repeats.
- **Duplicates and grouping.** A repeated request is linked to the open ticket. Related issues get their own ticket in a shared incident. Unrelated issues stay separate.
- **Handoff summary.** A masked summary for the agent. Emails, phone numbers, cards, secrets and ID numbers are masked, and logs hold only ids, statuses and codes.

### Configuration
The configuration file `config/ticket_config.json` is created on first use. Teams, agents, business hours, holidays, SLA targets and priority rules are all in it. Edits apply on the next reconcile (every 60 seconds while the app runs) without a restart. A bad edit keeps the last good configuration.

Environment variables (all optional, see `.env.example`): `TICKET_CONFIG_PATH`, `TICKET_DB_PATH`, `TICKET_LOG_PATH`, `TICKET_RECONCILE_SECONDS`.

### Checks
Close the Streamlit app first, then run from the project root:

    python eval_tickets_run.py

It runs 20 end-to-end scenarios on temporary files and writes `eval_results_tickets.md`. The detailed test scripts are `test_tickets_calendar.py`, `test_tickets_extract_priority.py`, `test_tickets_store_service.py`, `test_tickets_routing_sla.py`, `test_tickets_handoff_workflow.py` and `test_tickets_chat_bridge.py`. Design notes and known limits are in `TASK3_NOTES.md`.

## Task 4: Knowledge assistant

A RAG assistant answers from product documents, FAQs, policies and troubleshooting guides. It runs beside the existing question flow. Turn it on with the sidebar checkbox "Answer from the knowledge base". Everything is in `src/rag`.

### How it works
- **Metadata.** Each document has a `<name>.meta.json` file with doc_id, title, doc_type, topic, version, product, region, access_level, effective_date and expiry_date. A document with a missing or unknown field is rejected. Two files with the same doc_id and version are both rejected.
- **Authorisation.** Access levels are public, customer, internal, restricted. Documents above the selected level are removed first and never influence anything. The refusal text is the same for restricted, missing and wrong-region content.
- **Dates.** Current questions ignore expired and future documents. A historical question uses the document in force on the date given. A future date is refused. A missing or ambiguous date, such as 03/04/2025, leads to a question back to the customer.
- **Conflicts.** For each topic and product: a regional document beats a global one, then the latest effective date, then the highest version. A full tie is refused. If the region is not specified and a regional variant is in force, the bot asks for the region.
- **Injection.** Instruction-like text inside documents is quarantined. Instruction-like sentences in the question are removed. A question made only of instructions is blocked.
- **Answers.** Answers are sentences taken from the documents, each with a citation such as [POL-REF-GL v2, Refund window]. A verifier checks each line for a valid citation, word support, numbers, negation and injection text. Lines that fail are dropped, and if none remain the bot refuses.
- **Optional Gemini.** Gemini may only rephrase approved passages. Its output goes through the same verifier, with the extractive answer as fallback. It is off by default and capped per day.

### Known limits
Search is keyword based (BM25), so "money back" does not match "refund" and the bot refuses instead of guessing. The verifier checks words, numbers, negation and citations, not meaning. English only. Region and access level are demo selectors, not real authentication. The corpus is synthetic.

### Configuration
Optional variables: `RAG_CORPUS_DIR`, `RAG_LOG_PATH`, `RAG_TODAY`, `RAG_GEMINI_DAILY_CAP`, `RAG_GEMINI_MODEL`. See `.env.example`. The log holds statuses and codes only, never question or answer text.

### Checks
Close the Streamlit app first, then run from the project root:

    python make_rag_corpus.py
    python eval_rag_run.py

The evaluation writes `eval_results_rag.md`. Full design notes are in `TASK4_NOTES.md`.

## Task 5: Sentiment analysis and escalation

Each customer message is classified as positive, neutral, negative, frustrated, urgent or sarcastic, with a score for every label and a confidence. English, Hindi and Malayalam are supported, in native script and in Roman letters. The code is in `src/sentiment`, and it is switched by the sidebar checkbox "Sentiment-aware tone and escalation".

### How it works
- **Classifier.** Rule-based cue scoring with no model and no key. The current message is combined with earlier customer messages, so praise after two complaints is treated as likely sarcasm and repeated complaints raise the frustration score.
- **Tone.** Only an opening line is added in front of the answer. The answer text, Sources and refusal wording are never changed.
- **High-risk issues.** Account compromise, duplicate payment and legal threats are detected separately from sentiment, so a calm message still escalates.
- **Escalation rules.** Three negative-type messages among the last five, any high-risk issue, or a negative conversation unresolved for more than 15 minutes. Each rule fires once per conversation stretch. A human reply, or a customer saying it is solved or saying thanks, stops the clock.
- **Queues.** Outside business hours an urgent or high-risk complaint enters the on-call queue and a normal complaint is scheduled for the next working day. Business hours and holidays come from the Task 3 configuration.
- **Record.** Every escalation and queue entry stores the reason, the activated condition and a masked conversation summary in `sentiment_data/sentiment.db`. A ticket is created or updated through the Task 3 ticket system.
- **15-minute rule.** A background check runs every 60 seconds and records the escalation. The customer sees the notice on the next page run.

### Known limits
Rules catch sarcasm patterns but not subtle sarcasm. Hindi and Malayalam cue lists are limited and need native-speaker review. Hindi or Malayalam in Roman letters is answered in English. Task 3 ticket routing is unchanged, so its own on-call rule still applies to the ticket.

### Checks
Close the Streamlit app first, then run from the project root:

    python eval_sentiment_run.py

The evaluation writes `eval_results_sentiment.md`. Design notes are in `TASK5_NOTES.md`.