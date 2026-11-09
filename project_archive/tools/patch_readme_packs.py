"""One-time patch: adds language-pack text and the new tests to the Task 6 section of README.md and fixes one
sentence in TASK6_NOTES.md. Verifies every anchor in both files first, backs up first, refuses on any mismatch."""
import os
import shutil
import sys
import time


def refuse(message):
    print("REFUSED: " + message + "; nothing was written")
    sys.exit(1)


def read(path):
    if not os.path.isfile(path):
        refuse(path + " not found; run from the project root")
    try:
        with open(path, "r", encoding="utf-8", newline="") as handle:
            return handle.read()
    except UnicodeDecodeError:
        refuse(path + " is not valid UTF-8")


README, NOTES = "README.md", "TASK6_NOTES.md"

R1_OLD = "Optional environment variables: MULTILINGUAL_CONFIG_PATH, MULTILINGUAL_DB_PATH, MULTILINGUAL_NOW."
R1_NEW = (
    R1_OLD + " MULTILINGUAL_PACKS_DIR names another folder for language packs.\n\n"
    "Languages: the \"languages\" list in the same file switches languages on or off. A language can be added or "
    "changed without editing Python through a JSON language pack in config\\languages. A pack is validated "
    "completely and an invalid pack is rejected as a whole. A new language must also be listed in \"languages\". "
    "The fields of a pack are described at the top of src\\multilingual\\packs.py. No real pack is installed yet; "
    "the tests use an invented language to check the mechanism, not the quality of any wording."
)
R2_OLD = ", then python eval_multilingual_run.py"
R2_NEW = (
    ", test_multilingual_iam_name.py, test_multilingual_language_config.py, test_multilingual_zero_languages.py, "
    "test_multilingual_force_language.py, test_multilingual_packs.py, test_multilingual_packs_autoload.py"
    + R2_OLD
)
N1_OLD = "and the sixth conversation passes only after the expectation of user_02 was corrected"
N1_NEW = "and the rise to 6/8 is only because the expectation of user_02 was corrected"

readme, notes = read(README), read(NOTES)
if "MULTILINGUAL_PACKS_DIR" in readme:
    refuse("README.md already mentions MULTILINGUAL_PACKS_DIR")

edits = {README: (readme, [(R1_OLD, R1_NEW), (R2_OLD, R2_NEW)]), NOTES: (notes, [(N1_OLD, N1_NEW)])}
results = {}
for path, (source, pairs) in edits.items():
    newline = "\r\n" if "\r\n" in source else "\n"
    updated = source
    for old, new in pairs:
        count = updated.count(old)
        if count != 1:
            refuse("anchor %s in %s found %d times (expected 1)" % (ascii(old[:50]), path, count))
        updated = updated.replace(old, new.replace("\n", newline))
    results[path] = updated

os.makedirs("backups", exist_ok=True)
stamp = time.strftime("%Y%m%d_%H%M%S")
for path, updated in results.items():
    shutil.copy2(path, os.path.join("backups", path + ".before_packs_" + stamp + ".bak"))
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(updated)
    print("ok: patched " + path)