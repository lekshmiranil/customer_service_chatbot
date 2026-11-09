"""Ticket field extraction, mandatory-field checks and follow-up questions (Task 3).

extract_ticket_fields() reads only the customer's own turns. Every field is tagged:
  "stated"   - the customer wrote it (name, order ID, contact, product, error codes, amounts,
               and the issue description, which is a masked copy of their own words)
  "inferred" - derived from wording (category, severity, impact, sentiment, and the contact
               method when only one contact detail was given); each carries the wording used
Nothing is invented: a value that is not found is left out. The single exception is severity,
which falls back to DEFAULT_SEVERITY with a recorded reason because scoring needs a value.

A turn is a dict: {"role": "customer"|"bot"|"system", "text": str, "at": str (optional),
"attachment": {"file_id": str, "status": str, "kind": str} (optional)}.
"""
import re
from functools import lru_cache

from src.tickets.masking import EMAIL_RE, find_phone_spans, mask_text

STATED = "stated"
INFERRED = "inferred"
DEFAULT_SEVERITY = "medium"
LIST_FIELDS = ("error_codes", "amounts", "other_order_ids")
KEEP_FIRST_FIELDS = ("issue_description",)

ORDER_RES = (
    re.compile(r"(?i)\border(?:\s*(?:id|number|no\.?|num))?(?:\s+is)?\s*[:#]?\s*#?\s*([A-Z]{0,4}-?\d{4,12})(?!\w)"),
    re.compile(r"(?i)\b(ORD-?\d{4,12})(?!\w)"),
)
ERROR_LABELLED_RE = re.compile(r"(?i)\berror(?:\s+code)?\s*[:#]?\s*((?:E-?)?\d{3,5}|0x[0-9A-Fa-f]{4,8})\b")
ERROR_STANDALONE_RE = re.compile(r"\b(E-?\d{3,5})\b")
AMOUNT_RE = re.compile(
    r"(?i)(?:\brs\.?|\binr|\u20b9|\$|\busd|\beur|\u20ac)\s?(\d+(?:,\d{2,3})*(?:\.\d{1,2})?)"
)
NAME_RE = re.compile(
    r"(?i:\bmy name is|\bname\s*:|\bthis is|\bi am|\bi'm)\s+([A-Z][a-z'-]+(?:\s+[A-Z][a-z'-]+){0,2})"
)
NAME_STOPWORDS = {
    "Not", "Very", "Still", "Having", "Writing", "Calling", "Contacting", "Unable", "Really", "So",
    "Extremely", "Quite", "Just", "Sorry", "Frustrated", "Angry", "Upset", "Disappointed", "Order",
    "The", "A", "An", "My", "Your", "Please", "Regarding", "About", "Trying", "Waiting", "Looking",
    "Concerned", "Worried", "Furious", "Unhappy", "Annoyed",
}
CUSTOMER_ID_RE = re.compile(
    r"(?i)\b(?:customer|member|client)\s*(?:id|number|no\.?)\s*(?:is\s*)?[:#]?\s*([A-Za-z0-9-]{4,20})(?!\w)"
)
PRODUCT_RES = (
    re.compile(r"(?i)\b(?:product(?:\s+name)?|item)\s*[:\-]\s*([^\n.,;!?]{2,60})"),
    re.compile(r"(?i)\bproduct\s+(?:name\s+)?is\s+(?:(?:a|an|the)\s+)?([^\n.,;!?]{2,60})"),
    re.compile(
        r"(?i)\b(?:bought|purchased|ordered|received)\s+(?:(?:a|an|the|my|this)\s+)?"
        r"([A-Za-z0-9][A-Za-z0-9 '\-/+]{1,50}?)"
        r"(?=\s+(?:on|from|last|yesterday|today|but|and|which|that|it|is|was|has|have)\b|[.,;!?]|$)"
    ),
)
PRODUCT_NOT_NAMES = {
    "it", "this", "that", "one", "something", "items", "item", "order", "orders", "package", "parcel", "product",
}
METHOD_PATTERNS = (
    (re.compile(
        r"(?i)\b(?:email|e-mail|mail)\s+me\b|\b(?:contact|reach)\s+me\s+(?:by|via|on)\s+(?:email|e-mail)\b"
        r"|\bprefer\w*\s+(?:to\s+be\s+contacted\s+(?:by|via|on)\s+)?(?:email|e-mail)\b"), "email"),
    (re.compile(
        r"(?i)\b(?:call|phone|ring)\s+me\b|\b(?:contact|reach)\s+me\s+(?:by|via|on)\s+(?:phone|call)\b"
        r"|\bprefer\w*\s+(?:a\s+)?(?:phone\s+)?call\b"), "phone"),
    (re.compile(r"(?i)\b(?:text|sms)\s+me\b|\bprefer\w*\s+(?:text|sms)\b"), "sms"),
    (re.compile(r"(?i)\bwhats\s?app\b"), "whatsapp"),
)

CATEGORY_ORDER = ("payment", "refund", "delivery", "product", "technical", "account", "order", "general")
CATEGORY_KEYWORDS = {
    "payment": ("payment", "charged", "paid", "debit*", "credit card", "upi", "transaction", "billing",
                "invoice", "deducted"),
    "refund": ("refund", "money back", "reimburse*", "return", "returned", "cancel*"),
    "delivery": ("delivery", "deliver*", "shipping", "shipped", "courier", "tracking", "not arrived",
                 "hasn't arrived", "never arrived", "package", "parcel", "late", "delay*"),
    "product": ("broken", "damaged", "defect*", "faulty", "wrong item", "missing part", "quality",
                "not working", "stopped working"),
    "technical": ("error", "crash*", "website", "app", "login", "log in", "password", "bug", "checkout",
                  "page", "glitch"),
    "account": ("account", "profile", "otp", "verification", "sign in", "locked out"),
    "order": ("change order", "modify order", "cancel order", "wrong order", "order status",
              "where is my order"),
    "general": (),
}
SEVERITY_KEYWORDS = (
    ("critical", ("fraud*", "unauthorized", "unauthorised", "hacked", "compromised", "data breach",
                  "data leak", "stolen", "identity theft", "safety", "fire", "smoke", "overheat*",
                  "injur*", "allergic", "emergency")),
    ("high", ("charged twice", "double charged", "charged me twice", "money deducted",
              "money was deducted", "payment failed but", "never arrived", "never received",
              "lost package", "wrong item", "damaged", "locked out", "blocked", "urgent*", "asap",
              "immediately", "refund not received", "no response")),
    ("medium", ("delay*", "late", "not working", "stopped working", "problem", "issue", "missing",
                "error", "not received", "didn't receive", "cannot", "can't", "unable")),
    ("low", ("question", "how do i", "how can i", "wondering", "information", "feedback", "suggestion",
             "update my address", "change my address")),
)
IMPACT_KEYWORDS = (
    ("widespread", ("everyone", "all customers", "all users", "many customers", "many users",
                    "site is down", "website is down", "app is down", "nobody can", "no one can", "outage")),
    ("account_wide", ("all my orders", "all of my orders", "every order", "whole account",
                      "entire account", "locked out")),
    ("multiple_orders", ("two orders", "both orders", "several orders", "multiple orders")),
)
VERY_NEGATIVE_WORDS = ("furious", "outraged", "unacceptable", "worst", "terrible", "disgusting", "scam",
                       "fed up", "sue", "lawyer", "legal action", "never again", "useless", "ridiculous",
                       "horrible", "pathetic")
NEGATIVE_WORDS = ("disappointed", "frustrated", "frustrating", "annoyed", "annoying", "upset", "angry",
                  "unhappy", "not happy", "complaint", "complain", "poor", "bad", "still waiting",
                  "still not", "third time", "second time", "for days", "ignored", "waste")
POSITIVE_WORDS = ("thank you", "thanks", "appreciate", "great service", "happy with", "pleased")

QUESTIONS = {
    "issue_description": "Could you briefly describe what went wrong?",
    "order_id": "Could you share your order number?",
    "contact": "What email address or phone number can we reach you on?",
    "product": "Which product is this about?",
    "customer_name": "May I have your name?",
    "customer_id": "What is your customer ID?",
}
ASK_ORDER = ("issue_description", "order_id", "contact", "product", "customer_name", "customer_id")


@lru_cache(maxsize=None)
def _compiled(phrase):
    if phrase.endswith("*"):
        return re.compile(r"\b" + re.escape(phrase[:-1]), re.IGNORECASE)
    return re.compile(r"\b" + re.escape(phrase) + r"\b", re.IGNORECASE)


def _hits(text, phrases):
    return [phrase for phrase in phrases if _compiled(phrase).search(text)]


def _normalise(text):
    return str(text).replace("\u2019", "'").replace("\u2018", "'")


def _field(value, source, turn=None, reason=None):
    return {"value": value, "source": source, "turn": turn, "reason": reason}


def _order_matches(text):
    """(values in order of appearance, spans of the ID text)."""
    found = []
    for pattern in ORDER_RES:
        for match in pattern.finditer(text):
            found.append((match.start(1), match.end(1), match.group(1).upper().replace(" ", "")))
    found.sort()
    values = []
    for _, _, value in found:
        if value not in values:
            values.append(value)
    return values, [(start, end) for start, end, _ in found]


def _find_email(text):
    match = EMAIL_RE.search(text)
    return match.group() if match else None


def _find_phone(text):
    _, spans = _order_matches(text)
    phones = find_phone_spans(text, spans)
    if not phones:
        return None
    start, end = phones[0]
    return text[start:end]


def _find_name(text):
    for match in NAME_RE.finditer(text):
        tokens = []
        for token in match.group(1).split():
            if token in NAME_STOPWORDS:
                break
            tokens.append(token)
        if tokens:
            return " ".join(tokens)
    return None


def _find_customer_id(text):
    match = CUSTOMER_ID_RE.search(text)
    return match.group(1).upper() if match else None


def _find_product(text):
    for pattern in PRODUCT_RES:
        for match in pattern.finditer(text):
            value = re.sub(r"\s+", " ", match.group(1)).strip(" -'")
            words = value.split()
            if not value or value.lower() in PRODUCT_NOT_NAMES or len(words) > 8 or words[0].isdigit():
                continue
            return value
    return None


def _find_method(text):
    best = None
    for pattern, method in METHOD_PATTERNS:
        match = pattern.search(text)
        if match and (best is None or match.start() < best[0]):
            best = (match.start(), method)
    return best[1] if best else None


def _find_error_codes(text):
    codes = []
    for match in ERROR_LABELLED_RE.finditer(text):
        codes.append(match.group(1).upper())
    for match in ERROR_STANDALONE_RE.finditer(text):
        codes.append(match.group(1).upper())
    return codes


def _find_amounts(text):
    return [match.group(0).strip() for match in AMOUNT_RE.finditer(text)]


def _latest(customer_turns, finder):
    """The value from the most recent customer turn where the finder found something."""
    value, where = None, None
    for index, text in customer_turns:
        found = finder(text)
        if found:
            value, where = found, index
    return value, where


def _unique_in_order(customer_turns, finder):
    values, turns = [], {}
    for index, text in customer_turns:
        for value in finder(text):
            if value not in values:
                values.append(value)
            turns[value] = index
    return values, turns


def _category_rank(name):
    if name in CATEGORY_ORDER:
        return (CATEGORY_ORDER.index(name), name)
    return (len(CATEGORY_ORDER), name)


def _classify_category(cfg, description_text, rest_text, has_order_id):
    allowed = list(cfg.data["routing"]["categories"])
    scores = {}
    matched = {}
    for name in allowed:
        phrases = CATEGORY_KEYWORDS.get(name, (name,))
        in_description = _hits(description_text, phrases)
        in_rest = _hits(rest_text, phrases)
        scores[name] = 2 * len(in_description) + len(in_rest)
        matched[name] = sorted(set(in_description) | set(in_rest))
    best = max(scores.values()) if scores else 0
    if best > 0:
        tied = sorted((name for name in scores if scores[name] == best), key=_category_rank)
        winner = tied[0]
        return winner, "matched wording: " + ", ".join(matched[winner])
    if has_order_id and "order" in allowed:
        return "order", "no category wording found; an order number was given"
    fallback = "general" if "general" in allowed else allowed[0]
    return fallback, "no category wording found; default applied"


def _classify_severity(full_text):
    for level, phrases in SEVERITY_KEYWORDS:
        found = _hits(full_text, phrases)
        if found:
            return level, "matched wording: " + ", ".join(found)
    return DEFAULT_SEVERITY, "no severity wording found; default applied"


def _classify_impact(cfg, full_text, order_count):
    table = cfg.data["priority"]["impact_points"]
    for label, phrases in IMPACT_KEYWORDS:
        found = _hits(full_text, phrases)
        if found and label in table:
            return label, "matched wording: " + ", ".join(found)
    if order_count >= 2 and "multiple_orders" in table:
        return "multiple_orders", "more than one order number was given"
    default = "single_customer" if "single_customer" in table else next(iter(table))
    return default, "no wider impact wording found; default applied"


def _classify_sentiment(cfg, full_text):
    table = cfg.data["priority"]["sentiment_points"]
    very = _hits(full_text, VERY_NEGATIVE_WORDS)
    negative = _hits(full_text, NEGATIVE_WORDS)
    positive = _hits(full_text, POSITIVE_WORDS)
    if (very or ("!!" in full_text and negative)) and "very_negative" in table:
        return "very_negative", "matched wording: " + ", ".join(very + negative or ["!!"])
    if (very or negative) and "negative" in table:
        return "negative", "matched wording: " + ", ".join(very + negative)
    if positive and not negative and "positive" in table:
        return "positive", "matched wording: " + ", ".join(positive)
    return ("neutral" if "neutral" in table else next(iter(table))), "no sentiment wording found"


def extract_ticket_fields(cfg, turns):
    """Returns {"fields": {name: field}, "evidence": [..]} built from the customer's turns."""
    customer_turns = [
        (index, _normalise(turn.get("text", "")))
        for index, turn in enumerate(turns)
        if turn.get("role") == "customer" and str(turn.get("text", "")).strip()
    ]
    fields = {}
    notes = {}

    def note(index, name):
        if index is None:
            return
        notes.setdefault(index, [])
        if name not in notes[index]:
            notes[index].append(name)

    # ---- order numbers: the most recent turn that names one decides the main order
    all_ids, latest_ids, latest_turn = [], [], None
    for index, text in customer_turns:
        found, _ = _order_matches(text)
        if found:
            latest_ids, latest_turn = found, index
            for value in found:
                if value not in all_ids:
                    all_ids.append(value)
            note(index, "order_id")
    if latest_ids:
        primary = latest_ids[0]
        fields["order_id"] = _field(primary, STATED, latest_turn)
        others = [value for value in all_ids if value != primary]
        if others:
            fields["other_order_ids"] = _field(others, STATED, latest_turn)

    # ---- single-valued facts: the most recent statement wins
    for name, finder in (
        ("customer_name", _find_name),
        ("customer_id", _find_customer_id),
        ("product", _find_product),
        ("contact_email", _find_email),
        ("contact_phone", _find_phone),
    ):
        value, where = _latest(customer_turns, finder)
        if value:
            fields[name] = _field(value, STATED, where)
            note(where, name)

    method, method_turn = _latest(customer_turns, _find_method)
    if method:
        fields["contact_method"] = _field(method, STATED, method_turn)
        note(method_turn, "contact_method")
    elif "contact_email" in fields and "contact_phone" not in fields:
        fields["contact_method"] = _field("email", INFERRED, None, "only an email address was given")
    elif "contact_phone" in fields and "contact_email" not in fields:
        fields["contact_method"] = _field("phone", INFERRED, None, "only a phone number was given")

    # ---- lists
    codes, code_turns = _unique_in_order(customer_turns, _find_error_codes)
    if codes:
        fields["error_codes"] = _field(codes, STATED, max(code_turns.values()))
        for index in set(code_turns.values()):
            note(index, "error_codes")
    amounts, amount_turns = _unique_in_order(customer_turns, _find_amounts)
    if amounts:
        fields["amounts"] = _field(amounts, STATED, max(amount_turns.values()))
        for index in set(amount_turns.values()):
            note(index, "amounts")

    # ---- the issue description is the customer's first substantive message, masked
    description_index, description_text = None, ""
    for minimum in (5, 3):
        for index, text in customer_turns:
            if len(text.split()) >= minimum:
                description_index, description_text = index, text
                break
        if description_index is not None:
            break
    if description_index is not None:
        fields["issue_description"] = _field(mask_text(description_text)[:500], STATED, description_index)
        note(description_index, "issue_description")

    # ---- inferred facts, each with the wording that led to it
    if customer_turns:
        rest_text = " ".join(text for index, text in customer_turns if index != description_index)
        full_text = " ".join(text for _, text in customer_turns)
        category, reason = _classify_category(cfg, description_text, rest_text, bool(all_ids))
        fields["issue_category"] = _field(category, INFERRED, None, reason)
        severity, reason = _classify_severity(full_text)
        fields["severity"] = _field(severity, INFERRED, None, reason)
        impact, reason = _classify_impact(cfg, full_text, len(all_ids))
        fields["impact"] = _field(impact, INFERRED, None, reason)
        sentiment, reason = _classify_sentiment(cfg, full_text)
        fields["sentiment"] = _field(sentiment, INFERRED, None, reason)

    # ---- evidence: customer messages that supplied facts, and attachment references
    evidence = []
    texts = dict(customer_turns)
    for index in sorted(notes):
        evidence.append({
            "type": "message",
            "turn": index,
            "at": turns[index].get("at"),
            "excerpt": mask_text(texts[index])[:200],
            "supports": list(notes[index]),
        })
    for index, turn in enumerate(turns):
        attachment = turn.get("attachment")
        if isinstance(attachment, dict):
            evidence.append({
                "type": "attachment",
                "turn": index,
                "file_id": str(attachment.get("file_id", "")),
                "status": str(attachment.get("status", "")),
                "kind": str(attachment.get("kind", "")),
                "note": "reference only; the stored file is deleted after the retention period",
            })
    evidence.sort(key=lambda item: (item["turn"], 0 if item["type"] == "message" else 1))
    return {"fields": fields, "evidence": evidence}


def merge_fields(existing, new):
    """Combines stored fields with freshly extracted ones without losing what was collected.

    Stated beats inferred; a newer stated value replaces an older one (the old value is kept in
    previous_values); inferred values are recomputed; list fields are merged; the issue
    description keeps the customer's first wording.
    """
    merged = {name: dict(field) for name, field in existing.items()}
    for name, field in new.items():
        old = merged.get(name)
        if old is None:
            merged[name] = dict(field)
            continue
        if name in LIST_FIELDS:
            union = list(old["value"])
            for value in field["value"]:
                if value not in union:
                    union.append(value)
            merged[name] = {**old, "value": union}
            continue
        if name in KEEP_FIRST_FIELDS:
            continue
        if old["source"] == STATED and field["source"] == INFERRED:
            continue
        if old["source"] == INFERRED:
            merged[name] = dict(field)
            continue
        if old["value"] == field["value"]:
            continue
        replacement = dict(field)
        replacement["previous_values"] = list(old.get("previous_values", [])) + [old["value"]]
        merged[name] = replacement
    return merged


def _has(fields, name):
    if name == "contact":
        return "contact_email" in fields or "contact_phone" in fields
    field = fields.get(name)
    return field is not None and field["value"] not in (None, "", [])


def required_fields(cfg, category):
    mandatory = cfg.data["mandatory_fields"]
    return list(mandatory["by_category"].get(category, mandatory["default"]))


def missing_mandatory(cfg, fields):
    """The mandatory fields that are still missing, in the configured order."""
    category = fields.get("issue_category", {}).get("value")
    return [name for name in required_fields(cfg, category) if not _has(fields, name)]


def follow_up_questions(missing, asked=None, max_attempts=2, limit=2):
    """Short questions for missing fields, skipping any asked max_attempts times already."""
    asked = asked or {}
    wanted = [
        name for name in ASK_ORDER
        if name in missing and asked.get(name, 0) < max_attempts
    ]
    return [{"field": name, "question": QUESTIONS[name]} for name in wanted[:limit]]


def follow_up_text(questions):
    if not questions:
        return ""
    numbered = " ".join(f"{number}. {item['question']}" for number, item in enumerate(questions, start=1))
    return "To move this forward, please help with: " + numbered