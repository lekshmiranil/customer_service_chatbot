import os

from dotenv import load_dotenv

from src.langchain_helper import get_vectordb, retrieval_confidence

load_dotenv()

IN_SCOPE = [
    "Is there an EMI option?",
    "Do you offer installment payments?",
    "What if I don't like this bootcmp?",
    "Can I get a refund if I leave the bootcamp?",
    "Do I get lifetime access to the course material?",
    "Will I have access to recordings after the course ends?",
    "Do you provide any virtual internship?",
    "Is there an internship included with the program?",
    "What is the minimum RAM required for the laptop?",
    "How much memory should my laptop have?",
]

OUT_OF_SCOPE = [
    "What is the weather in Mumbai today?",
    "Who won the cricket match yesterday?",
    "What is the capital of France?",
    "Give me a recipe for biryani",
    "What is the current price of gold?",
    "Tell me a joke",
    "How do I fix my car engine?",
    "Who is the prime minister of India?",
    "Do you offer a medical coding course?",
    "Can I enroll in a cooking class?",
    "What is the salary of a data scientist in Bangalore?",
    "Do you sell laptops?",
    "Can you help me file my income tax return?",
    "Which bootcamp is better, yours or a competitor's?",
    "How do I reset my email password?",
    "What is the history of the Mughal empire?",
]

THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.4"))

db = get_vectordb()


def score_all(queries):
    results = [(retrieval_confidence(db, q), q) for q in queries]
    return sorted(results, reverse=True)


in_scores = score_all(IN_SCOPE)
out_scores = score_all(OUT_OF_SCOPE)

print(f"\nThreshold in use: {THRESHOLD}\n")
print("IN-SCOPE (should be answered):")
for score, query in in_scores:
    flag = "ANSWERED " if score >= THRESHOLD else "ESCALATED"
    print(f"  {score:.3f} {flag} | {query}")

print("\nOUT-OF-SCOPE (should escalate):")
for score, query in out_scores:
    flag = "ESCALATED" if score < THRESHOLD else "ANSWERED "
    print(f"  {score:.3f} {flag} | {query}")

lowest_in = min(score for score, _ in in_scores)
highest_out = max(score for score, _ in out_scores)
wrongly_escalated = sum(1 for score, _ in in_scores if score < THRESHOLD)
wrongly_answered = sum(1 for score, _ in out_scores if score >= THRESHOLD)

print(f"\nLowest in-scope score:    {lowest_in:.3f}")
print(f"Highest out-of-scope score: {highest_out:.3f}")
print(f"In-scope escalated at {THRESHOLD}: {wrongly_escalated} of {len(in_scores)}")
print(f"Out-of-scope answered at {THRESHOLD}: {wrongly_answered} of {len(out_scores)}")

if lowest_in > highest_out:
    midpoint = (lowest_in + highest_out) / 2
    print(f"\nClean separation. Gap: {lowest_in - highest_out:.3f}. Midpoint threshold: {midpoint:.3f}")
else:
    print("\nNo clean separation: some in-scope scores are at or below some out-of-scope scores.")
    print("Retrieval alone cannot separate them, so any threshold trades missed answers against wrong answers.")