from datetime import date, timedelta

import streamlit as st

from core.rules import LEAD_SOURCES, STAGES, inr, is_open_stage, to_date
from screens.common import (can_delete, confirm_delete, current_user, flash, owner_select, pick, show_errors,
                            show_flash, table)
from services import customers, opportunities
from services.customers import history


def opp_form(key, cust_options, old=None):
    old = old or {}
    with st.form(key):
        c1, c2 = st.columns(2)
        data = {
            "name": c1.text_input("Opportunity Name *", old.get("name", ""), max_chars=150),
            "customer_id": pick("Customer *", cust_options, key + "_cust", old.get("customer_id"), allow_none=False),
        }
        c3, c4, c5 = st.columns(3)
        data["amount"] = c3.number_input("Amount (Rs) *", value=float(old.get("amount", 0)), step=1000.0)
        data["probability"] = c4.number_input("Probability % *", value=int(old.get("probability", 10)), step=5)
        data["stage"] = c5.selectbox("Stage *", STAGES, index=STAGES.index(old.get("stage", "Qualification")))
        c6, c7 = st.columns(2)
        default_close = to_date(old["close_date"]) if old.get("close_date") else date.today() + timedelta(days=30)
        data["close_date"] = c6.date_input("Expected Close Date *", default_close)
        sources = [""] + LEAD_SOURCES
        data["source"] = c7.selectbox("Source", sources, index=sources.index(old.get("source") or ""), format_func=lambda x: x or "-- Select --")
        data["assigned_to"] = owner_select(key + "_owner", old.get("assigned_to"))
        data["notes"] = st.text_area("Notes", old.get("notes") or "", max_chars=1000)
        st.caption(f"Weighted amount = Amount x Probability / 100 = {inr(opportunities.weighted(data['amount'], data['probability']))}")
        submitted = st.form_submit_button("Save")
    return submitted, data


def show():
    user = current_user()
    st.title("Opportunities")
    show_flash()
    cust_options = customers.options(user)

    list_tab, add_tab, view_tab = st.tabs(["Opportunity List", "Add Opportunity", "View / Edit"])

    with list_tab:
        c1, c2, c3 = st.columns([2, 1, 1])
        search = c1.text_input("Search opportunity or customer")
        stage = c2.selectbox("Stage", [""] + STAGES, format_func=lambda x: x or "All")
        status = c3.selectbox("Status", ["", "Open", "Won", "Lost"], format_func=lambda x: x or "All")
        table(opportunities.list_opps(user, search, stage, status), money_cols=["amount", "weighted"], key="opp")

    with add_tab:
        if not cust_options:
            st.info("Add a customer first.")
        else:
            submitted, data = opp_form("add_opp", cust_options)
            if submitted:
                oid, errors = opportunities.create_opp(user, data)
                if errors:
                    show_errors(errors)
                else:
                    flash("Opportunity created.")
                    st.rerun()

    with view_tab:
        rows = opportunities.list_opps(user)
        if not rows:
            st.info("No opportunities yet.")
            return
        options = {r["id"]: f"{r['name']} - {r['customer']} ({r['stage']})" for r in rows}
        oid = st.selectbox("Select opportunity", list(options), format_func=lambda x: options[x])
        opp = opportunities.get_opp(user, oid)

        st.subheader(f"{opp['name']} - {opp['stage']}")
        st.write(f"**Customer:** {opp['customer']} | **Amount:** {inr(opp['amount'])} | **Probability:** {opp['probability']}% | "
                 f"**Weighted:** {inr(opportunities.weighted(opp['amount'], opp['probability']))}")
        st.write(f"**Expected Close:** {opp['close_date']} | **Status:** {opp['status']}"
                 + (f" on {opp['closed_at']}" if opp["closed_at"] else ""))

        if is_open_stage(opp["stage"]):
            st.write("Move stage:")
            cols = st.columns(len(STAGES))
            for col, s in zip(cols, STAGES):
                if s != opp["stage"] and col.button(s, key=f"move_{oid}_{s}"):
                    error = opportunities.move_stage(user, oid, s)
                    if error:
                        st.error(error)
                    else:
                        flash(f"Moved to {s}.")
                        st.rerun()

        with st.expander("Change History"):
            table(history("Opportunity", oid), key="opp_hist")

        st.markdown("#### Edit Opportunity")
        submitted, data = opp_form(f"edit_opp_{oid}", cust_options, opp)
        if submitted:
            errors = opportunities.update_opp(user, oid, data)
            if errors:
                show_errors(errors)
            else:
                flash("Opportunity updated.")
                st.rerun()

        if can_delete():
            st.markdown("#### Delete Opportunity")
            if confirm_delete("opportunity", f"del_opp_{oid}"):
                flash(opportunities.delete_opp(user, oid), "info")
                st.rerun()


def pipeline():
    """Board view - one column per stage."""
    user = current_user()
    st.title("Sales Pipeline")
    show_flash()
    rows = opportunities.list_opps(user)
    next_stage = {"Qualification": "Proposal", "Proposal": "Negotiation", "Negotiation": "Won"}

    cols = st.columns(len(STAGES))
    for col, stage in zip(cols, STAGES):
        items = [r for r in rows if r["stage"] == stage]
        with col:
            st.subheader(stage)
            st.caption(f"{len(items)} | {inr(sum(r['amount'] for r in items))}")
            for r in items:
                with st.container(border=True):
                    st.write(f"**{r['name']}**")
                    st.caption(f"{r['customer']} | {r['owner'] or '-'}")
                    st.write(f"{inr(r['amount'])} | {r['probability']}%")
                    st.caption(f"Close: {r['close_date']}")
                    if stage in next_stage:
                        if st.button(f"Move to {next_stage[stage]}", key=f"pipe_{r['id']}"):
                            error = opportunities.move_stage(user, r["id"], next_stage[stage])
                            if error:
                                flash(error, "error")
                            else:
                                flash(f"Moved to {next_stage[stage]}.")
                            st.rerun()
