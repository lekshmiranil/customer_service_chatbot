"""Pure-Python BM25 search over clean chunks. No model load, no network, deterministic."""
import math
import re
from collections import Counter
from dataclasses import dataclass

STOPWORDS = frozenset((
    "a an the is are was were be been am do does did can could would should will shall may might "
    "i me my we our you your he she it its they them their this that these those of to in on at by "
    "for from with about as into than then so if or and but not no what which who whom whose when where "
    "why how there here any some all tell please give show know need want get have has had also just "
    "much many more most other such only own same too very"
).split())


def _collapse(word):
    """cancelled -> cancell -> cancel, shipping -> shipp -> ship (same rule for question and document)."""
    if len(word) > 3 and word[-1] == word[-2] and word[-1].isalpha():
        return word[:-1]
    return word


def stem(word):
    if len(word) > 5 and word.endswith("ing"):
        word = word[:-3]
    elif len(word) > 4 and word.endswith("ied"):
        word = word[:-3] + "y"
    elif len(word) > 4 and word.endswith("ies"):
        word = word[:-3] + "y"
    elif len(word) > 4 and word.endswith("ed"):
        word = word[:-2]
    elif len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        word = word[:-1]
    return _collapse(word)


def tokenize(text):
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return [stem(w) for w in words if w not in STOPWORDS]


@dataclass(frozen=True)
class Hit:
    chunk: object
    score: float
    matched_terms: frozenset
    query_terms: frozenset
    matched_weight: float = 0.0
    query_weight: float = 0.0

    @property
    def coverage(self):
        """Share of the question's content weight found in this chunk. Rare words count more than
        common ones, and words found in no document at all count as rare."""
        if self.query_weight > 0:
            return self.matched_weight / self.query_weight
        return len(self.matched_terms) / len(self.query_terms) if self.query_terms else 0.0


class BM25Index:
    K1 = 1.5
    B = 0.75

    def __init__(self, chunks):
        self.chunks = list(chunks)
        self._by_id = {c.chunk_id: c for c in self.chunks}
        self._tf = {}
        self._len = {}
        doc_freq = Counter()
        for chunk in self.chunks:
            tokens = tokenize(f"{chunk.meta.title} {chunk.section} {chunk.text}")
            counts = Counter(tokens)
            self._tf[chunk.chunk_id] = counts
            self._len[chunk.chunk_id] = max(len(tokens), 1)
            doc_freq.update(counts.keys())
        total = max(len(self.chunks), 1)
        self._avg_len = sum(self._len.values()) / total
        self._idf = {
            term: math.log(1 + (total - freq + 0.5) / (freq + 0.5)) for term, freq in doc_freq.items()
        }
        self._max_idf = max(self._idf.values()) if self._idf else math.log(1 + (total + 0.5) / 0.5)

    def search(self, question, allowed_chunk_ids=None, k=5):
        """Ranks only the allowed chunks (all when None). Chunks matching no term are dropped."""
        terms = set(tokenize(question))
        if not terms:
            return []
        query_weight = sum(self._idf.get(term, self._max_idf) for term in terms)
        hits = []
        for chunk_id, counts in self._tf.items():
            if allowed_chunk_ids is not None and chunk_id not in allowed_chunk_ids:
                continue
            matched = terms & counts.keys()
            if not matched:
                continue
            length_norm = 1 - self.B + self.B * self._len[chunk_id] / self._avg_len
            score = 0.0
            for term in matched:
                tf = counts[term]
                score += self._idf.get(term, 0.0) * tf * (self.K1 + 1) / (tf + self.K1 * length_norm)
            matched_weight = sum(self._idf.get(term, 0.0) for term in matched)
            hits.append(Hit(self._by_id[chunk_id], round(score, 6), frozenset(matched), frozenset(terms),
                            matched_weight, query_weight))
        hits.sort(key=lambda h: (-h.score, h.chunk.chunk_id))
        return hits[:k]