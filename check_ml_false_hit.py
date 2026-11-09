import inspect
import sys

sys.stdout.reconfigure(errors="backslashreplace")

from src.multilingual import intents, session_store

text = "please send more later"
index = intents._build(["en"])
keys = intents._keys(text)
print("tokens:", keys)
for intent, spec in index.items():
    for position, token in enumerate(keys):
        for cue in spec["words"]:
            weight = intents._match(token, cue, 0.8)
            if weight:
                print("word hit:", intent, "| token", ascii(token), "| cue", ascii(cue), "| weight", round(weight, 3))
    for phrase in spec["phrases"]:
        size = len(phrase)
        for start in range(len(keys) - size + 1):
            weights = [intents._match(keys[start + k], phrase[k], 0.8) for k in range(size)]
            if all(weights):
                print("phrase hit:", intent, ascii(phrase), round(min(weights), 3))

print("---- find_restorable")
print(inspect.getsource(session_store.find_restorable))
print("---- _within_window")
print(inspect.getsource(session_store._within_window))