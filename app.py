"""
نظام جدولة الحصص والامتحانات — نقطة الدخول الرئيسية.

هذا الملف "منسّق" (orchestrator) فقط: يستدعي الوحدات الأخرى بالترتيب الصحيح
ولا يحتوي منطقاً تفصيلياً. لفهم أي جزء من التطبيق راجع الوحدة المختصة به:

- constants.py      ثوابت لا تتغيّر (أسماء الأيام، التخزين الافتراضي...)
- auth.py            حسابات المستخدمين (إنشاء حساب، تسجيل الدخول)
- ui_auth.py          واجهة الدخول/إنشاء حساب/تسجيل الخروج
- models.py         منطق بيانات نقي (تطبيع القيم، بناء نص الخانة...)
- persistence.py    الحفظ والتحميل وتبديل الصفحات (لكل مستخدم ملفه الخاص)
- pdf_export.py     توليد ملفات PDF
- ui_pages.py        واجهة الشريط الجانبي (اختيار/إدارة الصفحات)
- ui_config.py        واجهة إعداد الأقسام/المواد/الأساتذة/التوقيت
- ui_timetable.py      الجدول التفاعلي (تبويبات الأقسام)
- ui_downloads.py      أزرار تحميل PDF/Excel
"""

import streamlit as st

import browser_store
import models
import pdf_export
import persistence
import ui_auth
import ui_config
import ui_downloads
import ui_pages
import ui_timetable
from constants import (
    DEFAULT_PAGE,
    DEFAULT_PAGE_COUNT,
    DEFAULT_TIME_SLOTS,
    PDF_TITLE_BASE,
    SLOT_PAIR,
)


# يحدّث الجدول وحده عند أي تعديل (Streamlit 1.37+؛ بنسخ أقدم قليلاً يُسمّى
# experimental_fragment؛ وبدونهما تعمل الصفحة كلها كالمعتاد بلا تسريع).
_fragment = (
    getattr(st, "fragment", None)
    or getattr(st, "experimental_fragment", None)
    or (lambda func: func)
)


@_fragment
def _work_area(
    username,
    groups,
    group_names,
    courses_data,
    active_course_list,
    room_options,
    slots,
    days,
    group_source,
    pdf_title,
    pdf_left_header,
    pdf_right_header,
) -> None:
    """كل ما يتأثر بتعديل خانة يعيش هنا، فيُعاد تشغيله وحده بدل الصفحة كلها.

    لذلك الحفظ (على السيرفر والمتصفح) وتحميل الملفات داخله أيضاً: بدونه كان
    التعديل لا يُحفظ ولا يُلغي الملفات القديمة إلا عند تحديث الصفحة كلها.
    """
    ui_timetable.render_timetable_tabs(
        groups,
        group_names,
        courses_data,
        active_course_list,
        room_options,
        slots,
        SLOT_PAIR,
        group_source,
        days,
    )
    st.write("---")

    # حفظ تلقائي بعد كل تعديل. يأتي قبل قسم التحميل عمداً: لو فشل توليد PDF أو
    # غاب مجلد الخطوط (st.stop) يبقى كل ما عدّلته محفوظاً.
    persistence.save_data()
    browser_store.write_copy(username, sidebar=False)
    ui_config.render_saved_at()

    pdf_export.ensure_fonts_or_stop()
    ui_downloads.render_downloads(
        groups, group_names, slots, days, pdf_title, pdf_left_header, pdf_right_header
    )


def main() -> None:
    st.set_page_config(layout="wide", page_title="جدول الحصص")

    # ── الدخول: لا يظهر أي شيء من التطبيق قبل تسجيل الدخول ────────────────
    if not ui_auth.render_login_gate():
        return

    username = st.session_state["auth_user"]
    ui_auth.render_session_cookie()
    ui_auth.render_logout_button()
    ui_auth.sync_account_registry()

    # نقرأ نسخة المتصفح قبل تحميل البيانات، ليُفتح الأحدث بين السيرفر والمتصفح
    browser_store.read_copy(username)

    # ── تحميل البيانات عند أول تشغيل للجلسة ──────────────────────────────
    st.session_state.setdefault("selected_page", DEFAULT_PAGE)
    persistence.load_saved_data()
    if st.session_state.pop("_restored_from_browser", False):
        st.success("♻️ استُعيد جدولك من نسخة المتصفح (كانت أحدث من نسخة السيرفر).")

    current_page = st.session_state.get("_loaded_page", DEFAULT_PAGE)
    page_ids = models.page_ids(
        int(st.session_state.get("_page_count", DEFAULT_PAGE_COUNT))
    )
    page_labels = models.page_names(
        st.session_state.get("_page_names", {}), len(page_ids)
    )

    ui_pages.render_page_selector(page_ids, page_labels)
    ui_pages.render_page_management(page_ids, page_labels)

    # ── القيم المحسوبة لهذا التشغيل ───────────────────────────────────────
    pdf_title = f"{PDF_TITLE_BASE} - {page_labels[current_page]}"
    pdf_left_header = str(st.session_state.get("pdf_left_header", "")).strip()
    pdf_right_header = str(
        st.session_state.get("pdf_right_header", pdf_title)
    ).strip()

    groups = models.group_ids(int(st.session_state.get("group_count", 4)))
    group_names = models.normalize_group_names(
        st.session_state.get("group_names", {}),
        len(groups),
        models.page_group_prefix(current_page),
    )
    courses_data = {
        "-- فارغ --": [],
        **models.normalize_courses(st.session_state.get("courses_data", {})),
    }
    course_list = list(courses_data)
    rooms = models.normalize_rooms(st.session_state.get("rooms", []))
    room_options = ["-- اختر القاعة --"] + rooms
    time_slots = models.normalize_time_slots(
        st.session_state.get("time_slots", DEFAULT_TIME_SLOTS)
    )
    slots = models.slot_definitions(time_slots)
    days = models.active_days(st.session_state.get("include_saturday", False))
    # القسم الثاني من كل زوج يُملأ تلقائياً من القسم الأول (كما في النسخة السابقة)
    group_source = {groups[i]: groups[i - 1] for i in range(1, len(groups), 2)}

    # ── واجهة الإعدادات ───────────────────────────────────────────────────
    ui_config.render_header(page_labels[current_page])
    ui_config.render_settings_expander(current_page)
    ui_config.render_date_expander()
    active_course_list = ui_config.render_active_courses_filter(course_list)

    # ── منطقة العمل: الجدول + الحفظ + التحميل (تتحدّث لوحدها دون إعادة الصفحة) ──
    _work_area(
        username,
        groups,
        group_names,
        courses_data,
        active_course_list,
        room_options,
        slots,
        days,
        group_source,
        pdf_title,
        pdf_left_header,
        pdf_right_header,
    )


if __name__ == "__main__":
    main()
