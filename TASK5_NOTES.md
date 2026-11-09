# Task 5 notes: sentiment analysis and escalation

## Scope
Multilingual (English, Hindi, Malayalam) sentiment, risk and escalation layer in `src/sentiment`. It adjusts tone only and never changes business policy text.

## Design
- Labels: positive, neutral, negative, frustrated, urgent, sarcastic. Each has a score from 0 to 1. A label is flagged at 0.4 or more. The primary label is the highest flagged score, with sarcastic, frustrated, urgent, negative, positive as the tie order.
- History: praise after two negative-type messages becomes likely sarcasm. A negative message after two or more negative-type messages raises frustration.
- High-risk detection is separate from sentiment: account compromise, duplicate payment, legal threat.
- Complaint: a negative, frustrated or sarcastic message, an urgent message, or a high-risk message.
- Escalation conditions: repeated_negative (3 negative-type among the last 5 customer messages), high_risk:<category>, unresolved_timeout (negative for more than 15 minutes, strictly greater).
- The clock stops on a human reply or a customer message that says the issue is solved or says thanks. Escalation fires once per condition per stretch.
- Queues: business open means priority_support. Closed and urgent (or high-risk) means on_call. Closed and normal means next_working_day, scheduled for the next business opening from the Task 3 calendar.
- Every row stores reason, activated condition and a masked summary.
- Time is always an argument, so simulated clocks work. A naive time is treated as UTC.

## Assumptions
- A high-risk issue received outside business hours is treated as urgent. `HIGH_RISK_IS_URGENT` in `escalation.py` reverses this.
- A complaint is also an urgent message without negative wording.
- The conversation summary holds label history, risk categories, elapsed negative time and a masked excerpt of the last message.

## Evaluation
`python eval_sentiment_run.py` runs 35 scenarios with a fixed clock and writes `eval_results_sentiment.md`. Categories: sarcasm, calm high-risk, after hours, time change, repeated negative.

## Known limits
- Rule-based sarcasm detection misses subtle sarcasm, and praise next to a real complaint can be flagged as sarcasm.
- Hindi and Malayalam cue lists are limited and were not reviewed by a native speaker.
- Roman-script Hindi or Malayalam gets English tone lines.
- Task 3 routing is unchanged. Its on-call rule uses its own urgency test.
- The 15-minute notice appears on the next page run, because Streamlit only reruns on interaction.
- SENTIMENT_NOW is for testing only. Running the app later with the real clock can create timeout rows for old test conversations.