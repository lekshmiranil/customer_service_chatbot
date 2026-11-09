"""Bridge between the Streamlit app and the multilingual layer.

handle_turn never raises. On failure it returns ok False and sets LAST_ERROR.
Standard library only. The clock is an argument (now).
"""

from src.multilingual import config, dialogue, masking, replies, session_store, summary

LAST_ERROR = ""


def _note(exc):
    global LAST_ERROR
    LAST_ERROR = type(exc).__name__ + ": " + str(exc)


def _failure(session_id, reason):
    return {
        "ok": False,
        "error": reason,
        "session_id": session_id,
        "requested_session_id": session_id,
        "status": "",
        "notice": "",
        "notice_text": "",
        "kind": "error",
        "language": "en",
        "text": "",
        "query": "",
        "queries": [],
        "retrieval_query": "",
        "intents": [],
        "clarify": False,
        "escalated": False,
        "notices": [],
        "switched": False,
        "mixed": False,
        "turns": 0,
        "result": {},
    }


def _notice_text(resolved, lang):
    notice = resolved.get("notice", "")
    if notice == "restored":
        body = summary.text(resolved.get("summary"))
        return replies.render("restored", lang, summary=body)
    if notice == "expired_new":
        return replies.render("expired_new", lang)
    return ""


def handle_turn(session_id, customer_id="", text="", now=None, cfg=None,
                db_path=None, force_language=""):
    """Process one customer message and return a result dict."""
    global LAST_ERROR
    requested = str(session_id or "").strip()
    conn = None
    try:
        cfg = cfg or config.get_config()
        path = db_path or config.db_path()
        when = session_store.utc_now(now)
        if not requested:
            requested = session_store.new_session_id()
        conn = session_store.connect(path)
        resolved = session_store.resolve_session(
            conn, requested, str(customer_id or "").strip(), when, cfg
        )
        session = resolved.get("session") or {}
        active_id = session.get("session_id") or requested
        state = session.get("state") or summary.empty_state("en")

        new_state, result = dialogue.handle_message(state, text, cfg, force_language)
        if isinstance(new_state, dict) and new_state.get("held_text"):
            new_state["held_text"] = masking.mask(new_state["held_text"])
        lang = result.get("language") or "en"
        limit = cfg["session"]["store_max_turns"]
        meta = {
            "kind": result.get("kind"),
            "intents": result.get("intents"),
            "query": masking.mask(result.get("query")),
        }
        session_store.add_turn(
            conn, active_id, "customer", masking.mask(text), lang, when, None, limit
        )
        reply = masking.mask(result.get("text") or result.get("query") or "")
        session_store.add_turn(conn, active_id, "bot", reply, lang, when, meta, limit)
        session_store.save_state(conn, active_id, new_state)
        turns = session_store.count_turns(conn, active_id)

        return {
            "ok": True,
            "error": "",
            "session_id": active_id,
            "requested_session_id": requested,
            "status": resolved.get("status", ""),
            "notice": resolved.get("notice", ""),
            "notice_text": _notice_text(resolved, lang),
            "kind": result.get("kind", ""),
            "language": lang,
            "text": result.get("text", ""),
            "query": result.get("query", ""),
            "queries": list(result.get("queries") or []),
            "retrieval_query": result.get("retrieval_query", ""),
            "intents": list(result.get("intents") or []),
            "clarify": result.get("kind") == "clarify",
            "escalated": bool(result.get("escalated")),
            "notices": list(result.get("notices") or []),
            "switched": bool(result.get("switched")),
            "mixed": bool(result.get("mixed")),
            "turns": turns,
            "result": result,
        }
    except Exception as exc:
        _note(exc)
        return _failure(requested, type(exc).__name__)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def sweep(now=None, cfg=None, db_path=None):
    """Close idle sessions. Returns the store's result, or None on failure."""
    conn = None
    try:
        cfg = cfg or config.get_config()
        conn = session_store.connect(db_path or config.db_path())
        return session_store.sweep(conn, session_store.utc_now(now), cfg)
    except Exception as exc:
        _note(exc)
        return None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def session_status(session_id, now=None, cfg=None, db_path=None):
    """Return 'active', 'expired' or similar from the store, or 'unknown' on failure."""
    conn = None
    try:
        cfg = cfg or config.get_config()
        conn = session_store.connect(db_path or config.db_path())
        return session_store.session_status(
            conn, str(session_id or ""), session_store.utc_now(now), cfg
        )
    except Exception as exc:
        _note(exc)
        return "unknown"
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass