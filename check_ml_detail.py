import sys

sys.stdout.reconfigure(errors="backslashreplace")

from src.multilingual import config, entities, intents, languages

cfg = config.get_config()
thr = cfg["thresholds"]

print("== detect with a session language")
for text, session in [("ok", "ta"), ("yes", "ta"), ("thanks", "ml"), ("hmm", "hi")]:
    d = languages.detect(text, cfg, session_language=session)
    print(ascii(text), session, "->", d["language"], d["confidence"], "inherited:", d.get("inherited"), "langs:", d["languages"])

print("== spelling")
for text in ["wher is my ordr", "wheres my ordr", "wer is my oder", "i want refnd", "where is my order"]:
    a = intents.analyze(text, ["en"], thr)
    print(ascii(text), a["requests"], "ambiguous:", a["ambiguous"], "unknown:", a["unknown"], "conf:", a["confidence"])

print("== names")
for text in ["my name is Anu Menon, order ORD-12345", "my name is Anu Menon", "my name is Anu", "mera naam Anu hai", "this is Anu Menon"]:
    f = entities.extract(text, cfg)
    print(ascii(text), "names:", ascii(f["names"]))

print("== config")
print("intents_need_order:", cfg["intents_need_order"], "max_requests:", cfg["max_requests"])
print("thresholds:", thr)