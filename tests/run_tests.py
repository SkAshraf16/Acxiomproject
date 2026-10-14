"""Checks all modules and rules. Run from project folder:  python tests/run_tests.py
Uses a separate test database, so your real data is not touched."""
import os
import sys
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST_DB = os.path.join(ROOT, "tests", "test.db")
if os.path.exists(TEST_DB):
    os.remove(TEST_DB)
os.environ["SMARTSALES_DB"] = TEST_DB
sys.path.insert(0, ROOT)

from core import auth                                       # noqa: E402
from core.db import query, query_one                        # noqa: E402
from core.seed import setup                                 # noqa: E402
from services import activities, customers, followups, leads, opportunities, reports, users   # noqa: E402

setup()
passed, failed = 0, 0
TODAY = date.today()
TMR = TODAY + timedelta(days=1)
YDAY = TODAY - timedelta(days=1)
LATER = TODAY + timedelta(days=40)


def check(ok, name):
    global passed, failed
    if ok:
        passed += 1
        print("PASS ", name)
    else:
        failed += 1
        print("FAIL ", name)


def raises_permission(fn):
    try:
        fn()
        return False
    except PermissionError:
        return True


def audit_has(action):
    return query_one("SELECT id FROM audit_log WHERE action = ?", (action,)) is not None


print("== Login / security ==")
admin, _ = auth.login("admin@smartsales.in", "Admin@123")
manager, _ = auth.login("manager@smartsales.in", "Manager@123")
sales, _ = auth.login("sales1@smartsales.in", "Sales@123")
check(admin and manager and sales, "demo users can login")
check("password_hash" not in admin, "session user has no password hash")
row = query_one("SELECT password_hash FROM users WHERE id = ?", (admin["id"],))
check("Admin@123" not in row["password_hash"] and "$" in row["password_hash"], "password stored as salted hash")
u, err = auth.register("Test Kumar", "test.kumar@smartsales.in", "9123456780", "weak", "weak")
check(u is None and "password" in err, "register rejects weak password")
u, err = auth.register("Test Kumar", "test.kumar@smartsales.in", "9123456780", "Test@1234", "Test@1234")
check(u and u["role"] == "SalesExecutive", "register gives SalesExecutive role")
for _ in range(4):
    _, msg = auth.login("test.kumar@smartsales.in", "Wrong@123")
check("1 attempt(s) left" in msg, "shows attempts left")
_, msg = auth.login("test.kumar@smartsales.in", "Wrong@123")
check("locked" in msg, "5 wrong passwords lock account")
_, msg = auth.login("test.kumar@smartsales.in", "Test@1234")
check(msg and "locked" in msg, "correct password blocked while locked")
users.unlock(admin, u["id"])
user2, msg = auth.login("test.kumar@smartsales.in", "Test@1234")
check(user2 is not None, "admin unlock works")

print("== Users ==")
uid, err = users.create_user(admin, {"full_name": "Neha Rao", "email": "neha@smartsales.in", "phone": "9988776655",
                                     "role": "SalesExecutive", "password": "Neha@1234", "is_active": True})
check(uid and not err, "admin creates user")
err = users.update_user(admin, uid, {"full_name": "Neha Rao", "email": "neha@smartsales.in", "phone": "9988776655",
                                     "role": "Manager", "is_active": True})
check(not err and users.get_user(uid)["role"] == "Manager", "admin changes role")
users.toggle_active(admin, uid)
_, msg = auth.login("neha@smartsales.in", "Neha@1234")
check(msg and "inactive" in msg, "inactive user cannot login")
users.toggle_active(admin, uid)
users.reset_password(admin, uid, "Fresh@5678")
check(auth.login("neha@smartsales.in", "Fresh@5678")[0] is not None, "reset password works")
check(raises_permission(lambda: users.create_user(manager, {})), "manager cannot create users")
check(raises_permission(lambda: users.list_users(sales)), "sales cannot see users")
check(users.toggle_active(admin, admin["id"]) is not None, "admin cannot deactivate self")

print("== Customers ==")
good = {"name": "Ramesh Traders", "email": "ramesh@traders.in", "phone": "9811122233", "company": "Ramesh Traders",
        "city": "Hyderabad", "state": "Telangana", "status": "Active"}
cid, err = customers.create_customer(admin, good)
check(cid and not err, "create customer")
check(customers.get_customer(admin, cid)["code"].startswith("CUST-"), "customer code generated")
_, err = customers.create_customer(admin, dict(good, name="Copy"))
check("email" in err and "phone" in err, "duplicate email/phone blocked")
_, err = customers.create_customer(admin, dict(good, email="bad-email", phone="12345"))
check(err.get("email") == "Enter a valid email address." and "phone" in err, "invalid email/phone rejected")
_, err = customers.create_customer(admin, dict(good, name=""))
check("name" in err, "required name checked")
err = customers.update_customer(admin, cid, dict(good, name="Ramesh Traders Pvt", status="Prospect"))
check(not err and customers.get_customer(admin, cid)["name"] == "Ramesh Traders Pvt", "edit customer")
check(any(h["action"] == "Update" and "Pvt" in h["new_value"] for h in customers.history("Customer", cid)), "history has old/new values")
check(any(r["id"] == cid for r in customers.list_customers(admin, "ramesh")), "search customers")
check(raises_permission(lambda: customers.delete_customer(sales, cid)), "sales cannot delete")
other = query_one("SELECT id FROM customers WHERE assigned_to != ?", (sales["id"],))["id"]
check(customers.get_customer(sales, other) is None, "sales cannot open other owner customer")
check(customers.update_customer(sales, other, good) == {"_": "Customer not found."}, "sales cannot edit other owner customer")
mine = len(customers.list_customers(sales))
check(0 < mine < len(customers.list_customers(admin)), "sales sees only own customers")

print("== Leads ==")
lead = {"name": "Sunil Joshi", "email": "sunil@joshi.in", "phone": "9822233344", "company": "Joshi Steels",
        "source": "Referral", "status": "New", "priority": "High", "expected_value": 450000}
lid, err = leads.create_lead(sales, lead)
check(lid and leads.get_lead(sales, lid)["assigned_to"] == sales["id"], "sales creates lead (assigned to self)")
check("status" in leads.update_lead(sales, lid, dict(lead, status="Qualified")), "invalid status jump blocked")
check("expected_value" in leads.create_lead(sales, dict(lead, expected_value=999999999))[1], "expected value range")
_, err = leads.create_lead(sales, dict(lead, source="Hacked", status="Lost"))
check("source" in err and "status" in err, "invalid source/status rejected")
check(leads.convert_lead(sales, lid)[1] == "Only Qualified leads can be converted.", "convert blocked before Qualified")
leads.update_lead(sales, lid, dict(lead, status="Contacted"))
check(not leads.update_lead(sales, lid, dict(lead, status="Qualified")), "New -> Contacted -> Qualified")
oid, err = leads.convert_lead(sales, lid)
check(oid and not err, "convert lead")
check(leads.get_lead(sales, lid)["status"] == "Converted", "lead marked Converted")
check(opportunities.get_opp(sales, oid)["lead_id"] == lid, "opportunity linked to lead")
check(any(c["name"] == "Sunil Joshi" for c in customers.list_customers(sales)), "customer created from lead")
check(leads.update_lead(sales, lid, lead) == {"_": "Converted leads cannot be edited."}, "converted lead locked")
check(audit_has("Convert"), "conversion audited")

print("== Opportunities ==")
opp = {"name": "Big Deal", "customer_id": cid, "amount": 500000, "probability": 40, "stage": "Proposal", "close_date": LATER}
o2, err = opportunities.create_opp(admin, opp)
check(o2 and not err, "create opportunity")
_, err = opportunities.create_opp(admin, dict(opp, amount=0, probability=101, close_date=YDAY))
check(err.get("amount") == "Opportunity Amount must be greater than 0." and err.get("probability") == "Probability must be between 0 and 100."
      and err.get("close_date") == "Expected Close Date cannot be in the past.", "amount / probability / close date rules")
check("stage" in opportunities.create_opp(admin, dict(opp, stage="Won"))[1], "new opp cannot start Won")
check("customer_id" in opportunities.create_opp(sales, dict(opp, customer_id=other))[1], "sales cannot use other customer")
err = opportunities.update_opp(admin, o2, dict(opp, amount=600000, probability=60, stage="Negotiation"))
check(not err and opportunities.weighted(600000, 60) == 360000, "edit opp + weighted amount")
check(opportunities.move_stage(admin, o2, "Won") is None and opportunities.get_opp(admin, o2)["status"] == "Won", "move to Won")
check(opportunities.get_opp(admin, o2)["probability"] == 100, "Won sets probability 100")
check("stage" in opportunities.update_opp(admin, o2, dict(opp, stage="Proposal")), "Won cannot be reopened")
check(not opportunities.update_opp(admin, o2, dict(opp, stage="Won", close_date=YDAY)), "past date allowed for closed opp")
msg = customers.delete_customer(admin, cid)
check("Inactive" in msg and customers.get_customer(admin, cid)["status"] == "Inactive", "customer with opps deactivated")
check(opportunities.delete_opp(admin, oid) == "Opportunity deleted.", "delete opportunity")

print("== Follow-ups ==")
fu = {"lead_id": lid, "subject": "Send quote", "fu_type": "Call", "fu_date": YDAY}
_, err = followups.create_followup(sales, dict(fu))
check(err.get("fu_date") == "Follow-up date cannot be earlier than today.", "past follow-up date rejected")
check("related" in followups.create_followup(sales, {"subject": "No link", "fu_type": "Call", "fu_date": TMR})[1], "needs customer or lead")
fid, err = followups.create_followup(sales, dict(fu, fu_date=TODAY))
check(fid and not err, "schedule follow-up")
check(not followups.update_followup(sales, fid, dict(fu, fu_date=TMR, status="Planned", fu_type="Meeting")), "reschedule follow-up")
check(followups.set_status(sales, fid, "Completed") is None, "complete follow-up")
check(followups.set_status(sales, fid, "Missed") == "Only planned follow-ups can be updated.", "completed cannot change again")
check(isinstance(followups.list_followups(sales, "overdue"), list), "overdue list")
check(followups.delete_followup(admin, fid) == "Follow-up deleted.", "delete follow-up")

print("== Activities ==")
act = {"act_type": "Meeting", "subject": "Site visit", "act_date": TODAY, "lead_id": lid, "status": "Planned"}
aid, err = activities.create_activity(sales, dict(act))
check(aid and not err, "log activity")
check("act_date" in activities.create_activity(sales, dict(act, act_date=YDAY))[1], "planned activity in past rejected")
check(not activities.update_activity(sales, aid, dict(act, status="Completed", subject="Site visit done")), "edit activity")
check(activities.delete_activity(admin, aid) == "Activity deleted.", "delete activity")
check(raises_permission(lambda: activities.delete_activity(sales, 1)), "sales cannot delete activity")

print("== Dashboard / reports ==")
for choice in ["All Time", "Today", "This Week", "This Month"]:
    d_from, d_to = reports.date_range(choice)
    stats = reports.dashboard(sales, d_from, d_to)[0]
    check("Total Pipeline Value" in stats, f"dashboard {choice}")
check(reports.dashboard(sales)[0]["Total Customers"] < reports.dashboard(admin)[0]["Total Customers"], "dashboard scoped by role")
check(len(reports.customer_report(admin)) > 0 and len(reports.lead_report(admin)) > 0, "customer and lead reports")
check(isinstance(reports.followup_report(admin), list) and len(reports.opportunity_report(admin)) > 0, "follow-up and opportunity reports")
check(len(reports.pipeline_report(admin)[0]) > 0, "pipeline report")
check(reports.conversion_report(admin)["total_leads"] > 0, "conversion report")
check(len(reports.user_activity_report(manager)) > 0, "user activity report")
check(raises_permission(lambda: reports.user_activity_report(sales)), "sales blocked from user activity")
check(raises_permission(lambda: reports.audit_report(manager)), "manager blocked from audit log")

print("== Audit ==")
for action in ["Login", "FailedLogin", "Lockout", "Unlock", "Register", "RoleChange", "Deactivate", "Activate",
               "PasswordReset", "Convert", "Create", "Update", "Delete"]:
    check(audit_has(action), f"audit has {action}")
check(not query("SELECT id FROM audit_log WHERE new_value LIKE '%Test@1234%' OR new_value LIKE '%password%'"), "no passwords in audit")

print("== REST API ==")
from fastapi.testclient import TestClient   # noqa: E402
import api                                   # noqa: E402

client = TestClient(api.app)
check(client.get("/api/customers").status_code == 401, "API needs login (401)")
tok_admin = client.post("/api/auth/login", json={"email": "admin@smartsales.in", "password": "Admin@123"}).json()["token"]
tok_sales = client.post("/api/auth/login", json={"email": "sales1@smartsales.in", "password": "Sales@123"}).json()["token"]
A = {"Authorization": f"Bearer {tok_admin}"}
S = {"Authorization": f"Bearer {tok_sales}"}
body = {"name": "Api Cust", "email": "api.cust@x.in", "phone": "9700011122"}
r = client.post("/api/customers", json=body, headers=A)
check(r.status_code == 201, "POST /api/customers 201")
new_id = r.json()["id"]
check(client.post("/api/customers", json=body, headers=A).status_code == 409, "duplicate 409")
check(client.post("/api/customers", json={"name": "", "email": "x", "phone": "1"}, headers=A).status_code == 400, "invalid 400")
check(client.put(f"/api/customers/{new_id}", json=dict(body, status="Prospect"), headers=A).json()["status"] == "Prospect", "PUT customer")
check(client.get("/api/customers/99999", headers=A).status_code == 404, "unknown id 404")
check(client.delete(f"/api/customers/{new_id}", headers=S).status_code == 403, "sales DELETE 403")
check(client.delete(f"/api/customers/{new_id}", headers=A).status_code == 204, "admin DELETE 204")
check(client.post("/api/leads", json={"name": "Api Lead", "source": "Website", "expected_value": 1000}, headers=S).status_code == 201, "POST lead")
my_cust = client.get("/api/customers", headers=S).json()[0]["id"]
opp_body = {"name": "Api Opp", "customer_id": my_cust, "amount": 1000, "probability": 30, "close_date": LATER.isoformat()}
check(client.post("/api/opportunities", json=opp_body, headers=S).status_code == 201, "POST opportunity")
check(client.post("/api/opportunities", json=dict(opp_body, amount=0, probability=150), headers=S).status_code == 400, "opp rules 400")
check(client.post("/api/followups", json={"customer_id": my_cust, "subject": "Api call", "fu_date": YDAY.isoformat()}, headers=S).status_code == 400, "past follow-up 400")
check(client.post("/api/followups", json={"customer_id": my_cust, "subject": "Api call", "fu_date": TMR.isoformat()}, headers=S).status_code == 201, "POST follow-up")
for path in ["/api/leads", "/api/opportunities", "/api/followups", "/api/reports/pipeline"]:
    check(client.get(path, headers=S).status_code == 200, f"GET {path}")
check("password" not in client.get("/api/customers", headers=A).text.lower(), "API never returns passwords")
check(client.post("/api/auth/logout", headers=S).status_code == 200, "API logout")
check(client.get("/api/leads", headers=S).status_code == 401, "token invalid after logout")
codes = [client.post("/api/auth/login", json={"email": "x@x.in", "password": "x"}).status_code for _ in range(6)]
check(429 in codes, "login rate limit 429")

print("== Screens (each page opens for each role) ==")
from streamlit.testing.v1 import AppTest     # noqa: E402

PAGES = {
    "dashboard_page.show": ["Admin", "Manager", "SalesExecutive"],
    "customers_page.show": ["Admin", "Manager", "SalesExecutive"],
    "leads_page.show": ["Admin", "Manager", "SalesExecutive"],
    "opportunities_page.show": ["Admin", "Manager", "SalesExecutive"],
    "opportunities_page.pipeline": ["Admin", "Manager", "SalesExecutive"],
    "followups_page.show": ["Admin", "Manager", "SalesExecutive"],
    "activities_page.show": ["Admin", "Manager", "SalesExecutive"],
    "reports_page.show": ["Admin", "Manager", "SalesExecutive"],
    "users_page.show": ["Admin", "Manager"],
    "audit_page.show": ["Admin"],
}
role_user = {"Admin": admin, "Manager": manager, "SalesExecutive": sales}
for page, roles in PAGES.items():
    module, func = page.split(".")
    for role in roles:
        script = (f"import os, sys\nos.environ['SMARTSALES_DB'] = {TEST_DB!r}\nsys.path.insert(0, {ROOT!r})\n"
                  f"from screens import {module}\n{module}.{func}()\n")
        at = AppTest.from_string(script, default_timeout=30)
        at.session_state["user"] = role_user[role]
        at.run()
        check(not at.exception, f"{page} opens for {role}")

at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=30)
at.run()
at.text_input[0].input("admin@smartsales.in")
at.text_input[1].input("Admin@123")
at.button[0].click()
at.run()
check(at.session_state["user"]["role"] == "Admin" and not at.exception, "login form works in app")

print(f"\nRESULT: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
