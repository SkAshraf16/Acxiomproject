# Viva Guide (Python version)

## 1. How the app works (say this first)

```
Browser  ->  screens/ (Streamlit UI)  ->  services/ (rules + SQL)  ->  core/db.py  ->  smartsales.db (SQLite)
                                              |
                                              +-> core/audit.py writes audit_log for every change
api.py (FastAPI) also calls the same services/, so rules are written only once.
```

- **app.py** – sets up the database, shows login if nobody is logged in, then builds the side menu based on the role.
- **screens/** – only UI: forms, tables and buttons. No SQL here.
- **services/** – one file per module. Validation, permission checks and SQL queries are here.
- **core/** – shared things: `db.py` (connection + tables), `auth.py` (password hash, login, lockout, role helpers), `rules.py` (validation functions and fixed lists), `audit.py`, `seed.py` (sample data).

## 2. Requirement → where in code

| Requirement | File / function | How to explain |
|---|---|---|
| Password never plain text | `core/auth.py` `hash_password` | PBKDF2-SHA256 with a random salt, 120000 rounds. Only `salt$hash` is saved. |
| Password policy | `core/rules.py` `PASSWORD_RE` | Min 8 chars with upper, lower, number and special character. |
| Lockout | `core/auth.py` `login` | 5 wrong tries → `lockout_until` = now + 15 min. Admin can unlock (`services/users.py unlock`). |
| Login / Register / Logout | `core/auth.py`, `screens/login_page.py` | Register always gives the SalesExecutive role. |
| Pages need login | `app.py` | If `session_state["user"]` is empty, only the login page is shown (`st.stop()`). |
| Role based menu | `app.py` | The Users and Audit pages are added only for Admin/Manager. |
| Server side permission | `core/auth.py` `require_role`, used in services | Delete, user admin and audit call `require_role`, so they are blocked even if someone calls the function directly or through the API. |
| Sales sees only own data | `core/auth.py` `scope` | Adds `AND assigned_to = ?` for SalesExecutive in every query (lists, details, edit, reports, API). |
| SQL injection | all services | Always `?` placeholders, never string joining of user input. |
| Validation | `core/rules.py` + `validate()` in each service | Required, email, phone, length, date and number checks. Errors are shown next to the form with `st.error`. |
| Amount > 0, probability 0-100, close date not in past | `services/opportunities.py` `validate` | Same messages as in the PDF. The close date rule is skipped for Won/Lost. |
| Follow-up date not before today | `services/followups.py` `validate` | |
| No duplicate customer | `services/customers.py` `validate` + UNIQUE in table | Same email or phone is blocked. The API returns 409. |
| Lead workflow | `core/rules.py` `LEAD_FLOW`, `services/leads.py update_lead` | New→Contacted→Qualified etc. Converted is reachable only through the Convert button. |
| Lead conversion | `services/leads.py` `convert_lead` | One transaction: customer + opportunity + lead marked Converted, with rollback on error. |
| Weighted pipeline | `services/opportunities.py` `weighted` | amount × probability / 100 |
| Audit log | `core/audit.py` `log`, `changes` | Saves user, action, entity, record id, old and new value (only the changed fields) and time. No edit/delete screen. |
| Dashboard + charts | `services/reports.py dashboard`, `screens/dashboard_page.py` | Counts come from scoped queries, so each role sees its own numbers. |
| Search / filter / paging | list functions in services, `screens/common.py table` | |
| Reports + CSV | `services/reports.py`, `screens/reports_page.py` | `st.download_button` with pandas `to_csv`. |
| REST API | `api.py` | Token login, Bearer header, returns 200/201/204/400/401/403/404/409/429. No password fields are returned. |

## 3. Things that work differently from the .NET version

- **Anti-forgery token:** Streamlit does not use HTML form posts. It talks to the server over its own websocket session, so a CSRF token is not needed. The API uses a Bearer token in the header (not a cookie), so CSRF does not apply there either.
- **Client side validation:** Streamlit runs everything on the server. Widgets like `max_chars`, `number_input` and `date_input` limit input in the browser, and the full checks run in the services before saving.
- **Charts:** built-in Streamlit charts are used instead of Chart.js.
- **Refreshing the page logs you out:** the login is kept in the Streamlit session, and a refresh starts a new session.

## 4. Demo steps

1. `streamlit run app.py` → the login page opens.
2. Log in as admin@smartsales.in / Admin@123 → Dashboard.
3. Customers → Add with email `abc` and phone `123` → error messages appear and nothing is saved.
4. Opportunities → Add with Amount 0, Probability 101 and a past date → three errors.
5. Follow-Ups → schedule with yesterday's date → error.
6. Leads → pick a lead → change status New → Qualified → error (must go through Contacted).
7. Mark a lead Qualified → Convert → a new customer and opportunity are created.
8. Log out → log in as sales1 → only own records; no Users or Audit menu.
9. Log in as manager → Users is read only; no Audit Log.
10. Admin → Audit Log → see Login, Create, Update, Convert and other rows with old/new values.
11. `uvicorn api:app` → open /docs → login → try /api/customers.

## 5. Likely questions

- **Why are services separate from screens?** The API and the UI use the same rules. If a rule changes, only one place needs editing.
- **How is the password checked?** The saved salt is read, the hash is made again from the typed password, and the two are compared with `hmac.compare_digest`.
- **What stops a sales user from opening another person's record?** `scope()` adds the owner filter to the query, so the row is never found ("not found").
- **Why plain sqlite3 and not an ORM?** It's simple to read and explain, and every query is visible.
- **How do you test?** `python tests/run_tests.py` checks 139 things: login, lockout, all rules, all modules, API status codes, and that every page opens for every role.
