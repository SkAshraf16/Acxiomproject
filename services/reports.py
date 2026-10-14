from datetime import date, timedelta

from core.auth import require_role, scope
from core.db import query, query_one
from core.rules import STAGES


def date_range(choice, start=None, end=None):
    """Dashboard filter -> (from_date, to_date) as text, or (None, None) for all time."""
    t = date.today()
    if choice == "Today":
        return t.isoformat(), t.isoformat()
    if choice == "This Week":
        return (t - timedelta(days=t.weekday())).isoformat(), t.isoformat()
    if choice == "This Month":
        return t.replace(day=1).isoformat(), t.isoformat()
    if choice == "Custom" and start and end:
        return start.isoformat(), end.isoformat()
    return None, None


def dashboard(user, d_from=None, d_to=None):
    where, params = scope(user)
    period, pparams = "", []
    if d_from:
        period = " AND DATE(created_at) BETWEEN ? AND ?"
        pparams = [d_from, d_to]

    def count(table, extra=""):
        return query_one(f"SELECT COUNT(*) AS n FROM {table} WHERE 1=1{where}{period}{extra}", params + pparams)["n"]

    opps = query(f"SELECT stage, status, amount, probability, close_date, closed_at FROM opportunities WHERE 1=1{where}{period}", params + pparams)
    open_opps = [o for o in opps if o["status"] == "Open"]

    stats = {
        "Total Customers": count("customers"),
        "Total Leads": count("leads"),
        "Open Leads": count("leads", " AND status IN ('New', 'Contacted', 'Qualified')"),
        "Total Opportunities": len(opps),
        "Open Opportunities": len(open_opps),
        "Won Opportunities": sum(1 for o in opps if o["status"] == "Won"),
        "Lost Opportunities": sum(1 for o in opps if o["status"] == "Lost"),
        "Total Pipeline Value": sum(o["amount"] for o in open_opps),
        "Weighted Pipeline": sum(o["amount"] * o["probability"] / 100 for o in open_opps),
    }
    stats["Pending Follow-Ups"] = query_one(f"SELECT COUNT(*) AS n FROM followups WHERE status = 'Planned'{where}", params)["n"]
    stats["Overdue Follow-Ups"] = query_one(
        f"SELECT COUNT(*) AS n FROM followups WHERE status = 'Planned' AND fu_date < DATE('now', 'localtime'){where}", params)["n"]

    lead_rows = query(f"SELECT status, COUNT(*) AS n FROM leads WHERE 1=1{where}{period} GROUP BY status", params + pparams)
    lead_chart = {s: 0 for s in ["New", "Contacted", "Qualified", "Lost", "Converted"]}
    for r in lead_rows:
        if r["status"] in lead_chart:
            lead_chart[r["status"]] = r["n"]

    pipe_chart = {s: sum(o["amount"] for o in opps if o["stage"] == s) for s in STAGES}

    # monthly won amount for last 12 months
    months = {}
    first = date.today().replace(day=1)
    for i in range(11, -1, -1):
        y, m = first.year, first.month - i
        while m <= 0:
            m += 12
            y -= 1
        months[f"{y}-{m:02d}"] = 0
    for o in opps:
        if o["status"] == "Won":
            key = (o["closed_at"] or o["close_date"])[:7]
            if key in months:
                months[key] += o["amount"]

    upcoming = query(
        f"SELECT f.fu_date, f.subject, COALESCE(c.name, l.name) AS related_to FROM followups f "
        f"LEFT JOIN customers c ON c.id = f.customer_id LEFT JOIN leads l ON l.id = f.lead_id "
        f"WHERE f.status = 'Planned'{scope(user, 'f')[0]} ORDER BY f.fu_date LIMIT 6", scope(user, "f")[1])

    return stats, lead_chart, pipe_chart, months, upcoming


def admin_stats():
    return {
        "users": query_one("SELECT COUNT(*) AS n FROM users")["n"],
        "failed_today": query_one("SELECT COUNT(*) AS n FROM audit_log WHERE action = 'FailedLogin' AND DATE(created_at) = DATE('now', 'localtime')")["n"],
        "recent": query("SELECT created_at, user_email, action, entity, record_id FROM audit_log ORDER BY id DESC LIMIT 6"),
    }


def _period(sql, params, column, d_from, d_to):
    if d_from:
        sql += f" AND DATE({column}) >= ?"
        params.append(d_from.isoformat())
    if d_to:
        sql += f" AND DATE({column}) <= ?"
        params.append(d_to.isoformat())
    return sql, params


def customer_report(user, d_from=None, d_to=None, status=""):
    where, params = scope(user, "c")
    sql = ("SELECT c.code, c.name, c.company, c.email, c.phone, c.status, u.full_name AS owner, c.created_at "
           "FROM customers c LEFT JOIN users u ON u.id = c.assigned_to WHERE 1=1" + where)
    sql, params = _period(sql, params, "c.created_at", d_from, d_to)
    if status:
        sql += " AND c.status = ?"
        params.append(status)
    return query(sql + " ORDER BY c.name", params)


def lead_report(user, d_from=None, d_to=None, status=""):
    where, params = scope(user, "l")
    sql = ("SELECT l.code, l.name, l.source, l.status, l.priority, l.expected_value, u.full_name AS owner, l.created_at, l.converted_at "
           "FROM leads l LEFT JOIN users u ON u.id = l.assigned_to WHERE 1=1" + where)
    sql, params = _period(sql, params, "l.created_at", d_from, d_to)
    if status:
        sql += " AND l.status = ?"
        params.append(status)
    return query(sql + " ORDER BY l.created_at DESC", params)


def followup_report(user, d_from=None, d_to=None, status=""):
    where, params = scope(user, "f")
    sql = ("SELECT f.fu_date, f.subject, f.fu_type, COALESCE(c.name, l.name) AS related_to, f.status, "
           "CASE WHEN f.status = 'Planned' AND f.fu_date < DATE('now', 'localtime') THEN 'Yes' ELSE 'No' END AS overdue, "
           "u.full_name AS owner FROM followups f LEFT JOIN customers c ON c.id = f.customer_id "
           "LEFT JOIN leads l ON l.id = f.lead_id LEFT JOIN users u ON u.id = f.assigned_to WHERE 1=1" + where)
    sql, params = _period(sql, params, "f.fu_date", d_from, d_to)
    if status:
        sql += " AND f.status = ?"
        params.append(status)
    return query(sql + " ORDER BY f.fu_date", params)


def opportunity_report(user, d_from=None, d_to=None, stage=""):
    where, params = scope(user, "o")
    sql = ("SELECT o.name, c.name AS customer, o.stage, o.amount, o.probability, ROUND(o.amount * o.probability / 100.0, 2) AS weighted, "
           "o.close_date, u.full_name AS owner FROM opportunities o JOIN customers c ON c.id = o.customer_id "
           "LEFT JOIN users u ON u.id = o.assigned_to WHERE 1=1" + where)
    sql, params = _period(sql, params, "o.close_date", d_from, d_to)
    if stage:
        sql += " AND o.stage = ?"
        params.append(stage)
    return query(sql + " ORDER BY o.close_date", params)


def pipeline_report(user):
    where, params = scope(user, "o")
    by_stage = query("SELECT o.stage, COUNT(*) AS count, SUM(o.amount) AS amount, ROUND(SUM(o.amount * o.probability / 100.0), 2) AS weighted "
                     "FROM opportunities o WHERE 1=1" + where + " GROUP BY o.stage", params)
    order = {s: i for i, s in enumerate(STAGES)}
    by_stage.sort(key=lambda r: order.get(r["stage"], 99))
    by_owner = query("SELECT COALESCE(u.full_name, 'Unassigned') AS owner, COUNT(*) AS count, SUM(o.amount) AS amount, "
                     "ROUND(SUM(o.amount * o.probability / 100.0), 2) AS weighted FROM opportunities o "
                     "LEFT JOIN users u ON u.id = o.assigned_to WHERE o.status = 'Open'" + where +
                     " GROUP BY owner ORDER BY amount DESC", params)
    return by_stage, by_owner


def conversion_report(user):
    where, params = scope(user)
    leads = query("SELECT source, status FROM leads WHERE 1=1" + where, params)
    opps = query("SELECT status, amount FROM opportunities WHERE 1=1" + where, params)
    total = len(leads)
    converted = sum(1 for l in leads if l["status"] == "Converted")
    won = [o for o in opps if o["status"] == "Won"]
    lost = sum(1 for o in opps if o["status"] == "Lost")
    by_source = {}
    for l in leads:
        row = by_source.setdefault(l["source"], {"source": l["source"], "leads": 0, "converted": 0})
        row["leads"] += 1
        if l["status"] == "Converted":
            row["converted"] += 1
    for row in by_source.values():
        row["rate %"] = round(row["converted"] * 100 / row["leads"], 1)
    return {
        "total_leads": total,
        "converted": converted,
        "conversion_rate": round(converted * 100 / total, 1) if total else 0,
        "won": len(won),
        "lost": lost,
        "win_rate": round(len(won) * 100 / (len(won) + lost), 1) if (won or lost) else 0,
        "won_value": sum(o["amount"] for o in won),
        "by_source": sorted(by_source.values(), key=lambda r: -r["leads"]),
    }


def user_activity_report(user, d_from=None, d_to=None):
    require_role(user, "Admin", "Manager")
    sql = ("SELECT user_email AS user, COUNT(*) AS total, SUM(action = 'Login') AS logins, SUM(action = 'Create') AS creates, "
           "SUM(action = 'Update') AS updates, SUM(action = 'Delete') AS deletes FROM audit_log WHERE user_email IS NOT NULL")
    sql, params = _period(sql, [], "created_at", d_from, d_to)
    return query(sql + " GROUP BY user_email ORDER BY total DESC", params)


def audit_report(user, email="", entity="", action="", d_from=None, d_to=None):
    require_role(user, "Admin")
    sql = "SELECT id, created_at, user_email, action, entity, record_id, result, old_value, new_value FROM audit_log WHERE 1=1"
    params = []
    if email:
        sql += " AND user_email LIKE ?"
        params.append(f"%{email}%")
    if entity:
        sql += " AND entity = ?"
        params.append(entity)
    if action:
        sql += " AND action = ?"
        params.append(action)
    sql, params = _period(sql, params, "created_at", d_from, d_to)
    return query(sql + " ORDER BY id DESC LIMIT 2000", params)


def audit_filters():
    return ([r["entity"] for r in query("SELECT DISTINCT entity FROM audit_log ORDER BY entity")],
            [r["action"] for r in query("SELECT DISTINCT action FROM audit_log ORDER BY action")])
