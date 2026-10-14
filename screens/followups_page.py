from datetime import date, timedelta

import streamlit as st

from core.rules import FU_STATUS, FU_TYPES, to_date
from screens.common import (can_delete, confirm_delete, current_user, flash, is_sales, owner_select, pick,
                            show_errors, show_flash, table)
from services import customers, followups, leads
from services.users import assignable_users


def fu_form(key, user, old=None):
    old = old or {}
    is_new = not old
    with st.form(key):
        c1, c2 = st.columns(2)
        data = {
            "customer_id": pick("Customer", customers.options(user), key + "_c", old.get("customer_id")),
            "lead_id": pick("Lead", leads.options(user), key + "_l", old.get("lead_id")),
        }
        st.caption("Select a customer or a lead (at least one).")
        data["subject"] = st.text_input("Subject *", old.get("subject", ""), max_chars=150)
        c3, c4, c5 = st.columns(3)
        data["fu_type"] = c3.selectbox("Type *", FU_TYPES, index=FU_TYPES.index(old.get("fu_type", "Call")))
        default_date = to_date(old["fu_date"]) if old.get("fu_date") else date.today() + timedelta(days=1)
        data["fu_date"] = c4.date_input("Follow-Up Date *", default_date)
        if is_new:
            data["status"] = "Planned"
        else:
            data["status"] = c5.selectbox("Status *", FU_STATUS, index=FU_STATUS.index(old["status"]))
        data["assigned_to"] = owner_select(key + "_owner", old.get("assigned_to"))
        data["remarks"] = st.text_area("Remarks", old.get("remarks") or "", max_chars=1000)
        submitted = st.form_submit_button("Save")
    return submitted, data


def show():
    user = current_user()
    st.title("Follow-Ups")
    show_flash()

    list_tab, add_tab, edit_tab = st.tabs(["Follow-Up List", "Schedule Follow-Up", "Update / Reschedule"])

    with list_tab:
        view = st.radio("Show", ["pending", "overdue", "upcoming", "all"], horizontal=True, format_func=str.title)
        c1, c2, c3, c4 = st.columns(4)
        search = c1.text_input("Subject / customer / lead")
        on_date = c2.date_input("Date", value=None)
        status = c3.selectbox("Status", [""] + FU_STATUS, format_func=lambda x: x or "All")
        owner = None
        if not is_sales():
            users = {u["id"]: u["full_name"] for u in assignable_users()}
            owner = c4.selectbox("Assigned To", [None] + list(users), format_func=lambda x: "All" if x is None else users[x])
        table(followups.list_followups(user, view, status, owner, search, on_date), key="fu")

    with add_tab:
        submitted, data = fu_form("add_fu", user)
        if submitted:
            fid, errors = followups.create_followup(user, data)
            if errors:
                show_errors(errors)
            else:
                flash("Follow-up scheduled.")
                st.rerun()

    with edit_tab:
        rows = followups.list_followups(user, view="all")
        if not rows:
            st.info("No follow-ups yet.")
            return
        options = {r["id"]: f"{r['fu_date']} - {r['subject']} ({r['related_to']}) - {r['status']}" for r in rows}
        fid = st.selectbox("Select follow-up", list(options), format_func=lambda x: options[x])
        fu = followups.get_followup(user, fid)

        if fu["status"] == "Planned":
            st.write("Quick update:")
            b1, b2, b3, _ = st.columns([1, 1, 1, 3])
            for col, new_status in zip([b1, b2, b3], ["Completed", "Missed", "Cancelled"]):
                if col.button(f"Mark {new_status}", key=f"fu_{fid}_{new_status}"):
                    error = followups.set_status(user, fid, new_status)
                    if error:
                        st.error(error)
                    else:
                        flash(f"Follow-up marked as {new_status}.")
                        st.rerun()

        st.markdown("#### Edit / Reschedule")
        submitted, data = fu_form(f"edit_fu_{fid}", user, fu)
        if submitted:
            errors = followups.update_followup(user, fid, data)
            if errors:
                show_errors(errors)
            else:
                flash("Follow-up updated.")
                st.rerun()

        if can_delete():
            st.markdown("#### Delete Follow-Up")
            if confirm_delete("follow-up", f"del_fu_{fid}"):
                flash(followups.delete_followup(user, fid), "info")
                st.rerun()
