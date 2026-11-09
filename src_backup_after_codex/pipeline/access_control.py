import hmac
import json
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())

from pathlib import Path

# Anchors logs/access_audit.jsonl to the project root (customer_service_chatbot_LLM/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
AUDIT_LOG_PATH = PROJECT_ROOT / "logs" / "access_audit.jsonl"

# Which roles may perform which actions
PERMISSIONS = {
    "run_update":   {"admin","pipeline"},
    "rollback":     {"admin"},
    "add_document": {"admin"},
    "view_status":  {"admin", "viewer"},
}

# Role -> environment variable holding that role's token
ROLE_TOKEN_VARS = {
    "admin": "ADMIN_TOKEN",
    "viewer": "VIEWER_TOKEN",
    "pipeline": "PIPELINE_TOKEN",
}


def _identify_role(token):
    """Returns the role a token belongs to, or None.
    A role whose token is not configured is disabled, so an empty
    token can never match."""
    if not token:
        return None
    for role, env_name in ROLE_TOKEN_VARS.items():
        expected = os.getenv(env_name)
        if expected and hmac.compare_digest(token.encode(), expected.encode()):
            return role
    return None


def _audit(role, action, allowed, reason):
    """Appends one JSON line per access attempt. Never records the token."""
    entry = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "role": role or "none",
        "action": action,
        "allowed": allowed,
        "reason": reason,
    }
    try:
        AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError as e:
        print(f"Warning: could not write audit log: {e}")


def authorize(token, action) -> bool:
    """Checks whether the token's role may perform the action, and logs the attempt.
    If no token is passed, falls back to PIPELINE_TOKEN (the service credential
    used by the scheduled runner)."""
    if token is None:
        token = os.getenv("PIPELINE_TOKEN")

    allowed_roles = PERMISSIONS.get(action)
    if allowed_roles is None:
        _audit(None, action, False, "unknown action")
        return False

    role = _identify_role(token)
    if role is None:
        _audit(None, action, False, "invalid or missing token")
        return False
    if role not in allowed_roles:
        _audit(role, action, False, "role not permitted for this action")
        return False

    _audit(role, action, True, "ok")
    return True