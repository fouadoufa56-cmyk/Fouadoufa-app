"""
نسخة احتياطية داخل متصفحك (localStorage) بجانب التخزين الأساسي:

1) **نسخة بياناتك (الجداول)**: تُكتب عند كل حفظ، وعند فتح حسابك يُفتح الأحدث بين
   السيرفر والمتصفح (راجع ``persistence.load_saved_data``).
2) **سجل الحسابات**: اسم المستخدم + بصمة كلمة المرور المشفّرة لكل حساب دخلت به من
   هذا المتصفح. لو انمسح السيرفر (فاختفى الحساب)، يُعاد إنشاؤه تلقائياً من هذا
   السجل عند تسجيل الدخول بنفس كلمة المرور (راجع ``auth.restore_account``).

حدود: كل شيء مربوط بهذا المتصفح وهذا الجهاز، وينمسح لو مسحت بيانات المتصفح أو
استعملت التصفح الخفي. القراءة من المتصفح غير فورية.

ملاحظة: كود الصفحة الصغيرة (HTML) المطلوبة للمكوّن مكتوب داخل هذا الملف
(``_FRONTEND_HTML``) ويُنشأ تلقائياً عند أول تشغيل، فلا تحتاج رفع أي مجلد
إضافي. ولو فشل إنشاؤه لأي سبب، يستمر التطبيق بدون نسخة المتصفح ولا ينهار.
"""

import json
import tempfile
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from applog import logger

_FRONTEND_HTML = r'''<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body>
<script>
// مكوّن Streamlit صغير: يقرأ/يكتب نسخة البيانات في localStorage بمتصفح المستخدم.
// بروتوكول المكوّنات: رسائل postMessage بين هذا الإطار وصفحة Streamlit.
function send(type, data) {
  window.parent.postMessage(Object.assign({ isStreamlitMessage: true, type: type }, data || {}), "*");
}
var sentGet = false;
window.addEventListener("message", function (event) {
  var msg = event.data || {};
  if (msg.type !== "streamlit:render") return;
  var args = msg.args || {};
  if (args.action === "get") {
    if (sentGet) return;              // نرسل النتيجة مرة واحدة فقط
    sentGet = true;
    var value = null, ok = true;
    try { value = window.localStorage.getItem(args.store_key); } catch (e) { ok = false; }
    send("streamlit:setComponentValue", { value: { ok: ok, value: value }, dataType: "json" });
  } else if (args.action === "set" && typeof args.value === "string") {
    try {
      if (window.localStorage.getItem(args.store_key) !== args.value) {
        window.localStorage.setItem(args.store_key, args.value);
      }
    } catch (e) { /* التخزين ممتلئ أو ممنوع: نتجاهل، والسيرفر يبقى النسخة الأساسية */ }
  }
});
send("streamlit:componentReady", { apiVersion: 1 });
send("streamlit:setFrameHeight", { height: 0 });
</script>
</body>
</html>
'''

_ACCOUNTS_KEY = "tt_accounts_v1"


def _ensure_frontend_dir() -> Path:
    """ينشئ مجلد المكوّن (بجانب الكود، أو بمجلد مؤقت لو لم يكن قابلاً للكتابة)."""
    for base in (Path(__file__).resolve().parent, Path(tempfile.gettempdir())):
        folder = base / "browser_store_frontend"
        try:
            folder.mkdir(parents=True, exist_ok=True)
            index = folder / "index.html"
            if not index.exists() or index.read_text(encoding="utf-8") != _FRONTEND_HTML:
                index.write_text(_FRONTEND_HTML, encoding="utf-8")
            return folder
        except Exception:
            logger.warning("تعذّر إنشاء مجلد المكوّن في %s.", base)
    raise RuntimeError("لا يوجد مكان قابل للكتابة لإنشاء مجلد المكوّن")


def _declare():
    try:
        return components.declare_component(
            "tt_browser_store", path=str(_ensure_frontend_dir())
        )
    except Exception:
        # لا نُسقط التطبيق كله بسبب ميزة النسخة الاحتياطية
        logger.exception("تعذّر تفعيل نسخة المتصفح الاحتياطية.")
        return None


_component = _declare()


def _store_key(username: str) -> str:
    return f"tt_data_v1_{username}"


# ─── نسخة البيانات ─────────────────────────────────────────────────────────
def read_copy(username: str) -> None:
    """يقرأ نسخة المتصفح ويضعها في ``_browser_raw`` (نص JSON أو None).

    يوقف التشغيل لحظة حتى يردّ المتصفح، ثم يعيد التشغيل تلقائياً.
    """
    if _component is None:  # الميزة غير متاحة: نكمل بنسخة السيرفر فقط
        st.session_state["_skip_browser"] = True
        st.session_state["_browser_raw"] = None
        return

    with st.sidebar:
        result = _component(
            action="get",
            store_key=_store_key(username),
            key="tt_browser_reader",
            default=None,
        )

    if result is None and not st.session_state.get("_skip_browser"):
        st.info("⏳ جاري قراءة نسختك المحفوظة في المتصفح...")
        if st.button("متابعة بدون نسخة المتصفح"):
            st.session_state["_skip_browser"] = True
            st.rerun()
        st.stop()

    if not isinstance(result, dict) or not result.get("ok"):
        # المتصفح لم يردّ أو ممنوع من التخزين: نكمل بنسخة السيرفر فقط ولا نكتب بالمتصفح
        st.session_state["_skip_browser"] = True
        st.session_state["_browser_raw"] = None
    else:
        st.session_state["_browser_raw"] = result.get("value")


def write_copy(username: str, sidebar: bool = True) -> None:
    """يكتب آخر نسخة محفوظة في المتصفح (يُستدعى كل تشغيل بعد الحفظ).

    ``sidebar=False`` عند الاستدعاء من داخل fragment (لا يُسمح له بكتابة مكوّنات
    في الشريط الجانبي)، فيُرسم المكوّن (بلا ارتفاع) في مكان الاستدعاء.
    """
    payload = st.session_state.get("_browser_payload")
    if _component is None or not payload or st.session_state.get("_skip_browser"):
        return
    with (st.sidebar if sidebar else st.container()):
        _component(
            action="set",
            store_key=_store_key(username),
            value=payload,
            key="tt_browser_writer",
            default=None,
        )


# ─── سجل الحسابات ──────────────────────────────────────────────────────────
def read_accounts() -> tuple[dict, bool]:
    """يعيد (سجل الحسابات المحفوظ بالمتصفح، هل ردّ المتصفح). لا يوقف التشغيل."""
    if _component is None:
        return {}, False
    result = _component(
        action="get", store_key=_ACCOUNTS_KEY, key="tt_accounts_reader", default=None
    )
    if not isinstance(result, dict) or not result.get("ok"):
        return {}, False
    try:
        data = json.loads(result.get("value") or "{}")
    except Exception:
        logger.warning("سجل الحسابات بالمتصفح غير صالح، تم تجاهله.")
        return {}, True
    return (data if isinstance(data, dict) else {}), True


def write_accounts(registry: dict) -> None:
    if _component is None or not registry:
        return
    _component(
        action="set",
        store_key=_ACCOUNTS_KEY,
        value=json.dumps(registry, sort_keys=True),
        key="tt_accounts_writer",
        default=None,
    )
