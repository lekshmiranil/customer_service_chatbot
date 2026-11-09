"""Honest notice for order-status requests that the knowledge assistant refused.

Pure functions, standard library only. The caller decides what to do with the
text; this module never touches tickets or the RAG result.
"""
import re

ORDER_DATA_NOTICE = (
    "Order details are not available in this chat. "
    "A member of our support team will check your order and follow up with you."
)

_ORDER_ID_EXTRA = re.compile(r"Order ID:\s*(\S+)")


def order_ids_from_query(query):
    """Order IDs carried by the 'Order ID: X.' extra of a multilingual-layer query."""
    try:
        found = _ORDER_ID_EXTRA.findall(str(query or ""))
    except Exception:
        return []
    ids = []
    for item in found:
        item = item.rstrip(".,;")
        if item and item not in ids:
            ids.append(item)
    return ids


def order_data_notice(intents, order_ids, rag_status):
    """Return the English notice, or "" when it does not apply.

    Applies only when "order_status" is among the intents, at least one order
    ID is known, and the knowledge assistant refused (rag_status == "refused").
    """
    try:
        if rag_status != "refused":
            return ""
        if not intents or "order_status" not in list(intents):
            return ""
        if not order_ids or not list(order_ids):
            return ""
        return ORDER_DATA_NOTICE
    except TypeError:
        return ""