
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