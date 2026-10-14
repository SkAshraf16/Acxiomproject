import re
from datetime import date, datetime

# fixed lists used in dropdowns and checks
ROLES = ["Admin", "Manager", "SalesExecutive"]
CUSTOMER_STATUS = ["Active", "Prospect", "Inactive"]
LEAD_STATUS = ["New", "Contacted", "Qualified", "Unqualified", "Converted", "Lost"]
LEAD_PRIORITY = ["Low", "Medium", "High"]
LEAD_SOURCES = ["Website", "Referral", "Email Campaign", "Cold Call", "Social Media", "Event", "Other"]
STAGES = ["Qualification", "Proposal", "Negotiation", "Won", "Lost"]
FU_STATUS = ["Planned", "Completed", "Missed", "Cancelled"]
FU_TYPES = ["Call", "Meeting", "Email", "Visit"]
ACT_TYPES = ["Call", "Meeting", "Email", "Task"]
ACT_STATUS = ["Planned", "Completed", "Cancelled"]

# lead workflow - which status can go to which
LEAD_FLOW = {
    "New": ["Contacted", "Unqualified", "Lost"],
    "Contacted": ["Qualified", "Unqualified", "Lost"],
    "Qualified": ["Contacted", "Lost"],
    "Unqualified": ["Contacted", "Lost"],
    "Converted": [],
    "Lost": [],
}

PHONE_RE = re.compile(r"^[6-9]\d{9}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
NAME_RE = re.compile(r"^[A-Za-z0-9 .,'&()\-]+$")
PASSWORD_RE = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,}$")

MSG_EMAIL = "Enter a valid email address."
MSG_PHONE = "Enter a valid phone number (10 digit mobile starting with 6-9)."
MSG_AMOUNT = "Opportunity Amount must be greater than 0."
MSG_PROB = "Probability must be between 0 and 100."
MSG_CLOSE_DATE = "Expected Close Date cannot be in the past."
MSG_FU_DATE = "Follow-up date cannot be earlier than today."
MSG_PASSWORD = "Password must be at least 8 characters with upper case, lower case, number and special character."


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today():
    return date.today().isoformat()


def to_date(value):
    """Accept date object or 'YYYY-MM-DD' text."""
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def check_required(errors, field, value, label):
    if value is None or str(value).strip() == "":
        errors[field] = f"{label} is required."
        return False
    return True


def check_length(errors, field, value, label, min_len, max_len):
    if value and not (min_len <= len(value.strip()) <= max_len):
        errors[field] = f"{label} must be {min_len}-{max_len} characters."


def check_name(errors, field, value, label, max_len=100):
    if check_required(errors, field, value, label):
        check_length(errors, field, value, label, 2, max_len)
        if field not in errors and not NAME_RE.match(value.strip()):
            errors[field] = f"{label} contains invalid characters."


def check_email(errors, field, value, required=True):
    if not value:
        if required:
            errors[field] = "Email is required."
        return
    if not EMAIL_RE.match(value.strip()) or len(value) > 150:
        errors[field] = MSG_EMAIL


def check_phone(errors, field, value, required=True):
    if not value:
        if required:
            errors[field] = "Phone is required."
        return
    if not PHONE_RE.match(value.strip()):
        errors[field] = MSG_PHONE


def check_password(errors, field, value):
    if not value or not PASSWORD_RE.match(value):
        errors[field] = MSG_PASSWORD


def check_choice(errors, field, value, options, label):
    if value not in options:
        errors[field] = f"Select a valid {label}."


def is_open_stage(stage):
    return stage not in ("Won", "Lost")


def stage_status(stage):
    if stage == "Won":
        return "Won"
    if stage == "Lost":
        return "Lost"
    return "Open"


def inr(amount):
    """Indian style money format, 1500000 -> Rs 15,00,000"""
    amount = int(round(amount or 0))
    s = str(abs(amount))
    if len(s) > 3:
        last3 = s[-3:]
        rest = s[:-3]
        parts = []
        while len(rest) > 2:
            parts.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            parts.insert(0, rest)
        s = ",".join(parts) + "," + last3
    return ("-" if amount < 0 else "") + "Rs " + s
