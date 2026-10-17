"""
الجدول التفاعلي: تبويب لكل قسم، والأيام صفوف والفترات أعمدة، وكل خانة فيها
قوائم اختيار منفصلة: المادة، ثم الأستاذ، ثم القاعة، ثم النوع، ثم جمع.

الأقسام المرتبطة (القسم الثاني من كل زوج مثل B يتبع A) تُملأ تلقائياً من
القسم المصدر (نفس المادة والأستاذ في الوقت المقابل؛ القاعة مستقلة)، ويمكن
إلغاء الربط لأي خانة من مربع 🔗 والتعديل يدوياً.
"""

import streamlit as st

import models
import state_keys
import ui_styles
from constants import EXAM_TYPES

COL_RATIOS = [0.9, 2.0, 2.0, 0.6, 2.0, 2.0]
EMPTY_COURSE = "-- فارغ --"


def render_timetable_tabs(
    groups: list[str],
    group_names: dict[str, str],
    courses_data: dict[str, list[str]],
    active_course_list: list[str],
    room_options: list[str],
    slots: list[tuple[str, str, bool]],
    slot_pair: dict[int, int],
    group_source: dict[str, str],
    days: list[str],
) -> None:
    all_time_slots = [slot[1] for slot in slots]

    tabs = st.tabs([f"📋 القسم {g} — {group_names[g]}" for g in groups])
    for tab, g in zip(tabs, groups):
        with tab:
            _render_group_tab(
                g,
                group_names,
                courses_data,
                active_course_list,
                room_options,
                slots,
                all_time_slots,
                slot_pair,
                group_source,
                days,
            )


def _render_group_tab(
    g,
    group_names,
    courses_data,
    active_course_list,
    room_options,
    slots,
    all_time_slots,
    slot_pair,
    group_source,
    days,
) -> None:
    source_g = group_source.get(g)
    if source_g:
        st.caption(
            f"🔗 هذا القسم يُملأ تلقائيًا من القسم {source_g} — {group_names[source_g]} "
            f"(نفس المادة والأستاذ في الوقت المقابل فقط؛ القاعة مستقلة لكل قسم). "
            f"يمكن إلغاء الربط لأي خانة والتعديل يدويًا."
        )

    hdr = st.columns(COL_RATIOS)
    hdr[0].markdown("**اليوم ↓ / الوقت →**")
    for si, (lbl, _, is_pause) in enumerate(slots):
        with hdr[si + 1]:
            ui_styles.header_badge("PAUSE" if is_pause else lbl, is_pause)

    st.write("")

    for di, day in enumerate(days):
        row = st.columns(COL_RATIOS)
        with row[0]:
            ui_styles.day_badge(day)

        for si, (lbl, slot, is_pause) in enumerate(slots):
            with row[si + 1]:
                if is_pause:
                    ui_styles.pause_cell()
                    continue

                _render_cell(
                    g,
                    day,
                    di,
                    si,
                    slot,
                    source_g,
                    slot_pair,
                    all_time_slots,
                    room_options,
                    courses_data,
                    active_course_list,
                )

    st.write("---")
    with st.expander("👁️ معاينة الجدول", expanded=False):
        st.dataframe(
            st.session_state.timetables[g].style.map(_color_cells),
            use_container_width=True,
        )


def _color_cells(val) -> str:
    v = str(val)
    if "[EFM]" in v:
        return "background-color:#ffcccc;font-weight:bold"
    if "[CTRL]" in v:
        return "background-color:#fff3b0;font-weight:bold"
    if "[MERGE]" in v:
        return "background-color:#cce5ff;font-weight:bold"
    if v == "PAUSE DEJEUNER":
        return "background-color:#ffe599"
    if v.strip():
        return "background-color:#d9ead3"
    return ""


def _bare_teacher(teacher: str) -> str:
    """الأستاذ يُخزَّن داخل الخانة بين قوسين «(Pr. X)»؛ هذي الدالة تُرجع الاسم بدونهما."""
    teacher = str(teacher).strip()
    if teacher.startswith("(") and teacher.endswith(")"):
        teacher = teacher[1:-1].strip()
    return teacher


def _room_for_cell(sel_room, room_options) -> str:
    """«-- اختر القاعة --» تعني بلا قاعة (لا تُكتب داخل الخانة ولا في PDF)."""
    return "" if sel_room == room_options[0] else sel_room


def _render_cell(
    g,
    day,
    di,
    si,
    slot,
    source_g,
    slot_pair,
    all_time_slots,
    room_options,
    courses_data,
    active_course_list,
) -> None:
    if source_g:
        lk = state_keys.link_key(g, di, si)
        if lk not in st.session_state:
            st.session_state[lk] = True
        linked = st.checkbox(
            f"🔗 {source_g}",
            key=lk,
            help=f"يُملأ تلقائيًا من القسم {source_g} في الوقت المقابل "
            f"(نفس المادة والأستاذ فقط؛ القاعة مستقلة). "
            f"ألغِ التفعيل للتعديل اليدوي الكامل.",
        )
    else:
        linked = False

    if linked:
        _render_linked_cell(
            g, day, di, si, slot, source_g, slot_pair, all_time_slots, room_options
        )
        return

    ck = state_keys.course_key(g, di, si)
    if st.session_state.get(ck) not in active_course_list:
        st.session_state[ck] = _initial_course(
            g, day, di, si, slot, courses_data, active_course_list
        )
    sel_course = st.selectbox(
        "م", active_course_list, key=ck, label_visibility="collapsed"
    )

    if sel_course != EMPTY_COURSE:
        _render_manual_cell(g, day, di, si, slot, sel_course, room_options, courses_data)
    else:
        st.session_state.timetables[g].at[day, slot] = ""
        st.session_state.pop(state_keys.room_key(g, di, si), None)


def _initial_course(g, day, di, si, slot, courses_data, active_course_list) -> str:
    """القيمة الابتدائية لقائمة المادة عندما لا تكون محفوظة بشكل صالح.

    - بصيغة «المادة — الأستاذ» (من نسخة سابقة): نفصلهما.
    - غير ذلك: نقرأ المادة من الخانة المخزَّنة بالجدول (مثلاً عند إلغاء الربط).
    - لو المادة خارج «مواد هذا الأسبوع» تُفرَّغ الخانة (كما كان دائماً).
    """
    current = st.session_state.get(state_keys.course_key(g, di, si))
    if isinstance(current, str):
        for course in courses_data:
            if course != EMPTY_COURSE and current.startswith(f"{course} — "):
                teacher = current[len(course) + 3 :]
                if course in active_course_list and teacher in courses_data[course]:
                    st.session_state[state_keys.teacher_key(g, di, si, course)] = teacher
                    return course
    course = models.cell_parts(st.session_state.timetables[g].at[day, slot])[1]
    return course if course in active_course_list else EMPTY_COURSE


def _render_linked_cell(
    g, day, di, si, slot, source_g, slot_pair, all_time_slots, room_options
) -> None:
    src_si = slot_pair[si]
    src_val = str(st.session_state.timetables[source_g].at[day, all_time_slots[src_si]])
    rk = state_keys.room_key(g, di, si)
    current_room = models.cell_parts(st.session_state.timetables[g].at[day, slot])[3]
    if rk not in st.session_state or st.session_state[rk] not in room_options:
        st.session_state[rk] = (
            current_room if current_room in room_options else room_options[0]
        )
    sel_room = st.selectbox("القاعة", room_options, key=rk, label_visibility="collapsed")
    cell_value = models.cell_with_room(src_val, _room_for_cell(sel_room, room_options))
    st.session_state.timetables[g].at[day, slot] = cell_value

    clean = (
        cell_value.replace("[CTRL] ", "")
        .replace("[EFM] ", "")
        .replace("[MERGE] ", "")
        .strip()
    )
    if clean:
        parts = clean.splitlines()
        ui_styles.linked_summary(
            parts[0],
            parts[1] if len(parts) > 1 else "",
            parts[2] if len(parts) > 2 else "",
        )
    else:
        ui_styles.empty_placeholder()


def _render_manual_cell(
    g, day, di, si, slot, sel_course, room_options, courses_data
) -> None:
    stored_prefix, _, stored_teacher, stored_room = models.cell_parts(
        st.session_state.timetables[g].at[day, slot]
    )

    tk = state_keys.teacher_key(g, di, si, sel_course)
    if tk not in st.session_state and _bare_teacher(stored_teacher) in courses_data[sel_course]:
        st.session_state[tk] = _bare_teacher(stored_teacher)  # عند إلغاء الربط مثلاً
    sel_teacher = st.selectbox(
        "أ", courses_data[sel_course], key=tk, label_visibility="collapsed"
    )

    rk = state_keys.room_key(g, di, si)
    if rk not in st.session_state or st.session_state[rk] not in room_options:
        st.session_state[rk] = (
            stored_room if stored_room in room_options else room_options[0]
        )
    sel_room = st.selectbox("القاعة", room_options, key=rk, label_visibility="collapsed")

    ek = state_keys.exam_type_key(g, di, si)
    if ek not in st.session_state:
        st.session_state[ek] = (
            "EFM" if "[EFM]" in stored_prefix
            else "Controle" if "[CTRL]" in stored_prefix
            else EXAM_TYPES[0]
        )
    sel_exam = st.selectbox("ن", EXAM_TYPES, key=ek, label_visibility="collapsed")

    mk = state_keys.merge_key(g, di, si)
    if mk not in st.session_state:
        st.session_state[mk] = "[MERGE]" in stored_prefix
    merged = st.checkbox("جمع", key=mk, help="جمع مجموعتين — لا يُعطي تعارض")

    prefix = ""
    if sel_exam == "Controle":
        prefix = "[CTRL] "
    elif sel_exam == "EFM":
        prefix = "[EFM] "
    if merged:
        prefix += "[MERGE] "

    cell_text = models.cell_with_room(
        f"{prefix}{sel_course}\n({sel_teacher})", _room_for_cell(sel_room, room_options)
    )
    st.session_state.timetables[g].at[day, slot] = cell_text

    if not merged:
        conflicts = []
        for og, odf in st.session_state.timetables.items():
            if og == g:
                continue
            ov = str(odf.at[day, slot])
            if ov and ov not in ("", "PAUSE DEJEUNER"):
                if sel_teacher in ov and "[MERGE]" not in ov:
                    conflicts.append(f"محجوز في القسم **{og}**")
        if conflicts:
            ui_styles.conflict_warning(conflicts)
