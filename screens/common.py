import pandas as pd
import streamlit as st

from core.rules import inr
from services.users import assignable_users


def current_user():
    return st.session_state.get("user")


def is_sales():
    return current_user()["role"] == "SalesExecutive"


def can_delete():
    return current_user()["role"] in ("Admin", "Manager")


def flash(message, kind="success"):
    """Keep a message for the next run (after st.rerun)."""
    st.session_state["flash"] = (kind, message)


def show_flash():
    if "flash" in st.session_state:
        kind, message = st.session_state.pop("flash")
        getattr(st, kind)(message)


def show_errors(errors):
    for message in errors.values():
        st.error(message)


def table(rows, money_cols=(), page_size=10, key="tbl"):
    """Show rows as a table with simple page numbers."""
    if not rows:
        st.info("No records found.")
        return
    df = pd.DataFrame(rows)
    for col in money_cols:
        if col in df.columns:
            df[col] = df[col].apply(inr)
    pages = max(1, (len(df) + page_size - 1) // page_size)
    page = 1
    if pages > 1:
        page = st.number_input(f"Page (1-{pages})", 1, pages, 1, key=key + "_page")
    start = (page - 1) * page_size
    st.dataframe(df.iloc[start:start + page_size], width="stretch", hide_index=True)
    st.caption(f"Total records: {len(df)}")


def csv_button(rows, file_name, key):
    if rows:
        data = pd.DataFrame(rows).to_csv(index=False).encode("utf-8")
        st.download_button("Download CSV", data, file_name=file_name, mime="text/csv", key=key)


def owner_select(key, current=None):
    """'Assigned To' dropdown. Hidden for Sales Executive (always self)."""
    if is_sales():
        return None
    users = assignable_users()
    options = [None] + [u["id"] for u in users]
    labels = {u["id"]: u["full_name"] for u in users}
    index = options.index(current) if current in options else 0
    return st.selectbox("Assigned To", options, index=index, key=key,
                        format_func=lambda x: "-- Myself --" if x is None else labels[x])


def pick(label, options, key, current=None, allow_none=True):
    """Dropdown from a {id: label} dict."""
    ids = ([None] if allow_none else []) + list(options.keys())
    index = ids.index(current) if current in ids else 0
    return st.selectbox(label, ids, index=index, key=key, format_func=lambda x: "-- None --" if x is None else options[x])


def confirm_delete(label, key):
    """Two step delete: tick the box, then press the button."""
    sure = st.checkbox(f"Yes, I want to delete this {label}", key=key + "_sure")
    return st.button(f"Delete {label}", key=key, disabled=not sure)
