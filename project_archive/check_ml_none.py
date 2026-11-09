import inspect
import os
import shutil
import sys
import tempfile
from datetime import timedelta

sys.stdout.reconfigure(errors="backslashreplace")

from src.multilingual import bridge, config, session_store

cfg = config.get_config()
tmp = tempfile.mkdtemp()
db = os.path.join(tmp, "s.db")
t0 = session_store.utc_now()

first = bridge.handle_turn("sE", "", "where is my order ORD-55555", now=t0, cfg=cfg, db_path=db)
second = bridge.handle_turn("sE", "", "hello", now=t0 + timedelta(minutes=40), cfg=cfg, db_path=db)
for name, result in (("first", first), ("second", second)):
    print(name, {key: result.get(key) for key in ("ok", "error", "session_id", "status", "notice", "kind", "turns")})
print("LAST_ERROR:", ascii(bridge.LAST_ERROR))

conn = session_store.connect(db)
try:
    for sid in {"sE", first.get("session_id"), second.get("session_id")}:
        row = session_store.get_session(conn, sid)
        print("session", sid, "->", ascii({k: row.get(k) for k in ("customer_id", "ended_at", "end_reason", "restored_from")}) if row else None)
finally:
    conn.close()

print("---- resolve_session")
print(inspect.getsource(session_store.resolve_session))
print("---- expire_idle")
print(inspect.getsource(session_store.expire_idle))
shutil.rmtree(tmp, ignore_errors=True)