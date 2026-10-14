# Smart Sales & Customer Management System (Python + Streamlit)

Simple role based CRM made with **Python**, **Streamlit** (screens), **SQLite** (database) and **FastAPI** (REST API).

## How to run

```
pip install -r requirements.txt
streamlit run app.py
```

Open http://localhost:8501

The database file `smartsales.db` is created on first run with sample data. Delete the file to start fresh.

REST API (optional, separate terminal):

```
uvicorn api:app --port 8000
```

API docs: http://localhost:8000/docs

Run all tests:

```
python tests/run_tests.py
```

## Demo logins

| Role | Email | Password |
|---|---|---|
| Admin | admin@smartsales.in | Admin@123 |
| Manager | manager@smartsales.in | Manager@123 |
| Sales Executive | sales1@smartsales.in | Sales@123 |
| Sales Executive | sales2@smartsales.in | Sales@123 |

## Folders

```
app.py          start point - login check and side menu by role
api.py          REST API (FastAPI)
core/           db connection, tables, login/password, validation rules, audit log, sample data
services/       business logic for each module (all SQL is here)
screens/        Streamlit pages (only UI, they call services)
tests/          run_tests.py checks every module
```

## Modules

- Login, Register, Logout, password policy, lockout after 5 wrong tries (15 min)
- Dashboard with KPI cards, 3 charts and date filter
- Customers, Leads (workflow + convert), Opportunities (+ pipeline board), Follow-Ups, Activities
- Users & Roles (Admin), Audit Log (Admin)
- Reports with CSV download
- REST API for customers, leads, opportunities, follow-ups and pipeline

See `EXPLAIN.md` for where each requirement is done.
