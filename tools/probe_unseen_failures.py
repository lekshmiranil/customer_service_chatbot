"""Probe: what the dialogue layer returns for unseen_04, unseen_06 and unseen_07. Measurement only.
Run from the project root: python -m tools.probe_unseen_failures"""
from src.multilingual import config, dialogue, summary

CFG = config.get_config()
SHOW = ("kind", "language", "confidence", "mixed", "switched", "intents", "query", "queries", "reason", "resolved_from")


def run(messages):
    state = summary.empty_state("en")
    for text in messages:
        state, result = dialogue.handle_message(state, text, CFG, "")
        print("MSG  ", ascii(text))
        print("     ", ascii({k: result.get(k) for k in SHOW if k in result}))
        print("      result keys:", ascii(sorted(result)))
    print("      slots:", ascii(state.get("slots")))
    print()


run(["mujhe refund chahiye for order ORD-33902 please"])
run(["I am Anitha Menon, my order ORD-84120 placed on 3 March 2026 needs a refund"])
run(["where is my order ORD-19001", "and that one?"])