"""Decides WHICH documents may be used for a question. Pure metadata logic, no ranking.

Order of filters (each later step only sees what the earlier steps allowed):
  1. access   the user's role must reach the document's access level
  2. region   the document's region must be the user's region or GLOBAL
  3. date     the document must be in force on the date being asked about
  4. product  only when the question names a product
  5. conflict one winner per (topic, product): region-specific beats GLOBAL, then the latest
              effective date, then the highest version. A full tie holds the group back as ambiguous.
Unauthorised documents are removed first, so they can never influence the outcome
(not even through counts or clarification questions shown to the user).
"""
import re
from dataclasses import dataclass, field

from src.rag.metadata import can_access, version_key


@dataclass(frozen=True)
class UserContext:
    role: str = "public"
    region: str = "GLOBAL"   # GLOBAL here means "region not specified"


@dataclass
class Resolution:
    as_of: object = None
    winners: dict = field(default_factory=dict)  # (topic, product) -> DocMeta
    held: dict = field(default_factory=dict)     # (topic, product) -> {"reason": ..., "docs": [DocMeta]}
    excluded: dict = field(default_factory=dict) # counts per reason, for logs only

    def winner_keys(self):
        return {group: meta.key for group, meta in self.winners.items()}


def detect_products(question, catalog):
    """Product slugs named in the question (whole-word alias match). Empty = none named."""
    text = " " + re.sub(r"[^a-z0-9]+", " ", (question or "").lower()).strip() + " "
    found = []
    for slug, info in (catalog or {}).items():
        for alias in info["aliases"]:
            alias_text = " " + re.sub(r"[^a-z0-9]+", " ", alias).strip() + " "
            if alias_text in text:
                found.append(slug)
                break
    return found


def _rank(meta):
    return (0 if meta.region == "GLOBAL" else 1, meta.effective_date, version_key(meta.version))


def resolve(docs, ctx, as_of, products=None):
    """Returns a Resolution for one date. `products` is a list of slugs named in the question."""
    excluded = {"access": 0, "region": 0, "not_yet_effective": 0, "expired": 0, "product": 0, "superseded": 0}
    groups = {}
    region_known = ctx.region != "GLOBAL"
    for meta in docs:
        if not can_access(ctx.role, meta.access_level):
            excluded["access"] += 1
            continue
        if products and meta.product != "all" and meta.product not in products:
            excluded["product"] += 1
            continue
        status = meta.status_on(as_of)
        if status == "future":
            excluded["not_yet_effective"] += 1
            continue
        if status == "expired":
            excluded["expired"] += 1
            continue
        groups.setdefault((meta.topic, meta.product), []).append(meta)

    result = Resolution(as_of=as_of, excluded=excluded)
    for group, members in groups.items():
        if region_known:
            applicable = [m for m in members if m.region in ("GLOBAL", ctx.region)]
            excluded["region"] += len(members) - len(applicable)
        else:
            applicable = [m for m in members if m.region == "GLOBAL"]
            has_regional = any(m.region != "GLOBAL" for m in members)
            if has_regional:
                # A regional variant is in force but the user's region is unknown: the answer
                # could be wrong for them, so hold the group back and ask.
                result.held[group] = {"reason": "needs_region", "docs": list(members)}
                continue
        if not applicable:
            continue
        best = max(_rank(m) for m in applicable)
        top = [m for m in applicable if _rank(m) == best]
        excluded["superseded"] += len(applicable) - len(top)
        if len(top) > 1:
            result.held[group] = {"reason": "ambiguous", "docs": top}
        else:
            result.winners[group] = top[0]
    return result


def chunk_ids_for(corpus_chunks, metas):
    keys = {m.key for m in metas}
    return {c.chunk_id for c in corpus_chunks if (c.doc_id, c.version) in keys}