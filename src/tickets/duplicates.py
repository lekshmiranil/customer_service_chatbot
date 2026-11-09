"""Duplicate detection and related-issue grouping between two tickets (Task 3).

compare_fields() looks at two sets of extracted ticket fields and returns one of:
  "duplicate" - the same customer problem raised again. Needs the SAME CATEGORY, plus a shared
                order or the same customer, plus either description similarity at or above
                duplicates.min_similarity or a shared error code.
  "related"   - a separate ticket about the same underlying incident. Needs the SAME CATEGORY
                plus a shared error code, or the same product or a shared order with description
                similarity at or above duplicates.related_min_similarity.
  "unrelated" - everything else. Text similarity alone never links two tickets, and different
                categories are never linked, even for the same customer, product or order.
Every decision carries the signals and plain-language reasons behind it.
"""
import re

TOKEN_RE = re.compile(r"[a-z][a-z0-9']{2,}")
STOPWORDS = frozenset({
    "the", "and", "for", "with", "that", "this", "you", "your", "are", "was", "were", "has", "have",
    "had", "can", "could", "would", "should", "please", "help", "yet", "still", "again", "from",
    "about", "just", "its", "hello", "thanks", "thank", "need", "want", "like", "been", "will", "get",
    "got", "but", "all", "any", "out", "now", "how", "what", "when", "why", "who", "our", "their",
    "they", "them", "she", "him", "her", "his", "there", "here",
})


def tokens(text):
    """Meaningful lowercase words of a description (short words, numbers and filler removed)."""
    return {word for word in TOKEN_RE.findall(str(text).lower()) if word not in STOPWORDS}


def similarity(first, second):
    """Jaccard similarity of the meaningful words of two descriptions, from 0.0 to 1.0."""
    left, right = tokens(first), tokens(second)
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _value(fields, name, default=None):
    field = fields.get(name)
    if field is None or field.get("value") in (None, "", []):
        return default
    return field["value"]


def identity_keys(fields):
    """Keys that identify a customer: email, last ten phone digits, customer ID."""
    keys = set()
    email = _value(fields, "contact_email")
    if email:
        keys.add("email:" + str(email).lower())
    phone = _value(fields, "contact_phone")
    if phone:
        digits = re.sub(r"\D", "", str(phone))
        if len(digits) >= 10:
            keys.add("phone:" + digits[-10:])
    customer_id = _value(fields, "customer_id")
    if customer_id:
        keys.add("customer:" + str(customer_id).upper())
    return keys


def order_ids(fields):
    found = set()
    main = _value(fields, "order_id")
    if main:
        found.add(str(main).upper())
    for other in _value(fields, "other_order_ids", []):
        found.add(str(other).upper())
    return found


def compare_fields(cfg, new_fields, old_fields):
    """Decides how a new ticket's fields relate to an existing ticket's fields."""
    settings = cfg.data["duplicates"]
    category_new = _value(new_fields, "issue_category")
    category_old = _value(old_fields, "issue_category")
    same_category = bool(category_new) and category_new == category_old
    shared_orders = sorted(order_ids(new_fields) & order_ids(old_fields))
    same_customer = bool(identity_keys(new_fields) & identity_keys(old_fields))
    product_new = str(_value(new_fields, "product", "")).strip().lower()
    product_old = str(_value(old_fields, "product", "")).strip().lower()
    same_product = bool(product_new) and product_new == product_old
    shared_errors = sorted(set(_value(new_fields, "error_codes", [])) & set(_value(old_fields, "error_codes", [])))
    score = round(similarity(_value(new_fields, "issue_description", ""), _value(old_fields, "issue_description", "")), 3)

    duplicate = (
        same_category
        and (bool(shared_orders) or same_customer)
        and (score >= settings["min_similarity"] or bool(shared_errors))
    )
    related = (
        not duplicate
        and same_category
        and (
            bool(shared_errors)
            or (same_product and score >= settings["related_min_similarity"])
            or (bool(shared_orders) and score >= settings["related_min_similarity"])
        )
    )
    decision = "duplicate" if duplicate else ("related" if related else "unrelated")

    reasons = []
    if same_category:
        reasons.append(f"same category ({category_new})")
    else:
        reasons.append(f"different category ({category_new or 'unknown'} vs {category_old or 'unknown'})")
    if shared_orders:
        reasons.append("shared order " + ", ".join(shared_orders))
    if same_customer:
        reasons.append("same customer contact or ID")
    if shared_errors:
        reasons.append("shared error code " + ", ".join(shared_errors))
    if same_product:
        reasons.append(f"same product ({product_new})")
    reasons.append(f"description similarity {score:.2f}")
    reasons.append(f"decision: {decision}")
    return {
        "decision": decision,
        "signals": {
            "category": category_new,
            "same_category": same_category,
            "shared_orders": shared_orders,
            "same_customer": same_customer,
            "same_product": same_product,
            "shared_error_codes": shared_errors,
            "similarity": score,
        },
        "reasons": reasons,
    }