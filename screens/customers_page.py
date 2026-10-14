import streamlit as st

from core.rules import CUSTOMER_STATUS
from screens.common import (can_delete, confirm_delete, current_user, flash, owner_select, show_errors, show_flash,
                            table)
from services import customers


def customer_form(key, old=None):
    """Same form for add and edit. Returns (submitted, data)."""
    old = old or {}
    with st.form(key):
        c1, c2 = st.columns(2)
        data = {
            "name": c1.text_input("Customer Name *", old.get("name", ""), max_chars=100),
            "company": c2.text_input("Company Name", old.get("company") or "", max_chars=150),
            "email": c1.text_input("Email *", old.get("email", "")),
            "phone": c2.text_input("Phone *", old.get("phone", ""), max_chars=10, help="10 digit mobile number"),
            "address": st.text_input("Address", old.get("address") or "", max_chars=250),
        }
        c3, c4, c5 = st.columns(3)
        data["city"] = c3.text_input("City", old.get("city") or "", max_chars=60)
        data["state"] = c4.text_input("State", old.get("state") or "", max_chars=60)
        data["status"] = c5.selectbox("Status *", CUSTOMER_STATUS, index=CUSTOMER_STATUS.index(old.get("status", "Active")))
        data["assigned_to"] = owner_select(key + "_owner", old.get("assigned_to"))
        data["notes"] = st.text_area("Notes", old.get("notes") or "", max_chars=1000)
        submitted = st.form_submit_button("Save")
    return submitted, data


def show():
    user = current_user()
    st.title("Customers")
    show_flash()

    list_tab, add_tab, view_tab = st.tabs(["Customer List", "Add Customer", "View / Edit"])

    with list_tab:
        c1, c2 = st.columns([3, 1])
        search = c1.text_input("Search name, email, phone, company or code")
        status = c2.selectbox("Status", [""] + CUSTOMER_STATUS, format_func=lambda x: x or "All")
        table(customers.list_customers(user, search, status), key="cust")

    with add_tab:
        submitted, data = customer_form("add_customer")
        if submitted:
            cid, errors = customers.create_customer(user, data)
            if errors:
                show_errors(errors)
            else:
                flash(f"Customer {data['name']} created.")
                st.rerun()

    with view_tab:
        options = customers.options(user)
        if not options:
            st.info("No customers yet.")
            return
        cid = st.selectbox("Select customer", list(options.keys()), format_func=lambda x: options[x])
        cust = customers.get_customer(user, cid)

        st.subheader(f"{cust['name']} ({cust['code']}) - {cust['status']}")
        st.write(f"**Email:** {cust['email']} | **Phone:** {cust['phone']} | **Company:** {cust['company'] or '-'}")
        st.write(f"**Address:** {cust['address'] or '-'}, {cust['city'] or ''} {cust['state'] or ''}")
        st.write(f"**Created:** {cust['created_at']} by {cust['created_by']} | **Modified:** {cust['modified_at'] or '-'}")

        rel = customers.related(cid)
        with st.expander(f"Opportunities ({len(rel['opportunities'])})"):
            table(rel["opportunities"], money_cols=["amount"], key="cust_opp")
        with st.expander(f"Follow-Ups ({len(rel['followups'])})"):
            table(rel["followups"], key="cust_fu")
        with st.expander(f"Activities ({len(rel['activities'])})"):
            table(rel["activities"], key="cust_act")
        with st.expander("Change History"):
            table(customers.history("Customer", cid), key="cust_hist")

        st.markdown("#### Edit Customer")
        submitted, data = customer_form(f"edit_customer_{cid}", cust)
        if submitted:
            errors = customers.update_customer(user, cid, data)
            if errors:
                show_errors(errors)
            else:
                flash("Customer updated.")
                st.rerun()

        if can_delete():
            st.markdown("#### Delete Customer")
            if confirm_delete("customer", f"del_cust_{cid}"):
                flash(customers.delete_customer(user, cid), "info")
                st.rerun()
