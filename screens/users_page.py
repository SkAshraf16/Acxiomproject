import pandas as pd
import streamlit as st

from core.rules import ROLES
from screens.common import current_user, flash, show_errors, show_flash, table
from services import users

PERMISSIONS = [
    ("Dashboard", "Full", "Team", "Own / Assigned"),
    ("Customers", "Full", "Team", "Own / Assigned"),
    ("Leads", "Full", "Team", "Own / Assigned"),
    ("Opportunities", "Full", "Team", "Own / Assigned"),
    ("Follow-Ups", "Full", "Team", "Own / Assigned"),
    ("Activities", "Full", "Team", "Own / Assigned"),
    ("Delete records", "Yes", "Yes", "No"),
    ("User Management", "Full", "View only", "No"),
    ("Role Management", "Full", "View only", "No"),
    ("Audit Log", "Full", "No", "No"),
    ("REST API", "Authorized endpoints", "Authorized endpoints", "Own data only"),
    ("Reports", "All", "Management / Team", "Own / Assigned"),
]

ROLE_INFO = {
    "Admin": "Full administration - users, roles, audit logs, all CRM records and reports.",
    "Manager": "Manages team customers, leads, opportunities, follow-ups and reports. No security administration.",
    "SalesExecutive": "Manages only assigned customers, leads, opportunities, follow-ups and activities.",
}


def show():
    user = current_user()
    is_admin = user["role"] == "Admin"
    st.title("Users & Roles")
    show_flash()
    if not is_admin:
        st.info("Manager view: read only. Only Admin can change users and roles.")

    tabs = st.tabs(["Users", "Add User", "Edit User", "Roles", "Permissions"] if is_admin else ["Users", "Roles", "Permissions"])
    users_tab, roles_tab, perm_tab = tabs[0], tabs[-2], tabs[-1]

    with users_tab:
        c1, c2 = st.columns([3, 1])
        search = c1.text_input("Search name or email")
        role = c2.selectbox("Role", [""] + ROLES, format_func=lambda x: x or "All")
        rows = users.list_users(user, search, role)
        for r in rows:
            r["status"] = "Active" if r["is_active"] else "Inactive"
            r["lockout"] = "Locked" if r["locked"] else ""
        table([{k: r[k] for k in ("full_name", "email", "phone", "role", "status", "lockout", "failed_count", "created_at")} for r in rows],
              key="users")

    if is_admin:
        add_tab, edit_tab = tabs[1], tabs[2]
        with add_tab:
            with st.form("add_user"):
                c1, c2 = st.columns(2)
                data = {
                    "full_name": c1.text_input("Full Name *"),
                    "email": c2.text_input("Email *"),
                    "phone": c1.text_input("Phone", max_chars=10),
                    "role": c2.selectbox("Role *", ROLES, index=2),
                    "password": c1.text_input("Password *", type="password"),
                    "is_active": c2.checkbox("Active", value=True),
                }
                submitted = st.form_submit_button("Create User")
            if submitted:
                uid, errors = users.create_user(user, data)
                if errors:
                    show_errors(errors)
                else:
                    flash(f"User {data['email']} created.")
                    st.rerun()

        with edit_tab:
            all_users = users.list_users(user)
            options = {u["id"]: f"{u['full_name']} ({u['email']})" for u in all_users}
            uid = st.selectbox("Select user", list(options), format_func=lambda x: options[x])
            row = next(u for u in all_users if u["id"] == uid)
            st.write(f"Status: **{'Active' if row['is_active'] else 'Inactive'}**"
                     + (" | **Locked**" if row["locked"] else "") + f" | Failed attempts: {row['failed_count']}")

            with st.form(f"edit_user_{uid}"):
                c1, c2 = st.columns(2)
                data = {
                    "full_name": c1.text_input("Full Name *", row["full_name"]),
                    "email": c2.text_input("Email *", row["email"]),
                    "phone": c1.text_input("Phone", row["phone"] or "", max_chars=10),
                    "role": c2.selectbox("Role *", ROLES, index=ROLES.index(row["role"])),
                    "is_active": st.checkbox("Active", value=bool(row["is_active"])),
                }
                submitted = st.form_submit_button("Save Changes")
            if submitted:
                errors = users.update_user(user, uid, data)
                if errors:
                    show_errors(errors)
                else:
                    flash("User updated.")
                    st.rerun()

            b1, b2, _ = st.columns([1, 1, 3])
            if b1.button("Deactivate" if row["is_active"] else "Activate", key=f"toggle_{uid}"):
                error = users.toggle_active(user, uid)
                if error:
                    st.error(error)
                else:
                    flash("User status changed.")
                    st.rerun()
            if row["locked"] and b2.button("Unlock", key=f"unlock_{uid}"):
                users.unlock(user, uid)
                flash("User unlocked.")
                st.rerun()

            with st.form(f"reset_{uid}"):
                new_pwd = st.text_input("New Password", type="password")
                if st.form_submit_button("Reset Password"):
                    errors = users.reset_password(user, uid, new_pwd)
                    if errors:
                        show_errors(errors)
                    else:
                        flash("Password reset.")
                        st.rerun()

    with roles_tab:
        for r in users.role_counts():
            with st.container(border=True):
                st.write(f"**{r['role']}** - {r['users']} user(s)")
                st.caption(ROLE_INFO.get(r["role"], ""))
        st.caption("Each user has exactly one role. Admin changes roles from Edit User.")

    with perm_tab:
        st.dataframe(pd.DataFrame(PERMISSIONS, columns=["Module", "Admin", "Manager", "Sales Executive"]),
                     width="stretch", hide_index=True)
        st.caption("These rules are checked in the services (server side), not only by hiding menu items.")
