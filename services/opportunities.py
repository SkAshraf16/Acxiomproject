from datetime import date

from core import audit
from core.auth import require_role, scope
from core.db import execute, query, query_one
from core.rules import (LEAD_SOURCES, MSG_AMOUNT, MSG_CLOSE_DATE, MSG_PROB, STAGES, check_choice, is_open_stage,
                        now, stage_status, to_date)
from services.users import resolve_owner


def list_opps(user, search="", stage="", status=""):
    where, params = scope(user, "o")
    sql = ("SELECT o.id, o.name, c.name AS customer, o.stage, o.amount, o.probability, "
           "ROUND(o.amount * o.probability / 100.0, 2) AS weighted, o.close_date, o.status, u.full_name AS owner "
           "FROM opportunities o JOIN customers c ON c.id = o.customer_id LEFT JOIN users u ON u.id = o.assigned_to WHERE 1=1" + where)
    if search:
        sql += " AND (o.name LIKE ? OR c.name LIKE ?)"
        params += [f"%{search}%"] * 2
    if stage:
        sql += " AND o.stage = ?"
        params.append(stage)
    if status:
        sql += " AND o.status = ?"
        params.append(status)
    return query(sql + " ORDER BY o.id DESC", params)


def get_opp(user, oid):
    where, params = scope(user, "o")
    return query_one("SELECT o.*, c.name AS customer FROM opportunities o JOIN customers c ON c.id = o.customer_id WHERE o.id = ?" + where,
                     [oid] + params)


def weighted(amount, probability):
    return amount * probability / 100


def validate(user, data, is_new):
    errors = {}
    name = (data.get("name") or "").strip()
    if not 3 <= len(name) <= 150:
        errors["name"] = "Opportunity Name must be 3-150 characters."
    check_choice(errors, "stage", data.get("stage"), STAGES, "stage")
    if data.get("source") and data["source"] not in LEAD_SOURCES:
        errors["source"] = "Select a valid source."

    try:
        amount = float(data.get("amount"))
        if amount <= 0:
            errors["amount"] = MSG_AMOUNT
    except (TypeError, ValueError):
        errors["amount"] = MSG_AMOUNT
    try:
        prob = int(data.get("probability"))
        if not 0 <= prob <= 100:
            errors["probability"] = MSG_PROB
    except (TypeError, ValueError):
        errors["probability"] = MSG_PROB

    try:
        close = to_date(data.get("close_date"))
        if is_open_stage(data.get("stage")) and close < date.today():
            errors["close_date"] = MSG_CLOSE_DATE
    except (TypeError, ValueError):
        errors["close_date"] = "Expected Close Date is required."

    if is_new and not is_open_stage(data.get("stage")):
        errors["stage"] = "A new opportunity must start in an open stage."

    # customer must exist and be visible to this user (foreign key check)
    where, params = scope(user)
    if not query_one("SELECT id FROM customers WHERE id = ?" + where, [data.get("customer_id")] + params):
        errors["customer_id"] = "Selected customer does not exist or is not accessible."
    return errors


def fix_probability(stage, prob):
    if stage == "Won":
        return 100
    if stage == "Lost":
        return 0
    return int(prob)


def create_opp(user, data):
    errors = validate(user, data, is_new=True)
    owner, err = resolve_owner(user, data.get("assigned_to"))
    if err:
        errors["assigned_to"] = err
    if errors:
        return None, errors
    oid = execute(
        "INSERT INTO opportunities (name, customer_id, amount, stage, probability, close_date, status, source, notes, assigned_to, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 'Open', ?, ?, ?, ?)",
        (data["name"].strip(), data["customer_id"], float(data["amount"]), data["stage"], int(data["probability"]),
         to_date(data["close_date"]).isoformat(), data.get("source") or None, data.get("notes") or None, owner, now()),
    )
    audit.log(user, "Create", "Opportunity", oid, new={"name": data["name"], "amount": data["amount"], "stage": data["stage"]})
    return oid, {}


def update_opp(user, oid, data):
    old = get_opp(user, oid)
    if not old:
        return {"_": "Opportunity not found."}
    errors = validate(user, data, is_new=False)
    if not is_open_stage(old["stage"]) and data.get("stage") != old["stage"]:
        errors["stage"] = "Closed (Won/Lost) opportunities cannot be reopened."
    owner = old["assigned_to"]
    if user["role"] != "SalesExecutive" and data.get("assigned_to"):
        owner, err = resolve_owner(user, data["assigned_to"])
        if err:
            errors["assigned_to"] = err
    if errors:
        return errors

    stage = data["stage"]
    closed_at = old["closed_at"]
    if stage != old["stage"] and not is_open_stage(stage):
        closed_at = now()
    new = {"name": data["name"].strip(), "customer_id": int(data["customer_id"]), "amount": float(data["amount"]),
           "stage": stage, "probability": fix_probability(stage, data["probability"]),
           "close_date": to_date(data["close_date"]).isoformat(), "status": stage_status(stage),
           "source": data.get("source") or None, "notes": data.get("notes") or None, "assigned_to": owner}
    execute("UPDATE opportunities SET name=?, customer_id=?, amount=?, stage=?, probability=?, close_date=?, status=?, source=?, notes=?, "
            "assigned_to=?, closed_at=?, modified_at=? WHERE id=?",
            tuple(new.values()) + (closed_at, now(), oid))
    old_vals, new_vals = audit.changes(old, new)
    if new_vals:
        audit.log(user, "Update", "Opportunity", oid, old=old_vals, new=new_vals)
    return {}


def move_stage(user, oid, stage):
    """Quick stage change from pipeline board. Returns error text or None."""
    opp = get_opp(user, oid)
    if not opp:
        return "Opportunity not found."
    if stage not in STAGES:
        return "Invalid stage."
    if not is_open_stage(opp["stage"]):
        return "Closed opportunities cannot change stage."
    if is_open_stage(stage) and to_date(opp["close_date"]) < date.today():
        return "Expected Close Date is in the past. Edit the opportunity and set a valid date first."
    closed_at = now() if not is_open_stage(stage) else None
    execute("UPDATE opportunities SET stage=?, status=?, probability=?, closed_at=?, modified_at=? WHERE id=?",
            (stage, stage_status(stage), fix_probability(stage, opp["probability"]), closed_at, now(), oid))
    audit.log(user, "Update", "Opportunity", oid, old={"stage": opp["stage"]}, new={"stage": stage})
    return None


def delete_opp(user, oid):
    require_role(user, "Admin", "Manager")
    old = query_one("SELECT * FROM opportunities WHERE id = ?", (oid,))
    if not old:
        return "Opportunity not found."
    execute("DELETE FROM opportunities WHERE id = ?", (oid,))
    audit.log(user, "Delete", "Opportunity", oid, old=old)
    return "Opportunity deleted."
