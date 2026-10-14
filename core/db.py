import os
import sqlite3

# tests set SMARTSALES_DB to use a separate file
DB_FILE = os.environ.get("SMARTSALES_DB") or os.path.join(os.path.dirname(os.path.dirname(__file__)), "smartsales.db")


def get_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def query(sql, params=()):
    """Run a SELECT and return list of dicts."""
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def query_one(sql, params=()):
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql, params=()):
    """Run INSERT / UPDATE / DELETE and return new row id."""
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid


def create_tables():
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            phone TEXT,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('Admin', 'Manager', 'SalesExecutive')),
            is_active INTEGER NOT NULL DEFAULT 1,
            failed_count INTEGER NOT NULL DEFAULT 0,
            lockout_until TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            phone TEXT NOT NULL UNIQUE,
            company TEXT,
            address TEXT,
            city TEXT,
            state TEXT,
            status TEXT NOT NULL DEFAULT 'Active',
            notes TEXT,
            assigned_to INTEGER REFERENCES users(id),
            created_by TEXT,
            created_at TEXT NOT NULL,
            modified_at TEXT
        );

        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            company TEXT,
            source TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'New',
            priority TEXT NOT NULL DEFAULT 'Medium',
            expected_value REAL NOT NULL DEFAULT 0,
            notes TEXT,
            assigned_to INTEGER REFERENCES users(id),
            converted_customer_id INTEGER,
            converted_at TEXT,
            created_at TEXT NOT NULL,
            modified_at TEXT
        );

        CREATE TABLE IF NOT EXISTS opportunities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            customer_id INTEGER NOT NULL REFERENCES customers(id),
            lead_id INTEGER REFERENCES leads(id) ON DELETE SET NULL,
            amount REAL NOT NULL,
            stage TEXT NOT NULL,
            probability INTEGER NOT NULL,
            close_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Open',
            source TEXT,
            notes TEXT,
            assigned_to INTEGER REFERENCES users(id),
            created_at TEXT NOT NULL,
            modified_at TEXT,
            closed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS followups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER REFERENCES customers(id) ON DELETE CASCADE,
            lead_id INTEGER REFERENCES leads(id) ON DELETE CASCADE,
            fu_date TEXT NOT NULL,
            fu_type TEXT NOT NULL,
            subject TEXT NOT NULL,
            remarks TEXT,
            status TEXT NOT NULL DEFAULT 'Planned',
            assigned_to INTEGER REFERENCES users(id),
            created_at TEXT NOT NULL,
            completed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            act_type TEXT NOT NULL,
            subject TEXT NOT NULL,
            description TEXT,
            act_date TEXT NOT NULL,
            customer_id INTEGER REFERENCES customers(id) ON DELETE CASCADE,
            lead_id INTEGER REFERENCES leads(id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'Planned',
            assigned_to INTEGER REFERENCES users(id),
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            user_email TEXT,
            action TEXT NOT NULL,
            entity TEXT NOT NULL,
            record_id TEXT,
            old_value TEXT,
            new_value TEXT,
            result TEXT NOT NULL DEFAULT 'Success',
            created_at TEXT NOT NULL
        );
        """)
