import streamlit as st

from screens.common import csv_button, current_user, table
from services import reports


def show():
    """Read only - there is no edit or delete for audit rows anywhere in the app."""
    user = current_user()
    st.title("Audit Log")

    entities, actions = reports.audit_filters()
    c1, c2, c3, c4, c5 = st.columns(5)
    email = c1.text_input("User email")
    entity = c2.selectbox("Module", [""] + entities, format_func=lambda x: x or "All")
    action = c3.selectbox("Action", [""] + actions, format_func=lambda x: x or "All")
    d_from = c4.date_input("From", value=None)
    d_to = c5.date_input("To", value=None)

    rows = reports.audit_report(user, email, entity, action, d_from, d_to)
    table([{k: r[k] for k in ("id", "created_at", "user_email", "action", "entity", "record_id", "result")} for r in rows],
          page_size=20, key="audit")
    csv_button(rows, "audit-log.csv", "audit_csv")

    if rows:
        st.markdown("#### Entry details")
        ids = [r["id"] for r in rows]
        pick = st.selectbox("Select entry id", ids)
        row = next(r for r in rows if r["id"] == pick)
        st.write(f"**{row['action']}** on **{row['entity']}** #{row['record_id']} by {row['user_email'] or 'system'} at {row['created_at']}")
        st.write("Old value:")
        st.code(row["old_value"] or "-")
        st.write("New value:")
        st.code(row["new_value"] or "-")
