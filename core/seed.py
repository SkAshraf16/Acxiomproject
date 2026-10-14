import random
from datetime import date, timedelta

from core.auth import hash_password
from core.db import create_tables, execute, query_one
from core.rules import LEAD_SOURCES, now

DEMO_USERS = [
    ("System Admin", "admin@smartsales.in", "9000000001", "Admin@123", "Admin"),
    ("Meera Manager", "manager@smartsales.in", "9000000002", "Manager@123", "Manager"),
    ("Ravi Kumar", "sales1@smartsales.in", "9000000003", "Sales@123", "SalesExecutive"),
    ("Priya Sharma", "sales2@smartsales.in", "9000000004", "Sales@123", "SalesExecutive"),
]


def setup():
    """Create tables and put demo data only on first run."""
    create_tables()
    if query_one("SELECT id FROM users LIMIT 1"):
        return

    ids = {}
    for name, email, phone, pwd, role in DEMO_USERS:
        ids[email] = execute(
            "INSERT INTO users (full_name, email, phone, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (name, email, phone, hash_password(pwd), role, now()))
    owners = [ids["sales1@smartsales.in"], ids["sales2@smartsales.in"]]

    rnd = random.Random(42)
    t = date.today()
    companies = ["Tata Digital", "Infosys", "Wipro", "HCL Tech", "Reliance Retail", "Mahindra Logistics",
                 "Zoho", "Freshworks", "Byju's", "Swiggy", "Zomato", "Paytm"]
    names = ["Arjun Mehta", "Sneha Reddy", "Vikram Singh", "Anjali Gupta", "Rahul Verma", "Kavya Nair",
             "Suresh Iyer", "Pooja Patel", "Aditya Rao", "Neha Joshi", "Karan Malhotra", "Divya Menon"]
    cities = [("Hyderabad", "Telangana"), ("Bengaluru", "Karnataka"), ("Chennai", "Tamil Nadu"),
              ("Mumbai", "Maharashtra"), ("Pune", "Maharashtra"), ("Delhi", "Delhi")]

    cust_ids = []
    for i, name in enumerate(names):
        city, state = cities[i % len(cities)]
        created = (t - timedelta(days=rnd.randint(5, 300))).isoformat() + " 10:00:00"
        cust_ids.append(execute(
            "INSERT INTO customers (code, name, email, phone, company, address, city, state, status, assigned_to, created_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'admin@smartsales.in', ?)",
            (f"CUST-{i + 1:04d}", name, name.lower().replace(" ", ".") + "@example.com", f"98{rnd.randint(10000000, 99999999)}",
             companies[i], f"{rnd.randint(1, 200)}, MG Road", city, state, "Prospect" if i % 5 == 4 else "Active",
             owners[i % 2], created)))

    lead_names = ["Rohit Bansal", "Isha Kapoor", "Manoj Pillai", "Ritu Saxena", "Amit Chawla",
                  "Nisha Agarwal", "Gaurav Sinha", "Swati Desai", "Harish Kulkarni", "Tanvi Bhatt"]
    lead_status = ["New", "Contacted", "Qualified", "Lost", "Converted", "New", "Contacted", "Qualified", "Unqualified", "New"]
    for i, name in enumerate(lead_names):
        execute(
            "INSERT INTO leads (code, name, email, phone, company, source, status, priority, expected_value, assigned_to, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (f"LEAD-{i + 1:04d}", name, name.lower().replace(" ", ".") + "@prospect.in", f"97{rnd.randint(10000000, 99999999)}",
             name.split()[1] + " Enterprises", LEAD_SOURCES[i % len(LEAD_SOURCES)], lead_status[i],
             ["Low", "Medium", "High"][i % 3], rnd.randint(50, 900) * 1000, owners[i % 2],
             (t - timedelta(days=rnd.randint(1, 120))).isoformat() + " 11:00:00"))

    stages = ["Qualification", "Proposal", "Negotiation", "Won", "Lost"]
    prob = {"Qualification": 20, "Proposal": 50, "Negotiation": 75, "Won": 100, "Lost": 0}
    for i in range(18):
        stage = stages[i % 5]
        closed = stage in ("Won", "Lost")
        cid = cust_ids[i % len(cust_ids)]
        owner = owners[i % len(cust_ids) % 2]
        close = t - timedelta(days=rnd.randint(5, 300)) if closed else t + timedelta(days=rnd.randint(10, 120))
        execute(
            "INSERT INTO opportunities (name, customer_id, amount, stage, probability, close_date, status, source, assigned_to, created_at, closed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (f"{companies[i % len(companies)]} - {'CRM Licences' if i % 2 == 0 else 'Data Services'}", cid,
             rnd.randint(100, 2500) * 1000, stage, prob[stage], close.isoformat(),
             "Won" if stage == "Won" else "Lost" if stage == "Lost" else "Open", LEAD_SOURCES[i % len(LEAD_SOURCES)],
             owner, (t - timedelta(days=rnd.randint(30, 320))).isoformat() + " 12:00:00",
             close.isoformat() + " 17:00:00" if closed else None))

    subjects = ["Product demo", "Pricing discussion", "Contract review", "Requirement call", "Quarterly check-in"]
    for i in range(10):
        owner = owners[i % 2]
        done = i < 2
        execute(
            "INSERT INTO followups (customer_id, fu_date, fu_type, subject, remarks, status, assigned_to, created_at, completed_at) "
            "VALUES (?, ?, ?, ?, 'Sample follow-up', ?, ?, ?, ?)",
            (cust_ids[i], (t + timedelta(days=i - 3)).isoformat(), ["Call", "Meeting", "Email", "Visit"][i % 4],
             subjects[i % 5], "Completed" if done else "Planned", owner, now(), now() if done else None))
        execute(
            "INSERT INTO activities (act_type, subject, description, act_date, customer_id, status, assigned_to, created_at) "
            "VALUES (?, ?, 'Sample activity', ?, ?, ?, ?, ?)",
            (["Call", "Meeting", "Email", "Task"][i % 4], subjects[(i + 2) % 5], (t - timedelta(days=i)).isoformat(),
             cust_ids[i], "Planned" if i % 3 == 0 else "Completed", owner, now()))
