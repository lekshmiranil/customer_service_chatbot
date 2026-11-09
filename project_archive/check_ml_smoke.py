import sys

sys.stdout.reconfigure(errors="backslashreplace")

from src.multilingual import config, languages, intents, entities

cfg = config.get_config()
thr = cfg["thresholds"]

samples = [
    ("en", "where is my order ORD-12345"),
    ("hi", "mera order kab aayega"),
    ("ml", "ente order evide"),
    ("ta", "en order eppo varum"),
    ("te", "naa order ekkada undi"),
    ("kn", "nanna order yelli ide"),
    ("mixed", "mera order ORD-12345 refund chahiye please"),
    ("short", "and the refund?"),
]

for label, text in samples:
    try:
        det = languages.detect(text, cfg)
        ana = intents.analyze(text, det["languages"], thr)
        ents = entities.extract(text, cfg)
        print(label, ascii(text))
        print("  lang:", det["language"], det["confidence"], "mixed:", det["mixed"], "langs:", det["languages"])
        print("  intents:", [(r["intent"], r["score"]) for r in ana["requests"]],
              "ambiguous:", ana["ambiguous"], "confidence:", ana["confidence"])
        print("  entities:", [(i["type"], i["value"]) for i in ents["items"]]
              if isinstance(ents, dict) else [(i["type"], i["value"]) for i in ents])
    except Exception as exc:
        print(label, "ERROR", type(exc).__name__, ascii(str(exc)))