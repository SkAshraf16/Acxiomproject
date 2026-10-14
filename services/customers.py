from core import audit
from core.auth import require_role, scope
from core.db import execute, query, query_one
from core.rules import CUSTOMER_STATUS, check_choice, check_email, check_name, check_phone, now
from services.users import resolve_owner

FIELDS = ["name", "email", "phone", "company", "address", "city", "state", "status", "notes"]


def list_customers(user, search="", status=""):
    where, params = scope(user, "c")
    sql = ("SELECT c.id, c.code, c.name, c.email, c.phone, c.company, c.city, c.status, u.full_name AS owner, c.created_at "
           "FROM customers c LEFT JOIN users u ON u.id = c.assigned_to WHERE 1=1" + where)
    if search:
        sql += " AND (c.name LIKE ? OR c.email LIKE ? OR c.phone LIKE ? OR c.company LIKE ? OR c.code LIKE ?)"
        params += [f"%{search}%"] * 5
    if status:
        sql += " AND c.status = ?"
        params.append(status)
    return query(sql + " ORDER BY c.id DESC", params)


def get_customer(user, cid):
    where, params = scope(user)
    return query_one("SELECT * FROM customers WHERE id = ?" + where, [cid] + params)


def options(user):
    """id -> label, for dropdowns in other screens."""
    where, params = scope(user)
    rows = query("SELECT id, name, code FROM customers WHERE 1=1" + where + " ORDER BY name", params)
    return {r["id"]: f"{r['name']} ({r['code']})" for r in rows}


def validate(data, cid=0):
    errors = {}
    check_name(errors, "name", data.get("name"), "Customer Name")
    check_email(errors, "email", data.get("email"))
    check_phone(errors, "phone", data.get("phone"))
    check_choice(errors, "status", data.get("status"), CUSTOMER_STATUS, "status")
    for field, size in [("company", 150), ("address", 250), ("city", 60), ("state", 60), ("notes", 1000)]:
        if data.get(field) and len(data[field]) > size:
            errors[field] = f"{field.title()} must be at most {size} characters."
    # duplicate customer check - same email or phone not allowed
    if "email" not in errors and query_one("SELECT id FROM customers WHERE email = ? AND id != ?", (data["email"].strip().lower(), cid)):
        errors["email"] = "A customer with this email already exists."
    if "phone" not in errors and query_one("SELECT id FROM customers WHERE phone = ? AND id != ?", (data["phone"].strip(), cid)):
        errors["phone"] = "A customer with this phone number already exists."
    return errors


def clean(data):
    out = {f: (data.get(f) or "").strip() or None for f in FIELDS}
    out["email"] = out["email"].lower() if out["email"] else None
    return out


def next_code():
    last = query_one("SELECT MAX(id) AS m FROM customers")["m"] or 0
    return f"CUST-{last + 1:04d}"


def create_customer(user, data):
    errors = validate(data)
    owner, err = resolve_owner(user, data.get("assigned_to"))
    if err:
        errors["assigned_to"] = err
    if errors:
        return None, errors
    d = clean(data)
    code = next_code()
    cid = execute(
        "INSERT INTO customers (code, name, email, phone, company, address, city, state, status, notes, assigned_to, created_by, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (code, d["name"], d["email"], d["phone"], d["company"], d["address"], d["city"], d["state"],
         d["status"], d["notes"], owner, user["email"], now()),
    )
    audit.log(user, "Create", "Customer", cid, new={"code": code, **d})
    return cid, {}


def update_customer(user, cid, data):
    old = get_customer(user, cid)
    if not old:
        return {"_": "Customer not found."}
    errors = validate(data, cid)
    owner = old["assigned_to"]
    if user["role"] != "SalesExecutive" and data.get("assigned_to"):
        owner, err = resolve_owner(user, data["assigned_to"])
        if err:
            errors["assigned_to"] = err
    if errors:
        return errors
    d = clean(data)
    d["assigned_to"] = owner
    execute(
        "UPDATE customers SET name=?, email=?, phone=?, company=?, address=?, city=?, state=?, status=?, notes=?, assigned_to=?, modified_at=? WHERE id=?",
        (d["name"], d["email"], d["phone"], d["company"], d["address"], d["city"], d["state"], d["status"], d["notes"], owner, now(), cid),
    )
    old_vals, new_vals = audit.changes(old, d)
    if new_vals:
        audit.log(user, "Update", "Customer", cid, old=old_vals, new=new_vals)
    return {}


def delete_customer(user, cid):
    """Only Admin/Manager. If customer has opportunities we only make it Inactive."""
    require_role(user, "Admin", "Manager")
    old = query_one("SELECT * FROM customers WHERE id = ?", (cid,))
    if not old:
        return "Customer not found."
    if query_one("SELECT id FROM opportunities WHERE customer_id = ?", (cid,)):
        execute("UPDATE customers SET status = 'Inactive', modified_at = ? WHERE id = ?", (now(), cid))
        audit.log(user, "Update", "Customer", cid, old={"status": old["status"]}, new={"status": "Inactive"})
        return "Customer has opportunities, so it was made Inactive instead of deleted."
    execute("DELETE FROM customers WHERE id = ?", (cid,))
    audit.log(user, "Delete", "Customer", cid, old=old)
    return "Customer deleted."


def related(cid):
    return {
        "opportunities": query("SELECT id, name, stage, amount, close_date FROM opportunities WHERE customer_id = ?", (cid,)),
        "followups": query("SELECT id, fu_date, subject, fu_type, status FROM followups WHERE customer_id = ? ORDER BY fu_date DESC", (cid,)),
        "activities": query("SELECT id, act_date, act_type, subject, status FROM activities WHERE customer_id = ? ORDER BY act_date DESC", (cid,)),
    }


def history(entity, record_id):
    return query("SELECT created_at, user_email, action, old_value, new_value FROM audit_log WHERE entity = ? AND record_id = ? ORDER BY id DESC LIMIT 20",
                 (entity, str(record_id)))
