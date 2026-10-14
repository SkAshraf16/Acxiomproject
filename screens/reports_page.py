import streamlit as st

from core.rules import CUSTOMER_STATUS, FU_STATUS, LEAD_STATUS, STAGES, inr
from screens.common import csv_button, current_user, table
from services import reports


def date_filters(key):
    c1, c2 = st.columns(2)
    return c1.date_input("From", value=None, key=key + "_from"), c2.date_input("To", value=None, key=key + "_to")


def show():
    user = current_user()
    st.title("Reports")
    if user["role"] == "SalesExecutive":
        st.info("Reports show only your assigned records.")

    names = ["Customer", "Lead", "Follow-Up", "Opportunity", "Pipeline", "Conversion"]
    if user["role"] in ("Admin", "Manager"):
        names.append("User Activity")
    tabs = dict(zip(names, st.tabs(names)))

    with tabs["Customer"]:
        d_from, d_to = date_filters("rc")
        status = st.selectbox("Status", [""] + CUSTOMER_STATUS, format_func=lambda x: x or "All", key="rc_s")
        rows = reports.customer_report(user, d_from, d_to, status)
        table(rows, key="rc")
        csv_button(rows, "customer-report.csv", "rc_csv")

    with tabs["Lead"]:
        d_from, d_to = date_filters("rl")
        status = st.selectbox("Status", [""] + LEAD_STATUS, format_func=lambda x: x or "All", key="rl_s")
        rows = reports.lead_report(user, d_from, d_to, status)
        st.write(f"Converted: {sum(1 for r in rows if r['status'] == 'Converted')} of {len(rows)}")
        table(rows, money_cols=["expected_value"], key="rl")
        csv_button(rows, "lead-report.csv", "rl_csv")

    with tabs["Follow-Up"]:
        d_from, d_to = date_filters("rf")
        status = st.selectbox("Status", [""] + FU_STATUS, format_func=lambda x: x or "All", key="rf_s")
        rows = reports.followup_report(user, d_from, d_to, status)
        c = st.columns(4)
        c[0].metric("Planned", sum(1 for r in rows if r["status"] == "Planned"))
        c[1].metric("Completed", sum(1 for r in rows if r["status"] == "Completed"))
        c[2].metric("Missed", sum(1 for r in rows if r["status"] == "Missed"))
        c[3].metric("Overdue", sum(1 for r in rows if r["overdue"] == "Yes"))
        table(rows, key="rf")
        csv_button(rows, "followup-report.csv", "rf_csv")

    with tabs["Opportunity"]:
        st.caption("Date filter is on expected close date.")
        d_from, d_to = date_filters("ro")
        stage = st.selectbox("Stage", [""] + STAGES, format_func=lambda x: x or "All", key="ro_s")
        rows = reports.opportunity_report(user, d_from, d_to, stage)
        st.write(f"Total: {inr(sum(r['amount'] for r in rows))} | Weighted: {inr(sum(r['weighted'] for r in rows))}")
        table(rows, money_cols=["amount", "weighted"], key="ro")
        csv_button(rows, "opportunity-report.csv", "ro_csv")

    with tabs["Pipeline"]:
        st.caption("Weighted amount = Amount x Probability / 100")
        by_stage, by_owner = reports.pipeline_report(user)
        left, right = st.columns(2)
        with left:
            st.subheader("Stage wise")
            table(by_stage, money_cols=["amount", "weighted"], key="rp1")
        with right:
            st.subheader("Owner wise (open)")
            table(by_owner, money_cols=["amount", "weighted"], key="rp2")
            csv_button(by_owner, "pipeline-report.csv", "rp_csv")

    with tabs["Conversion"]:
        data = reports.conversion_report(user)
        c = st.columns(4)
        c[0].metric("Total Leads", data["total_leads"])
        c[1].metric("Converted", data["converted"], f"{data['conversion_rate']}% conversion", delta_color="off")
        c[2].metric("Won / Lost Deals", f"{data['won']} / {data['lost']}", f"{data['win_rate']}% win rate", delta_color="off")
        c[3].metric("Won Value", inr(data["won_value"]))
        st.subheader("Conversion by Lead Source")
        table(data["by_source"], key="rconv")

    if "User Activity" in tabs:
        with tabs["User Activity"]:
            d_from, d_to = date_filters("ru")
            rows = reports.user_activity_report(user, d_from, d_to)
            table(rows, key="ru")
            csv_button(rows, "user-activity.csv", "ru_csv")
