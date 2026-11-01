"""واجهة الإعدادات: الأقسام، المواد والأساتذة، القاعات، توقيت الحصص، رأس PDF."""

from datetime import datetime, time

import streamlit as st

import models
import persistence
from applog import logger
from constants import DEFAULT_TIME_SLOTS, LEGACY_COURSES_DATA


def render_header(page_label: str) -> None:
    st.title(f"📆 نظام جدولة الحصص والامتحانات — {page_label}")
    st.write("---")


def render_saved_at() -> None:
    """وقت آخر حفظ (يُرسم داخل منطقة العمل ليتحدّث مع كل تعديل)."""
    saved_at = st.session_state.get("_saved_at", "")
    if not saved_at:
        return
    try:
        dt = datetime.fromisoformat(saved_at)
        st.caption(f"💾 آخر حفظ: {dt.strftime('%d/%m/%Y  %H:%M:%S')}")
    except Exception:
        logger.warning("وقت آخر حفظ غير صالح: %r", saved_at)


def render_settings_expander(current_page: str) -> None:
    with st.expander("⚙️ إعداد الأقسام والمواد والأساتذة", expanded=True):
        st.caption(
            "أدخل هذه المعلومات مرة واحدة من هنا. بعد الضغط على «حفظ الإعدادات» "
            "ستظهر الأسماء مباشرة داخل خانات الجدول وتبقى محفوظة عند فتح التطبيق لاحقاً."
        )

        config_group_count = st.number_input(
            "عدد المجموعات / الأقسام",
            min_value=1,
            max_value=30,
            step=1,
            value=int(st.session_state.get("group_count", 4)),
            key="config_group_count",
        )
        config_group_ids = models.group_ids(int(config_group_count))
        current_group_names = st.session_state.get("group_names", {})

        st.markdown("**أسماء الأقسام أو المجموعات**")
        group_inputs = st.columns(2)
        for index, gid in enumerate(config_group_ids):
            group_key = f"config_group_name_{gid}"
            st.session_state.setdefault(
                group_key,
                current_group_names.get(
                    gid, f"{models.page_group_prefix(current_page)}{gid}"
                ),
            )
            with group_inputs[index % 2]:
                st.text_input(f"اسم القسم الموجود {gid}", key=group_key)

        config_course_count = st.number_input(
            "عدد المواد",
            min_value=1,
            max_value=50,
            step=1,
            value=len(st.session_state.get("courses_data", {}))
            or len(LEGACY_COURSES_DATA) - 1,
            key="config_course_count",
        )
        current_courses = st.session_state.get("courses_data", {})
        st.markdown("**أسماء المواد والأساتذة**")
        st.caption("اكتب اسم أستاذ واحد في كل سطر. يمكن إضافة أكثر من أستاذ للمادة نفسها.")
        course_inputs = st.columns(2)
        for index in range(int(config_course_count)):
            course_name_key = f"config_course_name_{index}"
            teachers_key = f"config_course_teachers_{index}"
            existing_names = list(current_courses)
            default_name = existing_names[index] if index < len(existing_names) else ""
            default_teachers = current_courses.get(default_name, [])
            st.session_state.setdefault(course_name_key, default_name)
            st.session_state.setdefault(teachers_key, "\n".join(default_teachers))
            with course_inputs[index % 2]:
                st.text_input(f"اسم المادة {index + 1}", key=course_name_key)
                st.text_area(
                    f"أساتذة المادة {index + 1}",
                    key=teachers_key,
                    height=75,
                    placeholder="مثال:\nالأستاذ الأول\nالأستاذ الثاني",
                )

        st.markdown("**توقيت الحصص**")
        st.caption(
            "عدّل بداية ونهاية كل فترة كما تريد. استراحة الغداء تبقى بين الفترة الثانية والثالثة."
        )
        current_time_slots = models.normalize_time_slots(
            st.session_state.get("time_slots", DEFAULT_TIME_SLOTS)
        )
        for index, current_slot in enumerate(current_time_slots):
            start_key = f"config_time_start_{index}"
            end_key = f"config_time_end_{index}"
            st.session_state.setdefault(
                start_key, time.fromisoformat(current_slot["start"])
            )
            st.session_state.setdefault(end_key, time.fromisoformat(current_slot["end"]))
            time_inputs = st.columns(2)
            with time_inputs[0]:
                st.time_input(f"بداية الفترة {index + 1}", key=start_key)
            with time_inputs[1]:
                st.time_input(f"نهاية الفترة {index + 1}", key=end_key)

        st.markdown("**أسماء القاعات**")
        st.caption(
            "اكتب اسم قاعة واحدة في كل سطر، مثل: Salle 1 أو Amphi 2. "
            "لو كتبت **قاعة واحدة فقط** تُملأ تلقائياً في كل خانات الجدول."
        )
        st.session_state.setdefault(
            "config_rooms",
            "\n".join(st.session_state.get("rooms", [])),
        )
        st.text_area(
            "القاعات المتاحة",
            key="config_rooms",
            height=100,
            placeholder="Salle 1\nSalle 2\nAmphi 2",
        )

        st.markdown("**أيام الأسبوع**")
        st.session_state.setdefault(
            "config_include_saturday",
            bool(st.session_state.get("include_saturday", False)),
        )
        st.checkbox(
            "➕ تفعيل يوم السبت (Samedi) بالجدول",
            key="config_include_saturday",
            help="فعّله لو عندك حصص أحياناً يوم السبت. تقدر تلغيه لاحقاً وقت ما تحتاج.",
        )

        st.markdown("**رأس ملف PDF**")
        st.caption(
            "اكتب النص الذي تريد ظهوره في الجهة اليسرى والجهة اليمنى من رأس ملف PDF. "
            "يمكن كتابة عدة أسطر."
        )
        st.session_state.setdefault(
            "config_pdf_left_header",
            st.session_state.get("pdf_left_header", ""),
        )
        st.session_state.setdefault(
            "config_pdf_right_header",
            st.session_state.get("pdf_right_header", ""),
        )
        pdf_header_inputs = st.columns(2)
        with pdf_header_inputs[0]:
            st.text_area(
                "نص رأس PDF — اليسار",
                key="config_pdf_left_header",
                height=140,
                placeholder="اكتب النص الموجود في الجهة اليسرى",
            )
        with pdf_header_inputs[1]:
            st.text_area(
                "نص رأس PDF — اليمين",
                key="config_pdf_right_header",
                height=140,
                placeholder="اكتب النص الموجود في الجهة اليمنى",
            )

        if st.button("💾 حفظ الإعدادات", type="primary", use_container_width=True):
            errors = []
            new_group_names = {}
            for gid in config_group_ids:
                value = str(st.session_state.get(f"config_group_name_{gid}", "")).strip()
                if not value:
                    errors.append(f"أدخل اسم القسم {gid}.")
                elif value in new_group_names.values():
                    errors.append(f"اسم القسم «{value}» مكرر.")
                new_group_names[gid] = value

            new_rooms = models.normalize_rooms(st.session_state.get("config_rooms", ""))

            new_time_slots = []
            for index, default in enumerate(DEFAULT_TIME_SLOTS):
                start_value = models.normalize_clock(
                    st.session_state.get(f"config_time_start_{index}"),
                    default["start"],
                )
                end_value = models.normalize_clock(
                    st.session_state.get(f"config_time_end_{index}"),
                    default["end"],
                )
                if start_value >= end_value:
                    errors.append(f"يجب أن تكون نهاية الفترة {index + 1} بعد وقت بدايتها.")
                new_time_slots.append({"start": start_value, "end": end_value})

            new_pdf_left_header = str(
                st.session_state.get("config_pdf_left_header", "")
            ).strip()
            new_pdf_right_header = str(
                st.session_state.get("config_pdf_right_header", "")
            ).strip()
            new_include_saturday = bool(
                st.session_state.get("config_include_saturday", False)
            )

            new_courses = {}
            for index in range(int(config_course_count)):
                name = str(st.session_state.get(f"config_course_name_{index}", "")).strip()
                raw_teachers = str(
                    st.session_state.get(f"config_course_teachers_{index}", "")
                )
                teachers = []
                for teacher in raw_teachers.replace(",", "\n").splitlines():
                    teacher = teacher.strip()
                    if teacher and teacher not in teachers:
                        teachers.append(teacher)
                if not name:
                    errors.append(f"أدخل اسم المادة {index + 1}.")
                elif name in new_courses:
                    errors.append(f"اسم المادة «{name}» مكرر.")
                if not teachers:
                    errors.append(
                        f"أدخل أستاذاً واحداً على الأقل للمادة «{name or index + 1}»."
                    )
                new_courses[name] = teachers

            if errors:
                for error in errors:
                    st.error(error)
            else:
                persistence.apply_configuration(
                    new_group_names,
                    new_courses,
                    new_rooms,
                    new_time_slots,
                    new_pdf_left_header,
                    new_pdf_right_header,
                    new_include_saturday,
                )
                st.session_state["_config_notice"] = (
                    "تم حفظ الإعدادات بنجاح، بما فيها توقيت الحصص."
                )
                st.rerun()

    if st.session_state.pop("_config_notice", None):
        st.success("تم حفظ إعدادات الأقسام والمواد والأساتذة بنجاح.")


def render_date_expander() -> None:
    with st.expander("📅 تاريخ بداية الجدول", expanded=False):
        st.date_input("à partir du", format="DD/MM/YYYY", key="pdf_date")
    st.write("---")


def render_active_courses_filter(course_list: list[str]) -> list[str]:
    """يعرض قائمة اختيار المواد النشطة لهذا الأسبوع، ويعيد القائمة الفعلية المستخدمة."""
    with st.expander("📚 مواد هذا الأسبوع (لتصفية القائمة)", expanded=False):
        st.caption(
            "اختر فقط المواد التي ستُدرَّس هذا الأسبوع. ستظهر هذه المواد فقط "
            "في خانات الاختيار داخل الجدول."
        )
        st.session_state["active_courses"] = [
            course
            for course in st.session_state.get("active_courses", course_list[1:])
            if course in course_list[1:]
        ]
        st.multiselect(
            "المواد النشطة",
            options=course_list[1:],
            key="active_courses",
            label_visibility="collapsed",
        )

    active_sel = st.session_state.get("active_courses", course_list[1:])
    active_course_list = ["-- فارغ --"] + [c for c in course_list[1:] if c in active_sel]
    if len(active_course_list) == 1:
        st.warning("⚠️ لم تختر أي مادة في «مواد هذا الأسبوع» — سيتم عرض كل المواد مؤقتًا.")
        active_course_list = course_list

    st.write("---")
    return active_course_list
