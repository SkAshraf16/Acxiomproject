from datetime import date

import streamlit as st

from core.rules import ACT_STATUS, ACT_TYPES, to_date
from screens.common import (can_delete, confirm_delete, current_user, flash, is_sales, owner_select, pick,
                            show_errors, show_flash, table)
from services import activities, customers, leads
from services.users import assignable_users


def act_form(key, user, old=None):
    old = old or {}
    with st.form(key):
        c1, c2 = st.columns(2)
        data = {
            "act_type": c1.selectbox("Activity Type *", ACT_TYPES, index=ACT_TYPES.index(old.get("act_type", "Call"))),
            "subject": c2.text_input("Subject *", old.get("subject", ""), max_chars=150),
            "customer_id": pick("Customer", customers.options(user), key + "_c", old.get("customer_id")),
            "lead_id": pick("Lead", leads.options(user), key + "_l", old.get("lead_id")),
        }
        c3, c4 = st.columns(2)
        data["act_date"] = c3.date_input("Activity Date *", to_date(old["act_date"]) if old.get("act_date") else date.today())
        data["status"] = c4.selectbox("Status *", ACT_STATUS, index=ACT_STATUS.index(old.get("status", "Planned")))
        data["assigned_to"] = owner_select(key + "_owner", old.get("assigned_to"))
        data["description"] = st.text_area("Description", old.get("description") or "", max_chars=1000)
        submitted = st.form_submit_button("Save")
    return submitted, data


def show():
    user = current_user()
    st.title("Activities")
    st.caption("Calls, meetings, emails and tasks done for customers or leads.")
    show_flash()

    list_tab, add_tab, edit_tab = st.tabs(["Activity List", "Log Activity", "Edit"])

    with list_tab:
        c1, c2, c3, c4 = st.columns(4)
        act_type = c1.selectbox("Type", [""] + ACT_TYPES, format_func=lambda x: x or "All")
        on_date = c2.date_input("Date", value=None, key="act_date_filter")
        status = c3.selectbox("Status", [""] + ACT_STATUS, format_func=lambda x: x or "All")
        owner = None
        if not is_sales():
            users = {u["id"]: u["full_name"] for u in assignable_users()}
            owner = c4.selectbox("Assigned To", [None] + list(users), format_func=lambda x: "All" if x is None else users[x])
        table(activities.list_activities(user, act_type, status, owner, on_date), key="act")

    with add_tab:
        submitted, data = act_form("add_act", user)
        if submitted:
            aid, errors = activities.create_activity(user, data)
            if errors:
                show_errors(errors)
            else:
                flash(f"{data['act_type']} logged.")
                st.rerun()

    with edit_tab:
        rows = activities.list_activities(user)
        if not rows:
            st.info("No activities yet.")
            return
        options = {r["id"]: f"{r['act_date']} - {r['act_type']} - {r['subject']}" for r in rows}
        aid = st.selectbox("Select activity", list(options), format_func=lambda x: options[x])
        act = activities.get_activity(user, aid)

        submitted, data = act_form(f"edit_act_{aid}", user, act)
        if submitted:
            errors = activities.update_activity(user, aid, data)
            if errors:
                show_errors(errors)
            else:
                flash("Activity updated.")
                st.rerun()

        if can_delete():
            st.markdown("#### Delete Activity")
            if confirm_delete("activity", f"del_act_{aid}"):
                flash(activities.delete_activity(user, aid), "info")
                st.rerun()
