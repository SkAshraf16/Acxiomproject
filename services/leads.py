from core import audit
from core.auth import require_role, scope
from core.db import execute, get_conn, query, query_one
from core.rules import (LEAD_FLOW, LEAD_PRIORITY, LEAD_SOURCES, LEAD_STATUS, check_choice, check_email,
                        check_name, check_phone, now)
from datetime import date, timedelta
from services.customers import next_code as next_customer_code
from services.users import resolve_owner


def list_leads(user, search="", status="", owner=None):
    where, params = scope(user, "l")
    sql = ("SELECT l.id, l.code, l.name, l.company, l.source, l.status, l.priority, l.expected_value, u.full_name AS owner, l.created_at "
           "FROM leads l LEFT JOIN users u ON u.id = l.assigned_to WHERE 1=1" + where)
    if search:
        sql += " AND (l.name LIKE ? OR l.company LIKE ? OR l.email LIKE ? OR l.code LIKE ?)"
        params += [f"%{search}%"] * 4
    if status:
        sql += " AND l.status = ?"
        params.append(status)
    if owner:
        sql += " AND l.assigned_to = ?"
        params.append(owner)
    return query(sql + " ORDER BY l.id DESC", params)


def get_lead(user, lid):
    where, params = scope(user)
    return query_one("SELECT * FROM leads WHERE id = ?" + where, [lid] + params)


def options(user):
    where, params = scope(user)
    rows = query("SELECT id, name, code FROM leads WHERE status != 'Converted'" + where + " ORDER BY name", params)
    return {r["id"]: f"{r['name']} ({r['code']})" for r in rows}


def next_statuses(current):
    return [current] + LEAD_FLOW[current]


def validate(data):
    errors = {}
    check_name(errors, "name", data.get("name"), "Lead Name")
    check_email(errors, "email", data.get("email"), required=False)
    check_phone(errors, "phone", data.get("phone"), required=False)
    check_choice(errors, "source", data.get("source"), LEAD_SOURCES, "lead source")
    check_choice(errors, "status", data.get("status"), LEAD_STATUS, "lead status")
    check_choice(errors, "priority", data.get("priority"), LEAD_PRIORITY, "priority")
    try:
        value = float(data.get("expected_value") or 0)
        if not 0 <= value <= 100000000:
            errors["expected_value"] = "Expected Value must be between 0 and 10,00,00,000."
    except ValueError:
        errors["expected_value"] = "Expected Value must be a number."
    if data.get("status") == "Converted":
        errors["status"] = "Use the Convert button to convert a lead."
    return errors


def create_lead(user, data):
    errors = validate(data)
    if data.get("status") not in ("New", "Contacted"):
        errors["status"] = "A new lead must start as New or Contacted."
    owner, err = resolve_owner(user, data.get("assigned_to"))
    if err:
        errors["assigned_to"] = err
    if errors:
        return None, errors
    last = query_one("SELECT MAX(id) AS m FROM leads")["m"] or 0
    code = f"LEAD-{last + 1:04d}"
    lid = execute(
        "INSERT INTO leads (code, name, email, phone, company, source, status, priority, expected_value, notes, assigned_to, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (code, data["name"].strip(), (data.get("email") or "").strip().lower() or None, data.get("phone") or None,
         data.get("company") or None, data["source"], data["status"], data["priority"],
         float(data.get("expected_value") or 0), data.get("notes") or None, owner, now()),
    )
    audit.log(user, "Create", "Lead", lid, new={"code": code, "name": data["name"], "status": data["status"]})
    return lid, {}


def update_lead(user, lid, data):
    old = get_lead(user, lid)
    if not old:
        return {"_": "Lead not found."}
    if old["status"] == "Converted":
        return {"_": "Converted leads cannot be edited."}
    errors = validate(data)
    # workflow check - only allowed next status
    if "status" not in errors and data["status"] != old["status"] and data["status"] not in LEAD_FLOW[old["status"]]:
        errors["status"] = f"Lead status cannot change from {old['status']} to {data['status']}."
    owner = old["assigned_to"]
    if user["role"] != "SalesExecutive" and data.get("assigned_to"):
        owner, err = resolve_owner(user, data["assigned_to"])
        if err:
            errors["assigned_to"] = err
    if errors:
        return errors
    new = {"name": data["name"].strip(), "email": (data.get("email") or "").strip().lower() or None,
           "phone": data.get("phone") or None, "company": data.get("company") or None, "source": data["source"],
           "status": data["status"], "priority": data["priority"], "expected_value": float(data.get("expected_value") or 0),
           "notes": data.get("notes") or None, "assigned_to": owner}
    execute("UPDATE leads SET name=?, email=?, phone=?, company=?, source=?, status=?, priority=?, expected_value=?, notes=?, assigned_to=?, modified_at=? WHERE id=?",
            tuple(new.values()) + (now(), lid))
    old_vals, new_vals = audit.changes(old, new)
    if new_vals:
        audit.log(user, "Update", "Lead", lid, old=old_vals, new=new_vals)
    return {}


def convert_lead(user, lid):
    """Qualified lead -> Customer (or link existing one) + new Opportunity. All in one transaction."""
    lead = get_lead(user, lid)
    if not lead:
        return None, "Lead not found."
    if lead["status"] != "Qualified":
        return None, "Only Qualified leads can be converted."
    if not lead["email"] or not lead["phone"]:
        return None, "Lead must have email and phone before conversion."

    conn = get_conn()
    try:
        cur = conn.cursor()
        row = cur.execute("SELECT id FROM customers WHERE email = ? OR phone = ?", (lead["email"], lead["phone"])).fetchone()
        if row:
            cid = row["id"]
        else:
            cur.execute(
                "INSERT INTO customers (code, name, email, phone, company, status, notes, assigned_to, created_by, created_at) "
                "VALUES (?, ?, ?, ?, ?, 'Active', ?, ?, ?, ?)",
                (next_customer_code(), lead["name"], lead["email"], lead["phone"], lead["company"],
                 f"Converted from lead {lead['code']}", lead["assigned_to"], user["email"], now()),
            )
            cid = cur.lastrowid
        cur.execute(
            "INSERT INTO opportunities (name, customer_id, lead_id, amount, stage, probability, close_date, status, source, assigned_to, created_at) "
            "VALUES (?, ?, ?, ?, 'Qualification', 20, ?, 'Open', ?, ?, ?)",
            (f"{lead['company'] or lead['name']} - {lead['source']}", cid, lid, lead["expected_value"] or 1,
             (date.today() + timedelta(days=30)).isoformat(), lead["source"], lead["assigned_to"], now()),
        )
        oid = cur.lastrowid
        cur.execute("UPDATE leads SET status='Converted', converted_customer_id=?, converted_at=?, modified_at=? WHERE id=?",
                    (cid, now(), now(), lid))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    audit.log(user, "Convert", "Lead", lid, new={"customer_id": cid, "opportunity_id": oid})
    return oid, None


def delete_lead(user, lid):
    require_role(user, "Admin", "Manager")
    old = query_one("SELECT * FROM leads WHERE id = ?", (lid,))
    if not old:
        return "Lead not found."
    execute("DELETE FROM leads WHERE id = ?", (lid,))
    audit.log(user, "Delete", "Lead", lid, old=old)
    return "Lead deleted."


def related(lid):
    return {
        "followups": query("SELECT id, fu_date, subject, status FROM followups WHERE lead_id = ? ORDER BY fu_date DESC", (lid,)),
        "activities": query("SELECT id, act_date, act_type, subject FROM activities WHERE lead_id = ? ORDER BY act_date DESC", (lid,)),
    }
