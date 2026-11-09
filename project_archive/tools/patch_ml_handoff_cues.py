"""Adds Roman Malayalam words for a person to the human_agent cues in src\\multilingual\\lexicon_cues.py.
Finds the ml line inside the human_agent block, checks that there is exactly one, compiles the result and writes
nothing on any mismatch."""
import sys

PATH = "src/multilingual/lexicon_cues.py"
NEW_WORDS = "manushyan manushya manushyanod manushyanodu agent "


def main():
    try:
        with open(PATH, "r", encoding="utf-8", newline="") as handle:
            raw = handle.read()
    except OSError as error:
        print("FAIL cannot read", PATH, error)
        return 1
    crlf = "\r\n" in raw
    lines = raw.replace("\r\n", "\n").split("\n")
    if any(NEW_WORDS in line for line in lines):
        print("FAIL already patched; nothing written")
        return 1
    starts = [i for i, line in enumerate(lines) if line.strip() == '"human_agent": {']
    if len(starts) != 1:
        print("FAIL human_agent block found", len(starts), "times; nothing written")
        return 1
    block = range(starts[0] + 1, min(starts[0] + 14, len(lines)))
    hits = [i for i in block if lines[i].strip().startswith('"ml": _c("')]
    if len(hits) != 1:
        print("FAIL ml line found", len(hits), "times in the human_agent block; nothing written")
        return 1
    line = lines[hits[0]]
    if line.count('_c("') != 1:
        print("FAIL unexpected line shape; nothing written")
        return 1
    lines[hits[0]] = line.replace('_c("', '_c("' + NEW_WORDS, 1)
    text = "\n".join(lines)
    try:
        compile(text, PATH, "exec")
    except SyntaxError as error:
        print("FAIL the result does not compile:", error, "; nothing written")
        return 1
    if text.count(NEW_WORDS) != 1:
        print("FAIL marker count is wrong; nothing written")
        return 1
    with open(PATH, "w", encoding="utf-8", newline="") as handle:
        handle.write(text.replace("\n", "\r\n") if crlf else text)
    print("ok   patched", PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())