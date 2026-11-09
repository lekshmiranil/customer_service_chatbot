"""Probe, not a test: prints how the layer treats Roman Malayalam requests for a person. Changes nothing."""
from src.multilingual import config, dialogue, summary

CFG = config.get_config()
PHRASES = [
    "enikk oru manushyanodu samsarikkanam",
    "enikk oru manushyanod samsarikkanam",
    "manushyanod samsarikkanam",
    "ningal oru manushyan aano enikk oru manushyanod samsarikkanam",
    "manushyanod samsarikkan avasaram tharaamo?",
    "manushyan aano?",
    "enikk oru manushya jeeviyod samsarikkanam",
]
for text in PHRASES:
    state, result = dialogue.handle_message(summary.empty_state("en"), text, CFG)
    print(ascii(text))
    print("   kind", result.get("kind"), "| reason", ascii(result.get("reason")), "| language", result.get("language"),
          "| languages", result.get("languages"), "| confidence", result.get("language_confidence"),
          "| intents", result.get("intents"), "| escalated", result.get("escalated"))