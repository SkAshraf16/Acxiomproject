from datetime import date

import pandas as pd
import streamlit as st

from core.rules import inr
from screens.common import current_user, table
from services import reports


def show():
    user = current_user()
    st.title("Dashboard")

    col1, col2, col3 = st.columns([2, 1, 1])
    choice = col1.radio("Period", ["All Time", "Today", "This Week", "This Month", "Custom"], horizontal=True)
    start = end = None
    if choice == "Custom":
        start = col2.date_input("From", date.today().replace(day=1))
        end = col3.date_input("To", date.today())
    d_from, d_to = reports.date_range(choice, start, end)

    stats, lead_chart, pipe_chart, months, upcoming = reports.dashboard(user, d_from, d_to)

    # count cards 4 per row, money cards 2 per row so big amounts fit
    counts = [(k, v) for k, v in stats.items() if "Pipeline" not in k]
    money = [(k, v) for k, v in stats.items() if "Pipeline" in k]
    for i in range(0, len(counts), 4):
        cols = st.columns(4)
        for col, (label, value) in zip(cols, counts[i:i + 4]):
            col.metric(label, value)
    cols = st.columns(2)
    for col, (label, value) in zip(cols, money):
        col.metric(label, inr(value))

    if user["role"] == "Admin":
        a = reports.admin_stats()
        st.info(f"Admin view: {a['users']} users, {a['failed_today']} failed login attempt(s) today.")

    st.divider()
    c1, c2, c3 = st.columns(3)
    with c1:
        st.subheader("Lead Status")
        st.bar_chart(pd.Series(lead_chart, name="Leads"), sort=False)
    with c2:
        st.subheader("Opportunity Pipeline (Rs)")
        st.bar_chart(pd.Series(pipe_chart, name="Amount"), sort=False)
    with c3:
        st.subheader("Monthly Sales - Won (Rs)")
        st.line_chart(pd.Series(months, name="Won"))

    st.divider()
    left, right = st.columns(2)
    with left:
        st.subheader("Upcoming Follow-Ups")
        table(upcoming, key="dash_fu")
    if user["role"] == "Admin":
        with right:
            st.subheader("Recent Activity (Audit)")
            table(reports.admin_stats()["recent"], key="dash_audit")
