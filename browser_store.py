"""
نسخة احتياطية من بياناتك داخل متصفحك (localStorage)، بجانب التخزين الأساسي.

- **عند كل حفظ**: تُكتب نسخة كاملة من بياناتك في المتصفح أيضاً (حتى لو فشل
  الحفظ على السيرفر).
- **عند فتح حسابك**: يقارن التطبيق وقت آخر حفظ بين نسخة السيرفر ونسخة المتصفح
  ويفتح الأحدث (راجع ``persistence.load_saved_data``). فلو انمسح السيرفر، ترجع
  جداولك من المتصفح.

حدود: النسخة مربوطة بهذا المتصفح وهذا الجهاز، وتنمسح لو مسحت بيانات المتصفح أو
استعملت التصفح الخفي. القراءة من المتصفح غير فورية، لذلك تظهر رسالة «جاري
القراءة» لحظة عند أول فتح.
"""

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

_component = components.declare_component(
    "tt_browser_store", path=str(Path(__file__).parent / "browser_store_frontend")
)


def _store_key(username: str) -> str:
    return f"tt_data_v1_{username}"


def read_copy(username: str) -> None:
    """يقرأ نسخة المتصفح ويضعها في ``_browser_raw`` (نص JSON أو None).

    يوقف التشغيل لحظة حتى يردّ المتصفح، ثم يعيد التشغيل تلقائياً.
    """
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


def write_copy(username: str) -> None:
    """يكتب آخر نسخة محفوظة في المتصفح (يُستدعى كل تشغيل بعد الحفظ)."""
    payload = st.session_state.get("_browser_payload")
    if not payload or st.session_state.get("_skip_browser"):
        return
    with st.sidebar:
        _component(
            action="set",
            store_key=_store_key(username),
            value=payload,
            key="tt_browser_writer",
            default=None,
        )
