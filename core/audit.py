import json

from core.db import execute
from core.rules import now


def log(user, action, entity, record_id=None, old=None, new=None, result="Success", email=None):
    """Save one audit row. Never pass passwords here."""
    execute(
        "INSERT INTO audit_log (user_id, user_email, action, entity, record_id, old_value, new_value, result, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            user["id"] if user else None,
            email or (user["email"] if user else None),
            action,
            entity,
            str(record_id) if record_id is not None else None,
            json.dumps(old, default=str) if old else None,
            json.dumps(new, default=str) if new else None,
            result,
            now(),
        ),
    )


def changes(old_row, new_data):
    """Return (old, new) dicts with only the fields that changed."""
    old, new = {}, {}
    for key, value in new_data.items():
        if key in old_row and str(old_row[key] or "") != str(value or ""):
            old[key] = old_row[key]
            new[key] = value
    return old, new
