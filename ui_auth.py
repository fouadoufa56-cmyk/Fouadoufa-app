"""واجهة الدخول/إنشاء حساب/تسجيل الخروج، مع إبقاء الدخول بعد تحديث الصفحة."""

import streamlit as st
import streamlit.components.v1 as components

import auth
import storage
from constants import SESSION_COOKIE, SESSION_DAYS


STORAGE_DOWN = "⚠️ تعذّر الوصول إلى مكان تخزين البيانات الآن. حاول مرة أخرى بعد قليل."


def _read_cookie() -> str | None:
    """يقرأ كوكي الجلسة من المتصفح (يتطلب Streamlit 1.37+، وإلا لا يُستعاد الدخول)."""
    context = getattr(st, "context", None)
    cookies = getattr(context, "cookies", None)
    if cookies is None:
        return None
    try:
        return cookies.get(SESSION_COOKIE)
    except Exception:
        return None


def _run_cookie_script(js_body: str) -> None:
    # يُنفَّذ داخل إطار صغير بلا ارتفاع، ويكتب الكوكي في صفحة التطبيق نفسها
    components.html(
        "<script>(function(){try{"
        "var secure = window.parent.location.protocol==='https:' ? '; Secure' : '';"
        f"{js_body}"
        "}catch(e){}})();</script>",
        height=0,
    )


def _set_cookie(token: str) -> None:
    max_age = SESSION_DAYS * 86400
    _run_cookie_script(
        f"window.parent.document.cookie = '{SESSION_COOKIE}={token}; path=/; "
        f"max-age={max_age}; SameSite=Lax' + secure;"
    )


def _clear_cookie() -> None:
    _run_cookie_script(
        f"window.parent.document.cookie = '{SESSION_COOKIE}=; path=/; max-age=0; "
        "SameSite=Lax' + secure;"
    )


def render_session_cookie() -> None:
    """يجدّد كوكي الدخول كل تشغيل (يُستدعى بعد نجاح الدخول)."""
    token = st.session_state.get("auth_token")
    if token:
        with st.sidebar:
            _set_cookie(token)


def render_login_gate() -> bool:
    """يعرض شاشة الدخول/إنشاء حساب إن لم يكن المستخدم مسجَّلاً دخوله.

    يعيد ``True`` لو كان مسجَّلاً دخوله (أو استُعيد دخوله من الكوكي بعد تحديث
    الصفحة)، و``False`` لو عرض شاشة الدخول (فيتوقف بقية التطبيق).
    """
    if st.session_state.get("auth_user"):
        return True

    # بعد تحديث الصفحة تضيع حالة الجلسة؛ نستعيد الدخول من الكوكي لو كان صالحاً
    cookie_token = _read_cookie()
    try:
        restored_user = auth.validate_session(cookie_token)
    except storage.StorageError:
        restored_user = None
        st.error(STORAGE_DOWN)
    if restored_user:
        st.session_state["auth_user"] = restored_user
        st.session_state["auth_token"] = cookie_token
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
            try:
                if auth.verify_login(username, password):
                    st.session_state["auth_token"] = auth.create_session(username.strip())
                    st.session_state["auth_user"] = username.strip()
                    st.rerun()
                else:
                    st.error("اسم المستخدم أو كلمة المرور غير صحيحة.")
            except storage.StorageError:
                st.error(STORAGE_DOWN)

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
                try:
                    ok, message = auth.create_user(new_username, new_password)
                except storage.StorageError:
                    ok, message = False, STORAGE_DOWN
                if ok:
                    st.success("تم إنشاء الحساب بنجاح! افتح تبويب «تسجيل الدخول» وادخل به.")
                else:
                    st.error(message)

    # لا أحد مسجَّل هنا: نمسح أي كوكي قديم أو منتهٍ
    _clear_cookie()
    return False


def render_logout_button() -> None:
    username = st.session_state.get("auth_user")
    if not username:
        return
    st.sidebar.write(f"👤 مسجَّل الدخول باسم: **{username}**")
    if st.sidebar.button("🚪 تسجيل الخروج"):
        try:
            auth.delete_session(st.session_state.get("auth_token"))
        except storage.StorageError:
            pass  # الخروج يتم محلياً حتى لو تعذّر حذف الرمز من التخزين
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
