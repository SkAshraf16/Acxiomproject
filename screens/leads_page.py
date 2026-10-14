import streamlit as st

from core.rules import LEAD_PRIORITY, LEAD_SOURCES, LEAD_STATUS
from screens.common import (can_delete, confirm_delete, current_user, flash, is_sales, owner_select, show_errors,
                            show_flash, table)
from services import leads
from services.customers import history
from services.users import assignable_users


def lead_form(key, statuses, old=None):
    old = old or {}
    with st.form(key):
        c1, c2 = st.columns(2)
        data = {
            "name": c1.text_input("Lead Name *", old.get("name", ""), max_chars=100),
            "company": c2.text_input("Company Name", old.get("company") or "", max_chars=150),
            "email": c1.text_input("Email", old.get("email") or ""),
            "phone": c2.text_input("Phone", old.get("phone") or "", max_chars=10),
        }
        c3, c4, c5 = st.columns(3)
        data["source"] = c3.selectbox("Source *", LEAD_SOURCES, index=LEAD_SOURCES.index(old.get("source", "Website")))
        current = old.get("status", statuses[0])
        data["status"] = c4.selectbox("Status *", statuses, index=statuses.index(current), help="Only allowed next statuses are shown")
        data["priority"] = c5.selectbox("Priority *", LEAD_PRIORITY, index=LEAD_PRIORITY.index(old.get("priority", "Medium")))
        data["expected_value"] = st.number_input("Expected Value (Rs) *", min_value=0.0, max_value=100000000.0,
                                                 value=float(old.get("expected_value", 0)), step=1000.0)
        data["assigned_to"] = owner_select(key + "_owner", old.get("assigned_to"))
        data["notes"] = st.text_area("Notes", old.get("notes") or "", max_chars=1000)
        submitted = st.form_submit_button("Save")
    return submitted, data


def show():
    user = current_user()
    st.title("Leads")
    show_flash()

    list_tab, add_tab, view_tab = st.tabs(["Lead List", "Add Lead", "View / Edit / Convert"])

    with list_tab:
        c1, c2, c3 = st.columns([2, 1, 1])
        search = c1.text_input("Search name, company, email or code")
        status = c2.selectbox("Status", [""] + LEAD_STATUS, format_func=lambda x: x or "All")
        owner = None
        if not is_sales():
            users = {u["id"]: u["full_name"] for u in assignable_users()}
            owner = c3.selectbox("Assigned To", [None] + list(users), format_func=lambda x: "All" if x is None else users[x])
        table(leads.list_leads(user, search, status, owner), money_cols=["expected_value"], key="lead")

    with add_tab:
        submitted, data = lead_form("add_lead", ["New", "Contacted"])
        if submitted:
            lid, errors = leads.create_lead(user, data)
            if errors:
                show_errors(errors)
            else:
                flash(f"Lead {data['name']} created.")
                st.rerun()

    with view_tab:
        rows = leads.list_leads(user)
        if not rows:
            st.info("No leads yet.")
            return
        options = {r["id"]: f"{r['name']} ({r['code']}) - {r['status']}" for r in rows}
        lid = st.selectbox("Select lead", list(options), format_func=lambda x: options[x])
        lead = leads.get_lead(user, lid)

        st.subheader(f"{lead['name']} ({lead['code']}) - {lead['status']}")
        st.write(f"**Email:** {lead['email'] or '-'} | **Phone:** {lead['phone'] or '-'} | **Company:** {lead['company'] or '-'}")
        st.write(f"**Source:** {lead['source']} | **Priority:** {lead['priority']} | **Expected Value:** Rs {lead['expected_value']:,.0f}")

        if lead["status"] == "Converted":
            st.success(f"Converted on {lead['converted_at']} (customer id {lead['converted_customer_id']}).")
        elif lead["status"] == "Qualified":
            if st.button("Convert to Customer + Opportunity"):
                oid, error = leads.convert_lead(user, lid)
                if error:
                    st.error(error)
                else:
                    flash(f"Lead converted. New opportunity id {oid} created.")
                    st.rerun()
        else:
            st.info("Workflow: New -> Contacted -> Qualified -> Convert. Mark the lead as Qualified to convert it.")

        rel = leads.related(lid)
        with st.expander(f"Follow-Ups ({len(rel['followups'])})"):
            table(rel["followups"], key="lead_fu")
        with st.expander(f"Activities ({len(rel['activities'])})"):
            table(rel["activities"], key="lead_act")
        with st.expander("Change History"):
            table(history("Lead", lid), key="lead_hist")

        if lead["status"] != "Converted":
            st.markdown("#### Edit Lead")
            submitted, data = lead_form(f"edit_lead_{lid}", leads.next_statuses(lead["status"]), lead)
            if submitted:
                errors = leads.update_lead(user, lid, data)
                if errors:
                    show_errors(errors)
                else:
                    flash("Lead updated.")
                    st.rerun()

        if can_delete():
            st.markdown("#### Delete Lead")
            if confirm_delete("lead", f"del_lead_{lid}"):
                flash(leads.delete_lead(user, lid), "info")
                st.rerun()
