import streamlit as st

from core import auth
from core.seed import setup
from screens import (activities_page, audit_page, customers_page, dashboard_page, followups_page, leads_page,
                     login_page, opportunities_page, reports_page, users_page)

st.set_page_config(page_title="Smart Sales", layout="wide")
setup()

user = st.session_state.get("user")

if not user:
    login_page.show()
    st.stop()

# sidebar - who is logged in + logout
st.sidebar.write(f"**{user['full_name']}**")
st.sidebar.caption(f"{user['email']} | {user['role']}")
if st.sidebar.button("Logout"):
    auth.logout(user)
    st.session_state.clear()
    st.rerun()

# menu changes by role, pages also check role again inside services
pages = [
    st.Page(dashboard_page.show, title="Dashboard", url_path="dashboard", default=True),
    st.Page(customers_page.show, title="Customers", url_path="customers"),
    st.Page(leads_page.show, title="Leads", url_path="leads"),
    st.Page(opportunities_page.show, title="Opportunities", url_path="opportunities"),
    st.Page(opportunities_page.pipeline, title="Sales Pipeline", url_path="pipeline"),
    st.Page(followups_page.show, title="Follow-Ups", url_path="followups"),
    st.Page(activities_page.show, title="Activities", url_path="activities"),
    st.Page(reports_page.show, title="Reports", url_path="reports"),
]
admin_pages = []
if user["role"] in ("Admin", "Manager"):
    admin_pages.append(st.Page(users_page.show, title="Users & Roles", url_path="users"))
if user["role"] == "Admin":
    admin_pages.append(st.Page(audit_page.show, title="Audit Log", url_path="audit"))

nav = st.navigation({"CRM": pages, "Administration": admin_pages} if admin_pages else pages)
nav.run()
