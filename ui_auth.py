"""واجهة الدخول/إنشاء حساب/تسجيل الخروج."""

import streamlit as st

import auth


def render_login_gate() -> bool:
    """يعرض شاشة الدخول/إنشاء حساب إن لم يكن المستخدم مسجَّلاً دخوله.

    يعيد ``True`` لو كان مسجَّلاً دخوله بالفعل (فيستمر التطبيق كالمعتاد)،
    و``False`` لو عرض شاشة الدخول (فيتوقف بقية التطبيق عن الظهور).
    """
    if st.session_state.get("auth_user"):
        return True

    st.title("📆 نظام جدولة الحصص والامتحانات")
    st.caption("لكل مستخدم حسابه وجدوله الخاص. سجّل الدخول أو أنشئ حساباً جديداً للمتابعة.")

    tab_login, tab_signup = st.tabs(["🔑 تسجيل الدخول", "🆕 إنشاء حساب جديد"])

    with tab_login:
        with st.form("login_form"):
            username = st.text_input("اسم المستخدم", key="login_username")
            password = st.text_input(
                "كلمة المرور", type="password", key="login_password"
            )
            submitted = st.form_submit_button(
                "دخول", use_container_width=True, type="primary"
            )
        if submitted:
            if auth.verify_login(username, password):
                st.session_state["auth_user"] = username.strip()
                st.rerun()
            else:
                st.error("اسم المستخدم أو كلمة المرور غير صحيحة.")

    with tab_signup:
        st.caption(
            "اسم المستخدم: 3 إلى 20 حرفاً/رقماً (يُسمح بـ _ و-، بدون مسافات). "
            "كلمة المرور: 6 أحرف على الأقل."
        )
        with st.form("signup_form"):
            new_username = st.text_input("اختر اسم مستخدم", key="signup_username")
            new_password = st.text_input(
                "اختر كلمة مرور", type="password", key="signup_password"
            )
            new_password_confirm = st.text_input(
                "أكّد كلمة المرور", type="password", key="signup_password_confirm"
            )
            submitted_signup = st.form_submit_button(
                "إنشاء الحساب", use_container_width=True
            )
        if submitted_signup:
            if new_password != new_password_confirm:
                st.error("كلمتا المرور غير متطابقتين.")
            else:
                ok, message = auth.create_user(new_username, new_password)
                if ok:
                    st.success("تم إنشاء الحساب بنجاح! افتح تبويب «تسجيل الدخول» وادخل به.")
                else:
                    st.error(message)

    return False


def render_logout_button() -> None:
    username = st.session_state.get("auth_user")
    if not username:
        return
    st.sidebar.write(f"👤 مسجَّل الدخول باسم: **{username}**")
    if st.sidebar.button("🚪 تسجيل الخروج"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
