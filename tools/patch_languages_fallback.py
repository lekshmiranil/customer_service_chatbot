"""One-time patch for src\\multilingual\\languages.py: supported_languages() falls back to ['en'] when no configured
language is usable, and detect() validates default_language. Verifies anchors, compiles, backs up first."""
import os
import shutil
import sys
import time

TARGET = os.path.join("src", "multilingual", "languages.py")
BACKUPS = "backups"


def refuse(message):
    print("REFUSED: " + message + "; nothing was written")
    sys.exit(1)


SUP_OLD = '''def supported_languages(cfg):
    return [code for code in cfg.get("languages", []) if code in lexicon.LANG_NAMES]
'''
SUP_NEW = '''def supported_languages(cfg):
    found = [code for code in cfg.get("languages", []) if code in lexicon.LANG_NAMES]
    return found or ["en"]  # a list with no usable language must not leave the layer without one
'''
DEF_OLD = '''    default = cfg.get("default_language", "en")
'''
DEF_NEW = '''    default = cfg.get("default_language", "en")
    if default not in supported:
        default = supported[0]
'''

if not os.path.isfile(TARGET):
    refuse(TARGET + " not found; run from the project root")
with open(TARGET, "r", encoding="utf-8", newline="") as handle:
    source = handle.read()
if 'return found or ["en"]' in source or "if default not in supported:" in source:
    refuse("languages.py already contains the fallback")
crlf = "\r\n" in source


def fit(text):
    return text.replace("\n", "\r\n") if crlf else text


edits = []
for label, old, new in (("supported_languages", SUP_OLD, SUP_NEW), ("default", DEF_OLD, DEF_NEW)):
    old_fit = fit(old)
    count = source.count(old_fit)
    if count != 1:
        refuse("anchor '%s' found %d times (expected 1)" % (label, count))
    edits.append((source.index(old_fit), old_fit, fit(new)))

result = source
for position, old_fit, new_fit in sorted(edits, reverse=True):
    result = result[:position] + new_fit + result[position + len(old_fit):]

try:
    compile(result, TARGET, "exec")
except SyntaxError as error:
    refuse("patched source does not compile: %s" % error)

os.makedirs(BACKUPS, exist_ok=True)
backup = os.path.join(BACKUPS, "languages.py.before_fallback_" + time.strftime("%Y%m%d_%H%M%S") + ".bak")
shutil.copy2(TARGET, backup)
with open(TARGET, "w", encoding="utf-8", newline="") as handle:
    handle.write(result)
print("ok: patched " + TARGET)
print("ok: backup " + backup)