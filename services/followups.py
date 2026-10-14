from datetime import date

from core import audit
from core.auth import require_role, scope
from core.db import execute, query, query_one
from core.rules import FU_STATUS, FU_TYPES, MSG_FU_DATE, check_choice, now, to_date
from services.users import resolve_owner


def list_followups(user, view="pending", status="", owner=None, search="", on_date=None):
    where, params = scope(user, "f")
    sql = ("SELECT f.id, f.fu_date, f.subject, f.fu_type, COALESCE(c.name, l.name) AS related_to, "
           "CASE WHEN f.customer_id IS NOT NULL THEN 'Customer' ELSE 'Lead' END AS related_type, "
           "f.status, u.full_name AS owner, "
           "CASE WHEN f.status = 'Planned' AND f.fu_date < DATE('now', 'localtime') THEN 'Yes' ELSE '' END AS overdue "
           "FROM followups f LEFT JOIN customers c ON c.id = f.customer_id LEFT JOIN leads l ON l.id = f.lead_id "
           "LEFT JOIN users u ON u.id = f.assigned_to WHERE 1=1" + where)
    if view == "pending":
        sql += " AND f.status = 'Planned'"
    elif view == "overdue":
        sql += " AND f.status = 'Planned' AND f.fu_date < DATE('now', 'localtime')"
    elif view == "upcoming":
        sql += " AND f.status = 'Planned' AND f.fu_date >= DATE('now', 'localtime')"
    if status:
        sql += " AND f.status = ?"
        params.append(status)
    if owner:
        sql += " AND f.assigned_to = ?"
        params.append(owner)
    if on_date:
        sql += " AND f.fu_date = ?"
        params.append(to_date(on_date).isoformat())
    if search:
        sql += " AND (f.subject LIKE ? OR c.name LIKE ? OR l.name LIKE ?)"
        params += [f"%{search}%"] * 3
    return query(sql + " ORDER BY f.fu_date", params)


def get_followup(user, fid):
    where, params = scope(user)
    return query_one("SELECT * FROM followups WHERE id = ?" + where, [fid] + params)


def validate(user, data, old_date=None):
    errors = {}
    subject = (data.get("subject") or "").strip()
    if not 3 <= len(subject) <= 150:
        errors["subject"] = "Subject must be 3-150 characters."
    check_choice(errors, "fu_type", data.get("fu_type"), FU_TYPES, "type")
    check_choice(errors, "status", data.get("status", "Planned"), FU_STATUS, "status")
    if not data.get("customer_id") and not data.get("lead_id"):
        errors["related"] = "Select a customer or a lead for this follow-up."

    where, params = scope(user)
    if data.get("customer_id") and not query_one("SELECT id FROM customers WHERE id = ?" + where, [data["customer_id"]] + params):
        errors["customer_id"] = "Selected customer does not exist or is not accessible."
    if data.get("lead_id") and not query_one("SELECT id FROM leads WHERE id = ?" + where, [data["lead_id"]] + params):
        errors["lead_id"] = "Selected lead does not exist or is not accessible."

    try:
        fu_date = to_date(data.get("fu_date"))
        date_changed = old_date is None or to_date(old_date) != fu_date
        if data.get("status", "Planned") == "Planned" and date_changed and fu_date < date.today():
            errors["fu_date"] = MSG_FU_DATE
    except (TypeError, ValueError):
        errors["fu_date"] = "Follow-up date is required."
    return errors


def create_followup(user, data):
    data["status"] = "Planned"
    errors = validate(user, data)
    owner, err = resolve_owner(user, data.get("assigned_to"))
    if err:
        errors["assigned_to"] = err
    if errors:
        return None, errors
    fid = execute(
        "INSERT INTO followups (customer_id, lead_id, fu_date, fu_type, subject, remarks, status, assigned_to, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 'Planned', ?, ?)",
        (data.get("customer_id") or None, data.get("lead_id") or None, to_date(data["fu_date"]).isoformat(),
         data["fu_type"], data["subject"].strip(), data.get("remarks") or None, owner, now()),
    )
    audit.log(user, "Create", "FollowUp", fid, new={"subject": data["subject"], "date": str(data["fu_date"])})
    return fid, {}


def update_followup(user, fid, data):
    """Edit or reschedule."""
    old = get_followup(user, fid)
    if not old:
        return {"_": "Follow-up not found."}
    errors = validate(user, data, old_date=old["fu_date"])
    owner = old["assigned_to"]
    if user["role"] != "SalesExecutive" and data.get("assigned_to"):
        owner, err = resolve_owner(user, data["assigned_to"])
        if err:
            errors["assigned_to"] = err
    if errors:
        return errors
    completed_at = old["completed_at"]
    if data["status"] == "Completed" and old["status"] != "Completed":
        completed_at = now()
    new = {"customer_id": data.get("customer_id") or None, "lead_id": data.get("lead_id") or None,
           "fu_date": to_date(data["fu_date"]).isoformat(), "fu_type": data["fu_type"], "subject": data["subject"].strip(),
           "remarks": data.get("remarks") or None, "status": data["status"],
           "assigned_to": owner}
    execute("UPDATE followups SET customer_id=?, lead_id=?, fu_date=?, fu_type=?, subject=?, remarks=?, status=?, assigned_to=?, completed_at=? WHERE id=?",
            tuple(new.values()) + (completed_at, fid))
    old_vals, new_vals = audit.changes(old, new)
    if new_vals:
        audit.log(user, "Update", "FollowUp", fid, old=old_vals, new=new_vals)
    return {}


def set_status(user, fid, status):
    """Quick buttons: Completed / Missed / Cancelled. Only for planned follow-ups."""
    old = get_followup(user, fid)
    if not old:
        return "Follow-up not found."
    if old["status"] != "Planned":
        return "Only planned follow-ups can be updated."
    if status not in FU_STATUS:
        return "Invalid status."
    execute("UPDATE followups SET status = ?, completed_at = ? WHERE id = ?",
            (status, now() if status == "Completed" else None, fid))
    audit.log(user, "Update", "FollowUp", fid, old={"status": "Planned"}, new={"status": status})
    return None


def delete_followup(user, fid):
    require_role(user, "Admin", "Manager")
    old = query_one("SELECT * FROM followups WHERE id = ?", (fid,))
    if not old:
        return "Follow-up not found."
    execute("DELETE FROM followups WHERE id = ?", (fid,))
    audit.log(user, "Delete", "FollowUp", fid, old=old)
    return "Follow-up deleted."
