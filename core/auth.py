import hashlib
import hmac
import os
from datetime import datetime, timedelta

from core import audit
from core.db import execute, query_one
from core.rules import check_email, check_name, check_password, check_phone, now

MAX_TRIES = 5
LOCK_MINUTES = 15


# ---------- password hashing (PBKDF2 with random salt, plain text never stored) ----------

def hash_password(password):
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120000)
    return salt.hex() + "$" + digest.hex()


def verify_password(password, stored):
    salt_hex, digest_hex = stored.split("$")
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 120000)
    return hmac.compare_digest(digest.hex(), digest_hex)


# ---------- helpers ----------

def safe_user(row):
    """User dict without password hash - this is what we keep in session."""
    return {"id": row["id"], "full_name": row["full_name"], "email": row["email"], "role": row["role"]}


def is_locked(row):
    return row["lockout_until"] is not None and datetime.fromisoformat(row["lockout_until"]) > datetime.now()


# ---------- login / register ----------

def login(email, password):
    """Returns (user, error_message)."""
    email = (email or "").strip().lower()
    row = query_one("SELECT * FROM users WHERE email = ?", (email,))
    wrong = "Invalid email or password."

    if not row:
        audit.log(None, "FailedLogin", "Account", result="Failure", email=email)
        return None, wrong
    if not row["is_active"]:
        audit.log(safe_user(row), "FailedLogin", "Account", row["id"], new={"reason": "inactive"}, result="Failure")
        return None, "Your account is inactive. Contact the administrator."
    if is_locked(row):
        return None, f"Account locked due to repeated failed logins. Try again after {row['lockout_until'][11:16]}."

    if not verify_password(password or "", row["password_hash"]):
        count = row["failed_count"] + 1
        if count >= MAX_TRIES:
            until = (datetime.now() + timedelta(minutes=LOCK_MINUTES)).isoformat(timespec="seconds")
            execute("UPDATE users SET failed_count = 0, lockout_until = ? WHERE id = ?", (until, row["id"]))
            audit.log(safe_user(row), "Lockout", "Account", row["id"], result="Failure")
            return None, f"Account locked for {LOCK_MINUTES} minutes due to {MAX_TRIES} wrong attempts."
        execute("UPDATE users SET failed_count = ? WHERE id = ?", (count, row["id"]))
        audit.log(safe_user(row), "FailedLogin", "Account", row["id"], result="Failure")
        return None, f"{wrong} {MAX_TRIES - count} attempt(s) left before lockout."

    execute("UPDATE users SET failed_count = 0, lockout_until = NULL WHERE id = ?", (row["id"],))
    user = safe_user(row)
    audit.log(user, "Login", "Account", row["id"])
    return user, None


def logout(user):
    audit.log(user, "Logout", "Account", user["id"])


def register(full_name, email, phone, password, confirm):
    """Self registration always gives SalesExecutive role. Returns (user, errors)."""
    errors = {}
    check_name(errors, "full_name", full_name, "Full Name")
    check_email(errors, "email", email)
    check_phone(errors, "phone", phone)
    check_password(errors, "password", password)
    if password != confirm:
        errors["confirm"] = "Passwords do not match."
    email = (email or "").strip().lower()
    if "email" not in errors and query_one("SELECT id FROM users WHERE email = ?", (email,)):
        errors["email"] = "This email is already registered."
    if errors:
        return None, errors

    uid = execute(
        "INSERT INTO users (full_name, email, phone, password_hash, role, created_at) VALUES (?, ?, ?, ?, 'SalesExecutive', ?)",
        (full_name.strip(), email, phone.strip(), hash_password(password), now()),
    )
    user = {"id": uid, "full_name": full_name.strip(), "email": email, "role": "SalesExecutive"}
    audit.log(user, "Register", "User", uid, new={"email": email, "role": "SalesExecutive"})
    audit.log(user, "Login", "Account", uid)
    return user, {}


# ---------- permission helpers (used by every service) ----------

def is_sales(user):
    return user["role"] == "SalesExecutive"


def require_role(user, *roles):
    if user["role"] not in roles:
        raise PermissionError("You do not have permission for this action.")


def scope(user, alias=""):
    """Sales Executive sees only own records. Returns (sql, params) to add in WHERE."""
    if is_sales(user):
        col = f"{alias}.assigned_to" if alias else "assigned_to"
        return f" AND {col} = ?", [user["id"]]
    return "", []
