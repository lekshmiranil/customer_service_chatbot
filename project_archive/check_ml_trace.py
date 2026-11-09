import linecache
import sys

sys.stdout.reconfigure(errors="backslashreplace")

from src.multilingual import config, dialogue, summary

cfg = config.get_config()
state = summary.empty_state("en")
state, first = dialogue.handle_message(state, "hello", cfg)

events = []


def tracer(frame, event, arg):
    if not frame.f_code.co_filename.endswith("dialogue.py"):
        return None
    if event in ("line", "return"):
        kind = type(arg).__name__ if event == "return" else ""
        events.append((frame.f_code.co_name, event, frame.f_lineno, kind))
    return tracer


sys.settrace(tracer)
try:
    out = dialogue.handle_message(state, "mera order ORD-12345 kab aayega", cfg)
finally:
    sys.settrace(None)

print("result type:", type(out).__name__)
for name, event, lineno, kind in events[-14:]:
    text = linecache.getline(dialogue.__file__, lineno).strip()
    print(name, event, lineno, kind, "|", ascii(text))