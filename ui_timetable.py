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

    # الخانات التي ستُملأ تلقائياً بسبب «جمع» قسم آخر: {(قسم، يوم، فترة): القسم المالك}
    owners = _merge_owners(groups, group_source, len(days), slots)
    _release_unmerged(owners, days, slots)

    tabs = st.tabs([f"📋 القسم {g} — {group_names[g]}" for g in groups])
    for tab, g in zip(tabs, groups):
        with tab:
            _render_group_tab(
                g,
                groups,
                group_names,
                courses_data,
                active_course_list,
                room_options,
                slots,
                all_time_slots,
                slot_pair,
                group_source,
                days,
                owners,
            )

    if _sync_merged_targets(owners, days, slots):
        st.rerun()  # يحدّث العرض بعد نسخ قيم كانت خلف قسم عُرض لاحقاً


def _render_group_tab(
    g,
    groups,
    group_names,
    courses_data,
    active_course_list,
    room_options,
    slots,
    all_time_slots,
    slot_pair,
    group_source,
    days,
    owners,
) -> None:
    source_g = group_source.get(g)
    if source_g:
        st.caption(
            f"🔗 هذا القسم يُملأ تلقائيًا من القسم {source_g} — {group_names[source_g]} "
            f"(نفس المادة والأستاذ في الوقت المقابل فقط؛ القاعة مستقلة لكل قسم). "
            f"يمكن إلغاء الربط لأي خانة والتعديل يدويًا."
        )

    single_room = _single_room(room_options)
    if single_room:
        st.caption(f"🏫 القاعة الوحيدة «{single_room}» تُملأ تلقائياً في كل الخانات.")

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
                    groups,
                    group_names,
                    owners.get((g, di, si)),
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


def _single_room(room_options):
    """لو عُرّفت قاعة واحدة فقط، تُملأ تلقائياً بكل الخانات (لا حاجة لاختيارها)."""
    return room_options[1] if len(room_options) == 2 else None


def _room_for_cell(sel_room, room_options) -> str:
    """«-- اختر القاعة --» تعني بلا قاعة (لا تُكتب داخل الخانة ولا في PDF)."""
    return "" if sel_room == room_options[0] else sel_room


def _is_merge_owner(x, di, si, group_source) -> bool:
    """هل خانة القسم x (يوم di، فترة si) تقوم بـ«جمع» مع أقسام أخرى؟"""
    if not st.session_state.get(state_keys.merge_key(x, di, si)):
        return False
    if not st.session_state.get(state_keys.merge_targets_key(x, di, si)):
        return False
    if st.session_state.get(state_keys.course_key(x, di, si), EMPTY_COURSE) == EMPTY_COURSE:
        return False
    if x in group_source and st.session_state.get(state_keys.link_key(x, di, si), True):
        return False  # الخانة المرتبطة تتبع قسمها المصدر ولا تُجمع بنفسها
    return True


def _merge_owners(groups, group_source, n_days, slots) -> dict:
    """يحسب الخانات المجموعة: {(قسم هدف، يوم، فترة): القسم المالك}.

    الأولوية لترتيب الأقسام: القسم الأسبق يملك، ولا يُستبدل قسم مالك بقسم أسبق
    منه ولا يملك قسمٌ هو نفسه هدف لغيره (لتفادي التضارب والحلقات).
    """
    owners = {}
    for di in range(n_days):
        for si, (_label, _slot, is_pause) in enumerate(slots):
            if is_pause:
                continue
            targets_taken, active_owners = set(), []
            for x in groups:
                if x in targets_taken or not _is_merge_owner(x, di, si, group_source):
                    continue
                claimed = False
                for t in st.session_state.get(state_keys.merge_targets_key(x, di, si), []):
                    if t == x or t not in groups or t in targets_taken or t in active_owners:
                        continue
                    targets_taken.add(t)
                    owners[(t, di, si)] = x
                    claimed = True
                if claimed:
                    active_owners.append(x)
    return owners


def _release_unmerged(owners, days, slots) -> None:
    """خانات كانت مجموعة وانفكّ جمعها: تُفرَّغ (وتُنسى قوائمها) لتبدأ من جديد."""
    previous = st.session_state.get("_merge_targets_prev", set())
    for (g, di, si) in previous - set(owners):
        st.session_state.timetables[g].at[days[di], slots[si][1]] = ""
        prefixes = (
            state_keys.course_key(g, di, si),
            state_keys.exam_type_key(g, di, si),
            state_keys.merge_key(g, di, si),
            state_keys.merge_targets_key(g, di, si),
            state_keys.room_key(g, di, si),
            f"t_{g}_{di}_{si}_",
        )
        for key in list(st.session_state.keys()):
            if isinstance(key, str) and key.startswith(prefixes):
                del st.session_state[key]
    st.session_state["_merge_targets_prev"] = set(owners)


def _sync_merged_targets(owners, days, slots) -> bool:
    """بعد رسم كل الأقسام: يتأكد أن كل خانة هدف تطابق خانة مالكها. يعيد True لو غيّر شيئاً."""
    changed = False
    for (target, di, si), owner in owners.items():
        day, slot = days[di], slots[si][1]
        wanted = str(st.session_state.timetables[owner].at[day, slot])
        if str(st.session_state.timetables[target].at[day, slot]) != wanted:
            st.session_state.timetables[target].at[day, slot] = wanted
            changed = True
    return changed


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
    groups,
    group_names,
    merge_owner,
) -> None:
    if merge_owner:
        # خانة جُمعت مع قسم آخر: تأخذ نسخة من خانته (المادة والأستاذ والقاعة والنوع)
        owner_text = str(st.session_state.timetables[merge_owner].at[day, slot])
        st.session_state.timetables[g].at[day, slot] = owner_text
        _, m_course, m_teacher, m_room = models.cell_parts(owner_text)
        ui_styles.merged_summary(
            f"{merge_owner} — {group_names[merge_owner]}", m_course, m_teacher, m_room
        )
        return

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
        _render_manual_cell(
            g, day, di, si, slot, sel_course, room_options, courses_data,
            groups, group_names,
        )
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
    single_room = _single_room(room_options)
    if single_room:
        sel_room = single_room
    else:
        rk = state_keys.room_key(g, di, si)
        current_room = models.cell_parts(st.session_state.timetables[g].at[day, slot])[3]
        if rk not in st.session_state or st.session_state[rk] not in room_options:
            st.session_state[rk] = (
                current_room if current_room in room_options else room_options[0]
            )
        sel_room = st.selectbox(
            "القاعة", room_options, key=rk, label_visibility="collapsed"
        )
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
    g, day, di, si, slot, sel_course, room_options, courses_data, groups, group_names
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

    single_room = _single_room(room_options)
    if single_room:
        sel_room = single_room
    else:
        rk = state_keys.room_key(g, di, si)
        if rk not in st.session_state or st.session_state[rk] not in room_options:
            st.session_state[rk] = (
                stored_room if stored_room in room_options else room_options[0]
            )
        sel_room = st.selectbox(
            "القاعة", room_options, key=rk, label_visibility="collapsed"
        )

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
    merged = st.checkbox(
        "جمع",
        key=mk,
        help="جمع مع قسم آخر: يدخل القسمان نفس القاعة ونفس الأستاذ في نفس الوقت، "
        "ويُسجَّل الدرس تلقائياً في جدول القسم الذي تختاره.",
    )
    if merged:
        others = [x for x in groups if x != g]
        if others:
            mtk = state_keys.merge_targets_key(g, di, si)
            st.session_state[mtk] = [
                x for x in st.session_state.get(mtk, []) if x in others
            ]
            if not st.session_state[mtk]:
                st.caption("اختر القسم المراد جمعه 👇")
            st.multiselect(
                "جمع مع",
                others,
                key=mtk,
                format_func=lambda x: f"{x} — {group_names[x]}",
                label_visibility="collapsed",
            )

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
