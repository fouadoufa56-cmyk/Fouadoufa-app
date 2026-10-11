"""
دوال منطق البيانات: توليد المعرّفات، تطبيع القيم القادمة من التخزين أو من
واجهة المستخدم، وبناء/تفكيك نص الخانة في الجدول.

هذه الدوال "نقية" قدر الإمكان (pure functions): تأخذ قيمة وتُرجع قيمة أخرى،
بلا رسم واجهة وبلا كتابة ملفات، لتبقى سهلة الاختبار وإعادة الاستخدام.
"""

from datetime import date, datetime, time

import pandas as pd
import streamlit as st

from constants import (
    DAYS,
    DEFAULT_PAGE_NAMES,
    DEFAULT_PDF_LEFT_HEADER,
    DEFAULT_TIME_SLOTS,
    LEGACY_COURSES_DATA,
    PDF_TITLE_BASE,
    SATURDAY,
)


# ═══════════════════════════════════════════════════════════════════════════
# معرّفات المجموعات والصفحات
# ═══════════════════════════════════════════════════════════════════════════
def group_id(index: int) -> str:
    """معرّف قصير ثابت للمجموعة، مع دعم أكثر من 26 مجموعة."""
    return chr(65 + index) if index < 26 else f"G{index + 1}"


def group_ids(count: int) -> list[str]:
    return [group_id(i) for i in range(count)]


def page_ids(count: int) -> list[str]:
    return [str(index + 1) for index in range(count)]


def page_names(value, count: int) -> dict[str, str]:
    ids = page_ids(count)
    result = {}
    for pid in ids:
        default = DEFAULT_PAGE_NAMES.get(pid, f"الصفحة {pid}")
        if isinstance(value, dict):
            result[pid] = str(value.get(pid, default)).strip() or default
        else:
            result[pid] = default
    return result


def page_group_prefix(page_id_value: str) -> str:
    return f"TS{page_id_value}"


def default_settings(page_id_value: str) -> dict:
    prefix = page_group_prefix(page_id_value)
    return {
        "pdf_date": date.today().isoformat(),
        "group_count": 4,
        "group_names": {gid: f"{prefix}{gid}" for gid in group_ids(4)},
        "courses_data": {
            name: teachers
            for name, teachers in LEGACY_COURSES_DATA.items()
            if name != "-- فارغ --"
        },
        "active_courses": list(LEGACY_COURSES_DATA.keys())[1:],
        "rooms": [],
        "time_slots": DEFAULT_TIME_SLOTS,
        "include_saturday": False,
        "pdf_left_header": DEFAULT_PDF_LEFT_HEADER,
        "pdf_right_header": (
            f"{PDF_TITLE_BASE} - {DEFAULT_PAGE_NAMES.get(page_id_value, f'الصفحة {page_id_value}')}"
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════
# تطبيع القيم القادمة من ملف الحفظ أو من واجهة المستخدم
# ═══════════════════════════════════════════════════════════════════════════
def normalize_courses(value) -> dict[str, list[str]]:
    """يدعم بنية الإعدادات الجديدة، وكذلك البيانات القديمة إن وُجدت."""
    result: dict[str, list[str]] = {}
    if isinstance(value, dict):
        for name, teachers in value.items():
            clean_name = str(name).strip()
            if not clean_name or clean_name == "-- فارغ --":
                continue
            if isinstance(teachers, str):
                teachers = [teachers]
            if isinstance(teachers, list):
                clean_teachers = []
                for teacher in teachers:
                    clean_teacher = str(teacher).strip()
                    if clean_teacher and clean_teacher not in clean_teachers:
                        clean_teachers.append(clean_teacher)
                result[clean_name] = clean_teachers
    return result


def normalize_rooms(value) -> list[str]:
    """ينظف قائمة القاعات ويزيل الفراغات والتكرار."""
    if isinstance(value, str):
        value = value.replace(",", "\n").splitlines()
    if not isinstance(value, list):
        return []
    rooms = []
    for room in value:
        clean_room = str(room).strip()
        if clean_room and clean_room not in rooms:
            rooms.append(clean_room)
    return rooms


def normalize_clock(value, fallback: str) -> str:
    """يعيد الوقت بصيغة HH:MM حتى يبقى صالحاً للحفظ وملف PDF."""
    if isinstance(value, time):
        return value.strftime("%H:%M")
    raw = str(value or "").strip().upper().replace("H", ":")
    for fmt in ("%H:%M", "%H:%M:%S", "%H"):
        try:
            return datetime.strptime(raw, fmt).strftime("%H:%M")
        except ValueError:
            continue
    return fallback


def normalize_time_slots(value) -> list[dict[str, str]]:
    """ينظف أربع فترات زمنية، مع الرجوع للتوقيت الافتراضي عند غياب القيمة."""
    result = []
    for index, default in enumerate(DEFAULT_TIME_SLOTS):
        item = value[index] if isinstance(value, list) and index < len(value) else {}
        if not isinstance(item, dict):
            item = {}
        result.append(
            {
                "start": normalize_clock(item.get("start"), default["start"]),
                "end": normalize_clock(item.get("end"), default["end"]),
            }
        )
    return result


def normalize_group_names(value, count: int, prefix: str = "TS2") -> dict[str, str]:
    ids = group_ids(count)
    result = {}
    for gid in ids:
        fallback = f"{prefix}{gid}"
        if isinstance(value, dict):
            result[gid] = str(value.get(gid, fallback)).strip() or fallback
        else:
            result[gid] = fallback
    return result


# ═══════════════════════════════════════════════════════════════════════════
# الفترات الزمنية الفعلية المعروضة (مع فترة الاستراحة بينها)
# ═══════════════════════════════════════════════════════════════════════════
def slot_definitions(time_slots=None) -> list[tuple[str, str, bool]]:
    """يبني قائمة (تسمية، مفتاح، هل هي استراحة) بترتيب العرض في الجدول.

    إن لم تُمرَّر ``time_slots`` تُقرأ من session_state الحالية.
    """
    resolved = normalize_time_slots(
        st.session_state.get("time_slots", DEFAULT_TIME_SLOTS)
        if time_slots is None
        else time_slots
    )
    active = [
        (f"{item['start']}\n{item['end']}", f"SLOT_{index + 1}", False)
        for index, item in enumerate(resolved)
    ]
    return active[:2] + [("PAUSE", "PAUSE DEJEUNER", True)] + active[2:]


def all_time_slot_keys(time_slots=None) -> list[str]:
    return [slot[1] for slot in slot_definitions(time_slots)]


# ═══════════════════════════════════════════════════════════════════════════
# محتوى خانة الجدول (المادة + الأستاذ + القاعة + وسوم الحصة)
# ═══════════════════════════════════════════════════════════════════════════
def cell_parts(value: str) -> tuple[str, str, str, str]:
    """يفصل وسم الحصة والمادة والأستاذ والقاعة من قيمة الخانة."""
    raw = str(value)
    prefix = ""
    for marker in ("[CTRL] ", "[EFM] ", "[MERGE] "):
        if marker in raw:
            prefix += marker
    clean = (
        raw.replace("[CTRL] ", "").replace("[EFM] ", "").replace("[MERGE] ", "").strip()
    )
    if not clean:
        return prefix, "", "", ""
    parts = clean.splitlines()
    course = parts[0].strip()
    teacher = parts[1].strip() if len(parts) > 1 else ""
    room = parts[2].strip() if len(parts) > 2 else ""
    # كانت النسخة السابقة تضع اسم القسم بين قوسين مربعين في هذا السطر.
    if room.startswith("[") and room.endswith("]"):
        room = ""
    return prefix, course, teacher, room


def cell_with_room(value: str, room: str = "") -> str:
    """يبني قيمة الخانة مع اسم القاعة مع الحفاظ على وسوم الحصة."""
    prefix, course, teacher, _ = cell_parts(value)
    if not course:
        return ""
    lines = [f"{prefix}{course}", teacher]
    if str(room).strip():
        lines.append(str(room).strip())
    return "\n".join(lines)


def active_days(include_saturday: bool = False) -> list[str]:
    """قائمة أيام الأسبوع الفعلية — تضيف السبت لو كان مفعّلاً بإعدادات الصفحة."""
    return DAYS + ([SATURDAY] if include_saturday else [])


def empty_df(time_slots=None, days=None) -> pd.DataFrame:
    days = list(days) if days is not None else list(DAYS)
    grid = {slot: [""] * len(days) for slot in all_time_slot_keys(time_slots)}
    df = pd.DataFrame(grid, index=days)
    df["PAUSE DEJEUNER"] = "PAUSE DEJEUNER"
    return df
