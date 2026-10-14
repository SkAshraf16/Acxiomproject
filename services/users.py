from datetime import datetime

from core import audit
from core.auth import hash_password, require_role
from core.db import execute, query, query_one
from core.rules import ROLES, check_choice, check_email, check_name, check_password, check_phone, now


def list_users(user, search="", role=""):
    require_role(user, "Admin", "Manager")
    sql = "SELECT id, full_name, email, phone, role, is_active, failed_count, lockout_until, created_at FROM users WHERE 1=1"
    params = []
    if search:
        sql += " AND (full_name LIKE ? OR email LIKE ?)"
        params += [f"%{search}%", f"%{search}%"]
    if role:
        sql += " AND role = ?"
        params.append(role)
    rows = query(sql + " ORDER BY full_name", params)
    for r in rows:
        r["locked"] = bool(r["lockout_until"]) and datetime.fromisoformat(r["lockout_until"]) > datetime.now()
    return rows


def get_user(uid):
    return query_one("SELECT id, full_name, email, phone, role, is_active FROM users WHERE id = ?", (uid,))


def assignable_users():
    """Active sales executives and managers, used in 'Assigned To' dropdowns."""
    return query("SELECT id, full_name FROM users WHERE is_active = 1 AND role IN ('SalesExecutive', 'Manager') ORDER BY full_name")


def resolve_owner(user, requested_id):
    """Sales Executive can only assign to self. Admin/Manager can pick any active user."""
    if user["role"] == "SalesExecutive" or not requested_id:
        return user["id"], None
    target = query_one("SELECT id, is_active FROM users WHERE id = ?", (requested_id,))
    if not target or not target["is_active"]:
        return None, "Selected user does not exist or is inactive."
    return target["id"], None


def validate(data, uid=None):
    errors = {}
    check_name(errors, "full_name", data.get("full_name"), "Full Name")
    check_email(errors, "email", data.get("email"))
    check_phone(errors, "phone", data.get("phone"), required=False)
    check_choice(errors, "role", data.get("role"), ROLES, "role")
    if uid is None:
        check_password(errors, "password", data.get("password"))
    email = (data.get("email") or "").strip().lower()
    if "email" not in errors and query_one("SELECT id FROM users WHERE email = ? AND id != ?", (email, uid or 0)):
        errors["email"] = "This email is already used by another user."
    return errors


def create_user(user, data):
    require_role(user, "Admin")
    errors = validate(data)
    if errors:
        return None, errors
    uid = execute(
        "INSERT INTO users (full_name, email, phone, password_hash, role, is_active, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (data["full_name"].strip(), data["email"].strip().lower(), data.get("phone") or None,
         hash_password(data["password"]), data["role"], 1 if data.get("is_active", True) else 0, now()),
    )
    audit.log(user, "Create", "User", uid, new={"email": data["email"], "role": data["role"]})
    return uid, {}


def update_user(user, uid, data):
    require_role(user, "Admin")
    old = get_user(uid)
    if not old:
        return {"_": "User not found."}
    errors = validate(data, uid)
    if uid == user["id"] and (data["role"] != "Admin" or not data.get("is_active", True)):
        errors["_"] = "You cannot remove your own Admin role or deactivate yourself."
    if errors:
        return errors

    active = 1 if data.get("is_active", True) else 0
    execute("UPDATE users SET full_name = ?, email = ?, phone = ?, role = ?, is_active = ? WHERE id = ?",
            (data["full_name"].strip(), data["email"].strip().lower(), data.get("phone") or None, data["role"], active, uid))
    if old["role"] != data["role"]:
        audit.log(user, "RoleChange", "User", uid, old={"role": old["role"]}, new={"role": data["role"]})
    if old["is_active"] != active:
        audit.log(user, "Activate" if active else "Deactivate", "User", uid)
    audit.log(user, "Update", "User", uid, new={"full_name": data["full_name"], "email": data["email"]})
    return {}


def toggle_active(user, uid):
    require_role(user, "Admin")
    if uid == user["id"]:
        return "You cannot deactivate your own account."
    row = get_user(uid)
    new_state = 0 if row["is_active"] else 1
    execute("UPDATE users SET is_active = ? WHERE id = ?", (new_state, uid))
    audit.log(user, "Activate" if new_state else "Deactivate", "User", uid)
    return None


def unlock(user, uid):
    require_role(user, "Admin")
    execute("UPDATE users SET lockout_until = NULL, failed_count = 0 WHERE id = ?", (uid,))
    audit.log(user, "Unlock", "User", uid)


def reset_password(user, uid, new_password):
    require_role(user, "Admin")
    errors = {}
    check_password(errors, "password", new_password)
    if errors:
        return errors
    execute("UPDATE users SET password_hash = ?, lockout_until = NULL, failed_count = 0 WHERE id = ?",
            (hash_password(new_password), uid))
    audit.log(user, "PasswordReset", "User", uid)
    return {}


def role_counts():
    return query("SELECT role, COUNT(*) AS users FROM users GROUP BY role ORDER BY role")
