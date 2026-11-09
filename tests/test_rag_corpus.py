"""Checks for src\\rag\\corpus_loader.py: loading, rejection rules and chunk labelling."""
import json
import sys
import tempfile
from pathlib import Path

from make_rag_corpus import DOCS, write_corpus
from src.rag.corpus_loader import load_corpus

failures = 0
total = 0


def check(name, condition):
    global failures, total
    total += 1
    if condition:
        print(f"PASS {name}")
    else:
        failures += 1
        print(f"FAIL {name}")


def meta_json(**changes):
    raw = {
        "doc_id": "T-1", "title": "T", "doc_type": "faq", "topic": "test-topic", "version": "1",
        "product": "homehub", "region": "GLOBAL", "access_level": "public",
        "effective_date": "2025-01-01", "expiry_date": None,
    }
    raw.update(changes)
    return json.dumps(raw)


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    check("generator reports document count", write_corpus(root) == len(DOCS))
    corpus = load_corpus(root)
    check("every generated document loads", len(corpus.docs) == len(DOCS))
    check("no generated document is rejected", corpus.rejected == [])
    check("products load", set(corpus.products) == {"homehub", "careplus"})
    check("product aliases are lowercase", all(a == a.lower() for p in corpus.products.values() for a in p["aliases"]))
    check("chunks exist", len(corpus.chunks) > 20)
    check("chunk ids are unique", len({c.chunk_id for c in corpus.chunks}) == len(corpus.chunks))
    check("every chunk carries full metadata", all(c.meta.doc_id == c.doc_id and c.meta.version == c.version for c in corpus.chunks))
    check("chunk ids name document and version", all(c.chunk_id.startswith(f"{c.doc_id}@{c.version}#") for c in corpus.chunks))
    check("every chunk has a section", all(c.section for c in corpus.chunks))
    check("sections come from headings", any(c.section == "Refund window" for c in corpus.chunks))
    check("headings are not chunks", not any(c.text.startswith("#") for c in corpus.chunks))
    restricted = [c for c in corpus.chunks if c.doc_id == "RST-DISC-GL"]
    check("body text cannot change access level", restricted and all(c.meta.access_level == "restricted" for c in restricted))
    check("footer text with fake access level still loads as plain text",
          any("access_level: public" in c.text for c in restricted))
    check("expired documents still load for historical questions",
          any(c.doc_id == "POL-REF-GL" and c.version == "1" for c in corpus.chunks))
    check("future documents still load", any(c.doc_id == "POL-REF-GL" and c.version == "3" for c in corpus.chunks))

    # rejection rules
    (root / "NOSIDE_v1.md").write_text("# No sidecar\n## A\nSome text.\n", encoding="utf-8")
    (root / "BADDATE_v1.md").write_text("# Bad\n## A\nSome text.\n", encoding="utf-8")
    (root / "BADDATE_v1.meta.json").write_text(meta_json(doc_id="BADDATE", effective_date="2025-13-01"), encoding="utf-8")
    (root / "DUP_v1.md").write_text("# Dup\n## A\nSome text.\n", encoding="utf-8")
    (root / "DUP_v1.meta.json").write_text(meta_json(doc_id="POL-REF-GL", version="2"), encoding="utf-8")
    (root / "BADPROD_v1.md").write_text("# Prod\n## A\nSome text.\n", encoding="utf-8")
    (root / "BADPROD_v1.meta.json").write_text(meta_json(doc_id="BADPROD", product="toaster"), encoding="utf-8")
    (root / "ORPHAN_v1.meta.json").write_text(meta_json(doc_id="ORPHAN"), encoding="utf-8")
    (root / "BROKEN_v1.md").write_text("# Broken\n## A\nSome text.\n", encoding="utf-8")
    (root / "BROKEN_v1.meta.json").write_text("{oops", encoding="utf-8")
    corpus = load_corpus(root)
    rejected = {r["file"]: " ".join(r["errors"]) for r in corpus.rejected}
    check("missing sidecar rejected", "NOSIDE_v1.md" in rejected)
    check("bad date rejected", "BADDATE_v1.md" in rejected and "effective_date" in rejected["BADDATE_v1.md"])
    check("duplicate id and version rejected", "DUP_v1.md" in rejected and "duplicate" in rejected["DUP_v1.md"])
    check("the other copy of a duplicate is rejected too", "POL-REF-GL_v2.md" in rejected and "duplicate" in rejected["POL-REF-GL_v2.md"])
    check("no copy of a duplicate is loaded", not any(d.key == ("POL-REF-GL", "2") for d in corpus.docs))
    check("no chunk of a duplicate is loaded", not any(c.doc_id == "POL-REF-GL" and c.version == "2" for c in corpus.chunks))
    check("unknown product rejected", "BADPROD_v1.md" in rejected and "unknown product" in rejected["BADPROD_v1.md"])
    check("orphan sidecar reported", "ORPHAN_v1.meta.json" in rejected)
    check("broken JSON rejected", "BROKEN_v1.md" in rejected)
    check("rejected documents add no chunks", not any(c.doc_id in ("BADDATE", "DUP", "BADPROD", "BROKEN", "NOSIDE") for c in corpus.chunks))

    # chunking
    long_text = "# Long\n## Details\n" + " ".join(f"Sentence number {i} explains one more detail." for i in range(60)) + "\n"
    (root / "LONG_v1.md").write_text(long_text, encoding="utf-8")
    (root / "LONG_v1.meta.json").write_text(meta_json(doc_id="LONG"), encoding="utf-8")
    (root / "LIST_v1.md").write_text("# List\n## Items\n- First item.\n- Second item.\n  continued here.\n", encoding="utf-8")
    (root / "LIST_v1.meta.json").write_text(meta_json(doc_id="LIST"), encoding="utf-8")
    corpus = load_corpus(root)
    long_chunks = [c for c in corpus.chunks if c.doc_id == "LONG"]
    check("long paragraph is split", len(long_chunks) > 1)
    check("no chunk exceeds the limit", all(len(c.text) <= 700 for c in long_chunks))
    list_chunks = [c.text for c in corpus.chunks if c.doc_id == "LIST"]
    check("each list item is its own chunk", len(list_chunks) == 2)
    check("indented continuation joins its item", list_chunks[1] == "Second item. continued here.")

check("empty folder loads as empty corpus", load_corpus(Path(tempfile.mkdtemp())).docs == [])

print(f"checks: {total}, failed: {failures}")
sys.exit(1 if failures else 0)