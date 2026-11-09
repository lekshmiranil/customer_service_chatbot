"""Loads the knowledge corpus: documents + sidecar metadata -> clean, labelled chunks.

Rules enforced here:
  * a document without a valid sidecar is rejected (and reported), never half-loaded
  * metadata comes only from the sidecar, never from text inside the document
  * a chunk that trips the injection scan is quarantined; the rest of the document loads
  * HTML comments are not visible content: they are scanned but never become chunks
"""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from src.rag.injection_scan import normalize_for_scan, scan_text
from src.rag.metadata import MetadataError, DocMeta, load_sidecar

DOC_SUFFIXES = (".md", ".txt")
MAX_CHUNK_CHARS = 700
_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*)$")
_COMMENT = re.compile(r"<!--(.*?)-->", re.DOTALL)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])")


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    version: str
    section: str
    text: str
    meta: DocMeta


@dataclass
class Corpus:
    docs: list = field(default_factory=list)         # DocMeta of loaded documents
    chunks: list = field(default_factory=list)       # clean Chunk objects
    quarantined: list = field(default_factory=list)  # dicts: where, which rules (never the text)
    rejected: list = field(default_factory=list)     # dicts: file, errors
    products: dict = field(default_factory=dict)     # slug -> {"name":..., "aliases":[...]}


def load_products(corpus_dir):
    path = Path(corpus_dir) / "products.json"
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    products = {}
    for slug, info in raw.items():
        aliases = [a.lower() for a in info.get("aliases", [])] + [slug.lower()]
        products[slug] = {"name": info.get("name", slug), "aliases": sorted(set(aliases))}
    return products


def _blocks(text):
    """Returns [(section, block_text)]: one block per paragraph or list item."""
    blocks = []
    section = ""
    lines = []          # lines of the block being built
    is_item = False     # the block being built is a list item

    def close():
        if lines:
            blocks.append((section, " ".join(lines).strip()))
            lines.clear()

    for line in text.splitlines():
        heading = _HEADING.match(line)
        if heading:
            close()
            section = heading.group(2).strip()
            is_item = False
            continue
        if not line.strip():
            close()
            is_item = False
            continue
        bullet = _LIST_ITEM.match(line)
        if bullet:
            close()
            lines.append(bullet.group(1).strip())
            is_item = True
        elif lines and (not is_item or line.startswith((" ", "\t"))):
            lines.append(line.strip())
        else:
            close()
            lines.append(line.strip())
            is_item = False
    close()
    return blocks


def _split_long(text):
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]
    parts, current = [], ""
    for sentence in _SENTENCE_SPLIT.split(text):
        if current and len(current) + 1 + len(sentence) > MAX_CHUNK_CHARS:
            parts.append(current)
            current = sentence
        else:
            current = (current + " " + sentence).strip()
    if current:
        parts.append(current)
    return parts


def _load_document(doc_path, meta, corpus):
    raw = doc_path.read_text(encoding="utf-8-sig")
    comment_rules = []
    for comment in _COMMENT.findall(raw):
        comment_rules.extend(scan_text(comment))
    if comment_rules:
        corpus.quarantined.append({
            "doc_id": meta.doc_id, "version": meta.version, "chunk_no": 0,
            "section": "(html comment)", "rules": sorted(set(comment_rules)),
        })
    visible = _COMMENT.sub("\n", raw)
    number = 0
    for section, block in _blocks(visible):
        block = normalize_for_scan(block)
        if not block:
            continue
        section_rules = scan_text(section)
        for piece in _split_long(block):
            number += 1
            rules = sorted(set(scan_text(piece) + section_rules))
            if rules:
                corpus.quarantined.append({
                    "doc_id": meta.doc_id, "version": meta.version, "chunk_no": number,
                    "section": section, "rules": rules,
                })
                continue
            corpus.chunks.append(Chunk(
                chunk_id=f"{meta.doc_id}@{meta.version}#{number}",
                doc_id=meta.doc_id, version=meta.version,
                section=section or meta.title, text=piece, meta=meta))


def load_corpus(corpus_dir):
    """Loads every document. A doc_id + version that appears twice is rejected in BOTH files:
    which copy is the real one cannot be decided safely, and file order must never decide it."""
    corpus_dir = Path(corpus_dir)
    corpus = Corpus(products=load_products(corpus_dir))
    doc_files = sorted(p for p in corpus_dir.glob("*") if p.suffix.lower() in DOC_SUFFIXES)

    loaded = []  # (path, meta)
    for doc_path in doc_files:
        try:
            loaded.append((doc_path, load_sidecar(doc_path.with_suffix(".meta.json"))))
        except MetadataError as exc:
            corpus.rejected.append({"file": doc_path.name, "errors": [str(exc)]})

    counts = {}
    for _, meta in loaded:
        counts[meta.key] = counts.get(meta.key, 0) + 1

    for doc_path, meta in loaded:
        problems = []
        if counts[meta.key] > 1:
            problems.append(f"duplicate doc_id and version {meta.doc_id} v{meta.version}: all copies rejected")
        if corpus.products and meta.product != "all" and meta.product not in corpus.products:
            problems.append(f"unknown product '{meta.product}' (not in products.json)")
        if problems:
            corpus.rejected.append({"file": doc_path.name, "errors": problems})
            continue
        corpus.docs.append(meta)
        _load_document(doc_path, meta, corpus)

    for sidecar in sorted(corpus_dir.glob("*.meta.json")):
        stem = sidecar.name[: -len(".meta.json")]
        if not any((corpus_dir / (stem + suffix)).exists() for suffix in DOC_SUFFIXES):
            corpus.rejected.append({"file": sidecar.name, "errors": ["sidecar has no document file"]})
    return corpus