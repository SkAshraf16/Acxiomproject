import streamlit as st

from core import auth
from screens.common import show_errors


def show():
    st.title("Smart Sales")
    st.write("Sales & Customer Management System")

    login_tab, register_tab = st.tabs(["Login", "Register"])

    with login_tab:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login")
        if submitted:
            if not email or not password:
                st.error("Email and Password are required.")
            else:
                user, error = auth.login(email, password)
                if error:
                    st.error(error)
                else:
                    st.session_state["user"] = user
                    st.rerun()

    with register_tab:
        st.caption("New users get the Sales Executive role. Admin can change it later.")
        with st.form("register_form"):
            name = st.text_input("Full Name")
            email = st.text_input("Email", key="reg_email")
            phone = st.text_input("Phone (10 digit mobile)", max_chars=10)
            password = st.text_input("Password", type="password", key="reg_pwd",
                                     help="Min 8 characters with upper case, lower case, number and special character")
            confirm = st.text_input("Confirm Password", type="password")
            submitted = st.form_submit_button("Register")
        if submitted:
            user, errors = auth.register(name, email, phone, password, confirm)
            if errors:
                show_errors(errors)
            else:
                st.session_state["user"] = user
                st.rerun()

    with st.expander("Demo logins"):
        st.write("Admin: admin@smartsales.in / Admin@123")
        st.write("Manager: manager@smartsales.in / Manager@123")
        st.write("Sales Executive: sales1@smartsales.in / Sales@123")
