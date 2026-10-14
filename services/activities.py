from datetime import date

from core import audit
from core.auth import require_role, scope
from core.db import execute, query, query_one
from core.rules import ACT_STATUS, ACT_TYPES, check_choice, now, to_date
from services.users import resolve_owner


def list_activities(user, act_type="", status="", owner=None, on_date=None):
    where, params = scope(user, "a")
    sql = ("SELECT a.id, a.act_date, a.act_type, a.subject, COALESCE(c.name, l.name) AS related_to, a.status, u.full_name AS owner "
           "FROM activities a LEFT JOIN customers c ON c.id = a.customer_id LEFT JOIN leads l ON l.id = a.lead_id "
           "LEFT JOIN users u ON u.id = a.assigned_to WHERE 1=1" + where)
    if act_type:
        sql += " AND a.act_type = ?"
        params.append(act_type)
    if status:
        sql += " AND a.status = ?"
        params.append(status)
    if owner:
        sql += " AND a.assigned_to = ?"
        params.append(owner)
    if on_date:
        sql += " AND a.act_date = ?"
        params.append(to_date(on_date).isoformat())
    return query(sql + " ORDER BY a.act_date DESC", params)


def get_activity(user, aid):
    where, params = scope(user)
    return query_one("SELECT * FROM activities WHERE id = ?" + where, [aid] + params)


def validate(user, data, is_new):
    errors = {}
    subject = (data.get("subject") or "").strip()
    if not 3 <= len(subject) <= 150:
        errors["subject"] = "Subject must be 3-150 characters."
    check_choice(errors, "act_type", data.get("act_type"), ACT_TYPES, "activity type")
    check_choice(errors, "status", data.get("status"), ACT_STATUS, "status")
    if not data.get("customer_id") and not data.get("lead_id"):
        errors["related"] = "Select a customer or a lead for this activity."

    where, params = scope(user)
    if data.get("customer_id") and not query_one("SELECT id FROM customers WHERE id = ?" + where, [data["customer_id"]] + params):
        errors["customer_id"] = "Selected customer does not exist or is not accessible."
    if data.get("lead_id") and not query_one("SELECT id FROM leads WHERE id = ?" + where, [data["lead_id"]] + params):
        errors["lead_id"] = "Selected lead does not exist or is not accessible."

    try:
        if is_new and data.get("status") == "Planned" and to_date(data.get("act_date")) < date.today():
            errors["act_date"] = "A planned activity cannot be dated in the past."
    except (TypeError, ValueError):
        errors["act_date"] = "Activity date is required."
    return errors


def create_activity(user, data):
    errors = validate(user, data, is_new=True)
    owner, err = resolve_owner(user, data.get("assigned_to"))
    if err:
        errors["assigned_to"] = err
    if errors:
        return None, errors
    aid = execute(
        "INSERT INTO activities (act_type, subject, description, act_date, customer_id, lead_id, status, assigned_to, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (data["act_type"], data["subject"].strip(), data.get("description") or None, to_date(data["act_date"]).isoformat(),
         data.get("customer_id") or None, data.get("lead_id") or None, data["status"], owner, now()),
    )
    audit.log(user, "Create", "Activity", aid, new={"type": data["act_type"], "subject": data["subject"]})
    return aid, {}


def update_activity(user, aid, data):
    old = get_activity(user, aid)
    if not old:
        return {"_": "Activity not found."}
    errors = validate(user, data, is_new=False)
    owner = old["assigned_to"]
    if user["role"] != "SalesExecutive" and data.get("assigned_to"):
        owner, err = resolve_owner(user, data["assigned_to"])
        if err:
            errors["assigned_to"] = err
    if errors:
        return errors
    new = {"act_type": data["act_type"], "subject": data["subject"].strip(), "description": data.get("description") or None,
           "act_date": to_date(data["act_date"]).isoformat(), "customer_id": data.get("customer_id") or None,
           "lead_id": data.get("lead_id") or None, "status": data["status"], "assigned_to": owner}
    execute("UPDATE activities SET act_type=?, subject=?, description=?, act_date=?, customer_id=?, lead_id=?, status=?, assigned_to=? WHERE id=?",
            tuple(new.values()) + (aid,))
    old_vals, new_vals = audit.changes(old, new)
    if new_vals:
        audit.log(user, "Update", "Activity", aid, old=old_vals, new=new_vals)
    return {}


def delete_activity(user, aid):
    require_role(user, "Admin", "Manager")
    old = query_one("SELECT * FROM activities WHERE id = ?", (aid,))
    if not old:
        return "Activity not found."
    execute("DELETE FROM activities WHERE id = ?", (aid,))
    audit.log(user, "Delete", "Activity", aid, old=old)
    return "Activity deleted."
