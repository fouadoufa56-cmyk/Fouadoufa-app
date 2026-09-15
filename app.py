import io
import json
from datetime import date, datetime, time
from pathlib import Path
import pandas as pd
import streamlit as st
from fpdf import FPDF
import arabic_reshaper
from bidi.algorithm import get_display
from streamlit_local_storage import LocalStorage


st.set_page_config(layout="wide", page_title="جدول الحصص")
localS = LocalStorage()


DEFAULT_PAGE_COUNT = 3
DEFAULT_PAGE_NAMES = {
    "1": "السنة الأولى",
    "2": "السنة الثانية",
    "3": "السنة الثالثة",
}
DEFAULT_PAGE = "2"
saved_data = localS.getItem("user_schedule_data")

if st.sidebar.button("🗑️ إفراغ البيانات وإعادة الضبط"):
    localS.deleteItem("user_schedule_data")
    st.rerun()

# ═══════════════════════════════════════════════════════════════════════════════
# الإعدادات الافتراضية
# ═══════════════════════════════════════════════════════════════════════════════
LEGACY_COURSES_DATA = {
    "-- فارغ --": [],
    "RDM": ["Pr. ALAMI", "Pr. BENNANI"],
    "MEC DES SOLS": ["Pr. CHEMAOU", "Pr. IDRISSI"],
    "METRE": ["Pr. JAWADI", "Pr. TOUATI"],
    "DAO (AUTOCAD)": ["Pr. ROUSSAFI"],
    "TOPOGRAPHIE": ["Pr. MESKINE", "Pr. TAZI"],
    "CALCUL DE STRUCTURE": ["Pr. JOUDA"],
}
DAYS = ["LUNDI", "MARDI", "MERCREDI", "JEUDI", "VENDREDI"]
EXAM_TYPES = ["Cours", "Controle", "EFM"]

DEFAULT_TIME_SLOTS = [
    {"start": "08:30", "end": "10:25"},
    {"start": "10:35", "end": "12:30"},
    {"start": "13:15", "end": "15:10"},
    {"start": "15:20", "end": "17:15"},
]
# ربط فترات الصباح ببعضها (0<->1) وفترات المساء ببعضها (3<->4)
SLOT_PAIR = {0: 1, 1: 0, 3: 4, 4: 3}
LEGACY_TIME_SLOT_KEYS = [
    "MATIN: 8H30 - 10H25",
    "MATIN: 10H35 - 12H30",
    "PAUSE DEJEUNER",
    "APRES-MIDI: 13H15 - 15H10",
    "APRES-MIDI: 15H20 - 17H15",
]

DATA_FILE = Path(__file__).parent / "saved_data.json"

PDF_TITLE_BASE = "EMPLOI DU TEMPS TECHNICIENS SPECIALISES GENIE CIVIL"
DEFAULT_PDF_LEFT_HEADER = (
    "ROYAUME DU MAROC\n"
    "MINISTERE DE L'INTERIEUR\n"
    "DIRECTION DU DEVELOPPEMENT DES COMPETENCES\n"
    "ET DE LA TRANSFORMATION DIGITALE\n"
    "I.F.T.T.S CASA"
)


def _group_id(index: int) -> str:
    """معرّف قصير ثابت للمجموعة، مع دعم أكثر من 26 مجموعة."""
    return chr(65 + index) if index < 26 else f"G{index + 1}"


def _group_ids(count: int) -> list[str]:
    return [_group_id(i) for i in range(count)]


def _page_ids(count: int) -> list[str]:
    return [str(index + 1) for index in range(count)]


def _page_names(value, count: int) -> dict[str, str]:
    ids = _page_ids(count)
    result = {}
    for page_id in ids:
        default = DEFAULT_PAGE_NAMES.get(page_id, f"الصفحة {page_id}")
        if isinstance(value, dict):
            result[page_id] = str(value.get(page_id, default)).strip() or default
        else:
            result[page_id] = default
    return result


def _page_group_prefix(page_id: str) -> str:
    return f"TS{page_id}"


def _default_settings(page_id: str) -> dict:
    prefix = _page_group_prefix(page_id)
    return {
        "pdf_date": date.today().isoformat(),
        "group_count": 4,
        "group_names": {gid: f"{prefix}{gid}" for gid in _group_ids(4)},
        "courses_data": {
            name: teachers
            for name, teachers in LEGACY_COURSES_DATA.items()
            if name != "-- فارغ --"
        },
        "active_courses": list(LEGACY_COURSES_DATA.keys())[1:],
        "rooms": [],
        "time_slots": DEFAULT_TIME_SLOTS,
        "pdf_left_header": DEFAULT_PDF_LEFT_HEADER,
        "pdf_right_header": (
            f"{PDF_TITLE_BASE} - {DEFAULT_PAGE_NAMES.get(page_id, f'الصفحة {page_id}')}"
        ),
    }


DEFAULT_SETTINGS = _default_settings(DEFAULT_PAGE)

# ═══════════════════════════════════════════════════════════════════════════════
# دوال الحفظ والتحميل
# ═══════════════════════════════════════════════════════════════════════════════


def _normalize_courses(value) -> dict[str, list[str]]:
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


def _normalize_rooms(value) -> list[str]:
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


def _normalize_clock(value, fallback: str) -> str:
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


def _normalize_time_slots(value) -> list[dict[str, str]]:
    """ينظف أربع فترات زمنية، مع الرجوع للتوقيت الافتراضي عند غياب القيمة."""
    result = []
    for index, default in enumerate(DEFAULT_TIME_SLOTS):
        item = value[index] if isinstance(value, list) and index < len(value) else {}
        if not isinstance(item, dict):
            item = {}
        result.append(
            {
                "start": _normalize_clock(item.get("start"), default["start"]),
                "end": _normalize_clock(item.get("end"), default["end"]),
            }
        )
    return result


def _slot_definitions(value=None) -> list[tuple[str, str, bool]]:
    time_slots = _normalize_time_slots(
        st.session_state.get("time_slots", DEFAULT_TIME_SLOTS)
        if value is None
        else value
    )
    active = [
        (f"{item['start']}\n{item['end']}", f"SLOT_{index + 1}", False)
        for index, item in enumerate(time_slots)
    ]
    return (
        active[:2]
        + [
            ("PAUSE", "PAUSE DEJEUNER", True),
        ]
        + active[2:]
    )


def _all_time_slot_keys() -> list[str]:
    return [slot[1] for slot in _slot_definitions()]


def _normalize_group_names(value, count: int, prefix: str = "TS2") -> dict[str, str]:
    ids = _group_ids(count)
    result = {}
    for gid in ids:
        fallback = f"{prefix}{gid}"
        if isinstance(value, dict):
            result[gid] = str(value.get(gid, fallback)).strip() or fallback
        else:
            result[gid] = fallback
    return result


def _cell_parts(value: str) -> tuple[str, str, str, str]:
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


def _cell_with_room(value: str, room: str = "") -> str:
    """يبني قيمة الخانة مع اسم القاعة مع الحفاظ على وسوم الحصة."""
    prefix, course, teacher, _ = _cell_parts(value)
    if not course:
        return ""
    lines = [f"{prefix}{course}", teacher]
    if str(room).strip():
        lines.append(str(room).strip())
    return "\n".join(lines)


def _empty_df() -> pd.DataFrame:
    grid = {slot: [""] * len(DAYS) for slot in _all_time_slot_keys()}
    df = pd.DataFrame(grid, index=DAYS)
    df["PAUSE DEJEUNER"] = "PAUSE DEJEUNER"
    return df


PROFILE_KEY_PREFIXES = ("c_", "t_", "e_", "m_", "r_", "link_", "config_")


def _clear_profile_session() -> None:
    for key in list(st.session_state.keys()):
        if isinstance(key, str) and key.startswith(PROFILE_KEY_PREFIXES):
            del st.session_state[key]
    for key in (
        "pdf_date",
        "group_count",
        "group_names",
        "courses_data",
        "active_courses",
        "rooms",
        "time_slots",
        "pdf_left_header",
        "pdf_right_header",
        "timetables",
    ):
        st.session_state.pop(key, None)


def _load_profile(profile: dict, year: str) -> None:
    defaults = _default_settings(year)
    saved_settings = profile.get("settings", {}) if isinstance(profile, dict) else {}

    pdf_date = saved_settings.get("pdf_date", defaults["pdf_date"])
    try:
        st.session_state["pdf_date"] = date.fromisoformat(str(pdf_date))
    except Exception:
        st.session_state["pdf_date"] = date.today()

    try:
        group_count = max(1, min(30, int(saved_settings.get("group_count", 4))))
    except Exception:
        group_count = 4
    st.session_state["group_count"] = group_count

    saved_courses = _normalize_courses(
        saved_settings.get("courses_data", defaults["courses_data"])
    )
    st.session_state["courses_data"] = saved_courses or _normalize_courses(
        defaults["courses_data"]
    )
    st.session_state["rooms"] = _normalize_rooms(
        saved_settings.get("rooms", defaults.get("rooms", []))
    )
    st.session_state["time_slots"] = _normalize_time_slots(
        saved_settings.get("time_slots", DEFAULT_TIME_SLOTS)
    )
    st.session_state["pdf_left_header"] = str(
        saved_settings.get("pdf_left_header", defaults["pdf_left_header"])
    ).strip()
    st.session_state["pdf_right_header"] = str(
        saved_settings.get("pdf_right_header", defaults["pdf_right_header"])
    ).strip()
    st.session_state["group_names"] = _normalize_group_names(
        saved_settings.get("group_names", defaults["group_names"]),
        group_count,
        _page_group_prefix(year),
    )
    saved_active = saved_settings.get("active_courses")
    if isinstance(saved_active, list):
        active = [
            str(course)
            for course in saved_active
            if str(course) in st.session_state["courses_data"]
        ]
        st.session_state["active_courses"] = active or list(
            st.session_state["courses_data"]
        )
    else:
        st.session_state["active_courses"] = list(st.session_state["courses_data"])

    for wkey, wval in profile.get("widgets", {}).items():
        st.session_state[wkey] = wval

    group_ids = _group_ids(group_count)
    st.session_state.timetables = {gid: _empty_df() for gid in group_ids}
    current_slot_keys = _all_time_slot_keys()
    for gid in group_ids:
        raw = profile.get("timetables", {}).get(gid)
        if raw:
            source_df = pd.DataFrame(raw).reindex(index=DAYS, fill_value="")
            df = _empty_df()
            source_columns = list(source_df.columns)
            for index, slot_key in enumerate(current_slot_keys):
                source_key = slot_key
                if source_key not in source_df.columns:
                    legacy_key = (
                        LEGACY_TIME_SLOT_KEYS[index]
                        if index < len(LEGACY_TIME_SLOT_KEYS)
                        else ""
                    )
                    source_key = (
                        legacy_key
                        if legacy_key in source_df.columns
                        and legacy_key not in current_slot_keys
                        else source_columns[index]
                        if index < len(source_columns)
                        else ""
                    )
                if source_key in source_df.columns:
                    for day in DAYS:
                        df.at[day, slot_key] = source_df.at[day, source_key]
            df["PAUSE DEJEUNER"] = "PAUSE DEJEUNER"
            df.index.name = None
            for day in DAYS:
                for slot in current_slot_keys:
                    if slot != "PAUSE DEJEUNER":
                        df.at[day, slot] = _cell_with_room(df.at[day, slot])
            st.session_state.timetables[gid] = df


def _current_profile() -> dict:
    pdf_date_value = st.session_state.get("pdf_date", date.today())
    settings = {
        "pdf_date": (
            pdf_date_value.isoformat()
            if hasattr(pdf_date_value, "isoformat")
            else str(pdf_date_value)
        ),
        "group_count": int(st.session_state.get("group_count", 4)),
        "group_names": st.session_state.get("group_names", {}),
        "courses_data": st.session_state.get("courses_data", {}),
        "active_courses": st.session_state.get("active_courses", []),
        "rooms": st.session_state.get("rooms", []),
        "time_slots": _normalize_time_slots(
            st.session_state.get("time_slots", DEFAULT_TIME_SLOTS)
        ),
        "pdf_left_header": str(
            st.session_state.get("pdf_left_header", DEFAULT_PDF_LEFT_HEADER)
        ).strip(),
        "pdf_right_header": str(
            st.session_state.get("pdf_right_header", PDF_TITLE_BASE)
        ).strip(),
    }
    widgets = {
        key: value
        for key, value in st.session_state.items()
        if isinstance(key, str)
        and key.startswith(("c_", "t_", "e_", "m_", "r_", "link_"))
    }
    timetables = {
        gid: df.to_dict()
        for gid, df in st.session_state.get("timetables", {}).items()
        if df is not None
    }
    return {"settings": settings, "widgets": widgets, "timetables": timetables}


def load_saved_data() -> None:
    """يحمّل ملف الصفحة المختارة، مع تحويل الملف القديم إلى الصفحة الثانية."""
    requested_page = st.session_state.get("selected_page", DEFAULT_PAGE)

    if "_page_profiles" not in st.session_state:
        profiles = {}
        page_count = DEFAULT_PAGE_COUNT
        page_names = dict(DEFAULT_PAGE_NAMES)
        if DATA_FILE.exists():
            try:
                saved = json.loads(DATA_FILE.read_text(encoding="utf-8"))
                page_config = saved.get("page_config", {})
                try:
                    page_count = max(
                        1, min(20, int(page_config.get("page_count", page_count)))
                    )
                except Exception:
                    page_count = DEFAULT_PAGE_COUNT
                page_names = _page_names(
                    page_config.get("page_names", DEFAULT_PAGE_NAMES),
                    page_count,
                )
                if isinstance(saved.get("years"), dict):
                    profiles = saved["years"]
                elif isinstance(saved.get("pages"), dict):
                    profiles = saved["pages"]
                elif isinstance(saved, dict):
                    # تنسيق النسخة السابقة كان خاصاً بالصفحة الثانية.
                    profiles = {DEFAULT_PAGE: saved}
            except Exception:
                profiles = {}
        st.session_state["_page_profiles"] = profiles
        st.session_state["_page_count"] = page_count
        st.session_state["_page_names"] = page_names

    if (
        st.session_state.get("_data_loaded")
        and st.session_state.get("_loaded_page") == requested_page
    ):
        return

    page_ids = _page_ids(int(st.session_state.get("_page_count", DEFAULT_PAGE_COUNT)))
    if requested_page not in page_ids:
        requested_page = page_ids[0]
        st.session_state["selected_page"] = requested_page

    if st.session_state.get("_data_loaded"):
        old_page = st.session_state.get("_loaded_page", DEFAULT_PAGE)
        st.session_state["_page_profiles"][old_page] = _current_profile()

    _clear_profile_session()
    _load_profile(
        st.session_state["_page_profiles"].get(requested_page, {}),
        requested_page,
    )
    st.session_state["_loaded_page"] = requested_page
    st.session_state["_data_loaded"] = True


def save_data() -> None:
    """يحفظ إعدادات وجداول كل صفحة في ملف واحد."""
    current_page = st.session_state.get("_loaded_page", DEFAULT_PAGE)
    st.session_state["_page_profiles"][current_page] = _current_profile()
    payload = {
        "saved_at": datetime.now().isoformat(),
        "page_config": {
            "page_count": int(st.session_state.get("_page_count", DEFAULT_PAGE_COUNT)),
            "page_names": st.session_state.get("_page_names", {}),
        },
        "pages": st.session_state["_page_profiles"],
    }
    DATA_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def clear_all_data() -> None:
    """يفرّغ جداول الصفحة الحالية فقط، مع إبقاء إعداداتها محفوظة."""
    for key in list(st.session_state.keys()):
        if isinstance(key, str) and key.startswith(
            ("c_", "t_", "e_", "m_", "r_", "link_")
        ):
            del st.session_state[key]
    for gid in st.session_state.get("timetables", {}):
        st.session_state.timetables[gid] = _empty_df()
    save_data()
    st.session_state["_data_loaded"] = True


# ── تحميل البيانات عند أول تشغيل للجلسة ──────────────────────────────────────
st.session_state.setdefault("selected_page", DEFAULT_PAGE)
load_saved_data()

# القيم التي يستخدمها الجدول بعد تحميل إعدادات المستخدم
CURRENT_PAGE = st.session_state.get("_loaded_page", DEFAULT_PAGE)
PAGE_IDS = _page_ids(int(st.session_state.get("_page_count", DEFAULT_PAGE_COUNT)))
PAGE_LABELS = _page_names(
    st.session_state.get("_page_names", DEFAULT_PAGE_NAMES),
    len(PAGE_IDS),
)
st.sidebar.selectbox(
    "صفحة الجدول",
    options=PAGE_IDS,
    format_func=lambda page_id: PAGE_LABELS[page_id],
    key="selected_page",
)

with st.sidebar.expander("🗂️ إدارة الصفحات", expanded=False):
    st.caption(
        "حدد عدد الصفحات وامنح كل صفحة اسماً يناسب استعمالك. "
        "يمكن أن تكون الصفحات سنوات أو تخصصات أو أفواجاً أو أي تصنيف آخر."
    )
    st.session_state.setdefault("page_config_count", len(PAGE_IDS))
    page_config_count = st.number_input(
        "عدد الصفحات",
        min_value=1,
        max_value=20,
        step=1,
        key="page_config_count",
    )
    page_config_ids = _page_ids(int(page_config_count))
    current_page_names = st.session_state.get("_page_names", PAGE_LABELS)
    page_name_inputs = {}
    for page_id in page_config_ids:
        page_name_key = f"page_config_name_{page_id}"
        st.session_state.setdefault(
            page_name_key,
            current_page_names.get(page_id, f"الصفحة {page_id}"),
        )
        page_name_inputs[page_id] = st.text_input(
            f"اسم الصفحة {page_id}",
            key=page_name_key,
                page_name_inputs[page_id] = st.text_input(
            f"اسم الصفحة {page_id}",
            key=page_name_key,
        )

cleaned_page_names = {}

if st.button("💾 حفظ أسماء الصفحات", use_container_width=True):
    page_errors = []
    cleaned_page_names = {}
    for page_id, page_name in page_name_inputs.items():
        page_name = str(page_name).strip()
        if not page_name:
            page_errors.append(f"ادخل اسم الصفحة {page_id}")
        elif page_name in cleaned_page_names.values():
            page_errors.append(f"اسم الصفحة {page_name} مكرر")
        cleaned_page_names[page_id] = page_name

    if page_errors:
        for error in page_errors:
            st.error(error)
    else:
        _apply_page_configuration(cleaned_page_names)
        st.session_state["page_config_notice"] = "تم حفظ أسماء الصفحات بنجاح"
        st.rerun()

if st.session_state.pop("_page_config_notice", None):
    st.success("تم حفظ أسماء الصفحات بنجاح.")

PDF_TITLE = f"{PDF_TITLE_BASE} - {PAGE_LABELS[CURRENT_PAGE]}"
PDF_LEFT_HEADER = str(
    st.session_state.get("pdf_left_header", DEFAULT_PDF_LEFT_HEADER)
).strip()
PDF_RIGHT_HEADER = str(st.session_state.get("pdf_right_header", PDF_TITLE)).strip()
GROUPS = _group_ids(int(st.session_state.get("group_count", 4)))
GROUP_NAMES = _normalize_group_names(
    st.session_state.get("group_names", {}),
    len(GROUPS),
    _page_group_prefix(CURRENT_PAGE),
)
COURSES_DATA = {
    "-- فارغ --": [],
    **_normalize_courses(st.session_state.get("courses_data", LEGACY_COURSES_DATA)),
}
COURSE_LIST = list(COURSES_DATA.keys())
ROOMS = _normalize_rooms(st.session_state.get("rooms", []))
ROOM_OPTIONS = ["-- اختر القاعة --"] + ROOMS
TIME_SLOTS = _normalize_time_slots(
    st.session_state.get("time_slots", DEFAULT_TIME_SLOTS)
)
SLOTS = _slot_definitions(TIME_SLOTS)
ALL_TIME_SLOTS = [slot[1] for slot in SLOTS]
# القسم الثاني من كل زوج يُملأ تلقائياً من القسم الأول، كما في النسخة السابقة
GROUP_SOURCE = {GROUPS[index]: GROUPS[index - 1] for index in range(1, len(GROUPS), 2)}


def _apply_configuration(
    new_group_names: dict[str, str],
    new_courses: dict[str, list[str]],
    new_rooms: list[str],
    new_time_slots: list[dict[str, str]],
    new_pdf_left_header: str,
    new_pdf_right_header: str,
) -> None:
    """يحفظ الإعدادات ويُبقي الخانات الصالحة من الجداول الحالية."""
    old_timetables = st.session_state.get("timetables", {})
    new_group_ids = list(new_group_names)
    valid_courses = set(new_courses)
    new_timetables = {}

    for gid in new_group_ids:
        old_df = old_timetables.get(gid)
        df = old_df.copy() if old_df is not None else _empty_df()
        for day in DAYS:
            for slot in ALL_TIME_SLOTS:
                if slot == "PAUSE DEJEUNER":
                    df.at[day, slot] = "PAUSE DEJEUNER"
                    continue
                value = str(df.at[day, slot])
                clean = (
                    value.replace("[CTRL] ", "")
                    .replace("[EFM] ", "")
                    .replace("[MERGE] ", "")
                    .strip()
                )
                course_name = clean.split("\n", 1)[0] if clean else ""
                if course_name not in valid_courses:
                    df.at[day, slot] = ""
        new_timetables[gid] = df

    for key in list(st.session_state.keys()):
        if isinstance(key, str) and key.startswith(PROFILE_KEY_PREFIXES):
            del st.session_state[key]

    st.session_state["group_count"] = len(new_group_ids)
    st.session_state["group_names"] = new_group_names
    st.session_state["courses_data"] = new_courses
    st.session_state["active_courses"] = list(new_courses)
    st.session_state["rooms"] = new_rooms
    st.session_state["time_slots"] = _normalize_time_slots(new_time_slots)
    st.session_state["pdf_left_header"] = new_pdf_left_header
    st.session_state["pdf_right_header"] = new_pdf_right_header
    st.session_state["timetables"] = new_timetables
    save_data()


def _apply_page_configuration(new_page_names: dict[str, str]) -> None:
    """يحفظ أسماء الصفحات وعددها دون خلط بيانات الصفحات الموجودة."""
    st.session_state["_page_count"] = len(new_page_names)
    st.session_state["_page_names"] = new_page_names
    if st.session_state.get("selected_page") not in new_page_names:
        st.session_state["selected_page"] = next(iter(new_page_names))
    save_data()


# ═══════════════════════════════════════════════════════════════════════════════
# واجهة المستخدم
# ═══════════════════════════════════════════════════════════════════════════════
st.title(f"📆 نظام جدولة الحصص والامتحانات — {PAGE_LABELS[CURRENT_PAGE]}")

# مؤشر آخر حفظ
if DATA_FILE.exists():
    try:
        saved_at = json.loads(DATA_FILE.read_text(encoding="utf-8")).get("saved_at", "")
        if saved_at:
            dt = datetime.fromisoformat(saved_at)
            st.caption(f"💾 آخر حفظ: {dt.strftime('%d/%m/%Y  %H:%M:%S')}")
    except Exception:
        pass

st.write("---")

# ─── إعداد الأقسام والمواد والأساتذة ────────────────────────────────────────────
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
    config_group_ids = _group_ids(int(config_group_count))
    current_group_names = st.session_state.get("group_names", {})

    st.markdown("**أسماء الأقسام أو المجموعات**")
    group_inputs = st.columns(2)
    for index, gid in enumerate(config_group_ids):
        group_key = f"config_group_name_{gid}"
        st.session_state.setdefault(
            group_key,
            current_group_names.get(gid, f"{_page_group_prefix(CURRENT_PAGE)}{gid}"),
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
    current_time_slots = _normalize_time_slots(
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
    st.caption("اكتب اسم قاعة واحدة في كل سطر، مثل: Salle 1 أو Amphi 2.")
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

    st.markdown("**رأس ملف PDF**")
    st.caption(
        "اكتب النص الذي تريد ظهوره في الجهة اليسرى والجهة اليمنى من رأس ملف PDF. "
        "يمكن كتابة عدة أسطر."
    )
    st.session_state.setdefault(
        "config_pdf_left_header",
        st.session_state.get("pdf_left_header", DEFAULT_PDF_LEFT_HEADER),
    )
    st.session_state.setdefault(
        "config_pdf_right_header",
        st.session_state.get("pdf_right_header", PDF_TITLE),
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

        new_rooms = _normalize_rooms(st.session_state.get("config_rooms", ""))

        new_time_slots = []
        for index, default in enumerate(DEFAULT_TIME_SLOTS):
            start_value = _normalize_clock(
                st.session_state.get(f"config_time_start_{index}"),
                default["start"],
            )
            end_value = _normalize_clock(
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
            _apply_configuration(
                new_group_names,
                new_courses,
                new_rooms,
                new_time_slots,
                new_pdf_left_header,
                new_pdf_right_header,
            )
            st.session_state["_config_notice"] = (
                "تم حفظ الإعدادات بنجاح، بما فيها توقيت الحصص."
            )
            st.rerun()

if st.session_state.pop("_config_notice", None):
    st.success("تم حفظ إعدادات الأقسام والمواد والأساتذة بنجاح.")

# ─── التاريخ فقط ──────────────────────────────────────────────────────────────
with st.expander("📅 تاريخ بداية الجدول", expanded=False):
    st.date_input("à partir du", format="DD/MM/YYYY", key="pdf_date")

st.write("---")

# ─── مواد هذا الأسبوع (تصفية القائمة) ──────────────────────────────────────────
with st.expander("📚 مواد هذا الأسبوع (لتصفية القائمة)", expanded=False):
    st.caption(
        "اختر فقط المواد التي ستُدرَّس هذا الأسبوع. ستظهر هذه المواد فقط "
        "في خانات الاختيار داخل الجدول."
    )
    st.session_state["active_courses"] = [
        course
        for course in st.session_state.get("active_courses", COURSE_LIST[1:])
        if course in COURSE_LIST[1:]
    ]
    st.multiselect(
        "المواد النشطة",
        options=COURSE_LIST[1:],
        key="active_courses",
        label_visibility="collapsed",
    )

_active_sel = st.session_state.get("active_courses", COURSE_LIST[1:])
ACTIVE_COURSE_LIST = ["-- فارغ --"] + [c for c in COURSE_LIST[1:] if c in _active_sel]
if len(ACTIVE_COURSE_LIST) == 1:
    st.warning("⚠️ لم تختر أي مادة في «مواد هذا الأسبوع» — سيتم عرض كل المواد مؤقتًا.")
    ACTIVE_COURSE_LIST = COURSE_LIST

st.write("---")

# ─── الجداول التفاعلية ────────────────────────────────────────────────────────
COL_RATIOS = [0.9, 2.0, 2.0, 0.6, 2.0, 2.0]

tabs = st.tabs([f"📋 القسم {g} — {GROUP_NAMES[g]}" for g in GROUPS])
for tab, g in zip(tabs, GROUPS):
    with tab:
        source_g = GROUP_SOURCE.get(g)
        if source_g:
            st.caption(
                f"🔗 هذا القسم يُملأ تلقائيًا من القسم {source_g} — {GROUP_NAMES[source_g]} "
                f"(نفس المادة والأستاذ في الوقت المقابل فقط؛ القاعة مستقلة لكل قسم). "
                f"يمكن إلغاء الربط لأي خانة والتعديل يدويًا."
            )

        hdr = st.columns(COL_RATIOS)
        hdr[0].markdown("**اليوم ↓ / الوقت →**")
        for si, (lbl, _, is_pause) in enumerate(SLOTS):
            ci = si + 1
            if is_pause:
                hdr[ci].markdown(
                    "<div style='background:#f5c518;text-align:center;padding:5px 2px;"
                    "border-radius:6px;font-size:11px;font-weight:bold'>PAUSE</div>",
                    unsafe_allow_html=True,
                )
            else:
                hdr[ci].markdown(
                    f"<div style='background:#1e50a0;color:white;text-align:center;"
                    f"padding:5px 2px;border-radius:6px;font-size:11px;font-weight:bold'>"
                    f"{lbl}</div>",
                    unsafe_allow_html=True,
                )

        st.write("")

        for di, day in enumerate(DAYS):
            row = st.columns(COL_RATIOS)
            row[0].markdown(
                f"<div style='background:#1e3d7a;color:white;text-align:center;"
                f"padding:8px 4px;border-radius:6px;font-size:12px;font-weight:bold'>"
                f"{day}</div>",
                unsafe_allow_html=True,
            )

            for si, (lbl, slot, is_pause) in enumerate(SLOTS):
                ci = si + 1
                with row[ci]:
                    if is_pause:
                        st.markdown(
                            "<div style='background:#ffe599;text-align:center;"
                            "padding:28px 0;border-radius:6px;font-size:11px;"
                            "font-weight:bold'>🍽️</div>",
                            unsafe_allow_html=True,
                        )
                        continue

                    if source_g:
                        lk = f"link_{g}_{di}_{si}"
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
                        src_si = SLOT_PAIR[si]
                        src_val = str(
                            st.session_state.timetables[source_g].at[
                                day, ALL_TIME_SLOTS[src_si]
                            ]
                        )
                        rk = f"r_{g}_{di}_{si}"
                        current_room = _cell_parts(
                            st.session_state.timetables[g].at[day, slot]
                        )[3]
                        if rk not in st.session_state:
                            st.session_state[rk] = (
                                current_room
                                if current_room in ROOM_OPTIONS
                                else ROOM_OPTIONS[0]
                            )
                        elif st.session_state[rk] not in ROOM_OPTIONS:
                            st.session_state[rk] = (
                                current_room
                                if current_room in ROOM_OPTIONS
                                else ROOM_OPTIONS[0]
                            )
                        sel_room = st.selectbox(
                            "القاعة",
                            ROOM_OPTIONS,
                            key=rk,
                            label_visibility="collapsed",
                        )
                        cell_value = _cell_with_room(src_val, sel_room)
                        st.session_state.timetables[g].at[day, slot] = cell_value
                        clean = (
                            cell_value.replace("[CTRL] ", "")
                            .replace("[EFM] ", "")
                            .replace("[MERGE] ", "")
                            .strip()
                        )
                        if clean:
                            parts = clean.splitlines()
                            course_t = parts[0]
                            teach_t = parts[1] if len(parts) > 1 else ""
                            room_t = parts[2] if len(parts) > 2 else ""
                            st.markdown(
                                "<div style='background:#d2ebff;border-right:3px solid #1c66a8;"
                                "border-radius:5px;padding:6px 4px;font-size:11px;"
                                f"text-align:center'>🔗 {course_t}<br>{teach_t}"
                                f"{('<br><small>' + room_t + '</small>') if room_t else ''}</div>",
                                unsafe_allow_html=True,
                            )
                        else:
                            st.markdown(
                                "<div style='color:#999;font-size:10px;text-align:center;"
                                "padding:8px 0'>-- فارغ --</div>",
                                unsafe_allow_html=True,
                            )
                        continue

                    ck = f"c_{g}_{di}_{si}"
                    if (
                        ck in st.session_state
                        and st.session_state[ck] not in ACTIVE_COURSE_LIST
                    ):
                        st.session_state[ck] = "-- فارغ --"
                    sel_course = st.selectbox(
                        "م", ACTIVE_COURSE_LIST, key=ck, label_visibility="collapsed"
                    )

                    if sel_course != "-- فارغ --":
                        tk = f"t_{g}_{di}_{si}_{sel_course}"
                        sel_teacher = st.selectbox(
                            "أ",
                            COURSES_DATA[sel_course],
                            key=tk,
                            label_visibility="collapsed",
                        )

                        rk = f"r_{g}_{di}_{si}"
                        current_room = _cell_parts(
                            st.session_state.timetables[g].at[day, slot]
                        )[3]
                        if rk not in st.session_state:
                            st.session_state[rk] = (
                                current_room
                                if current_room in ROOM_OPTIONS
                                else ROOM_OPTIONS[0]
                            )
                        elif st.session_state[rk] not in ROOM_OPTIONS:
                            st.session_state[rk] = (
                                current_room
                                if current_room in ROOM_OPTIONS
                                else ROOM_OPTIONS[0]
                            )
                        sel_room = st.selectbox(
                            "القاعة",
                            ROOM_OPTIONS,
                            key=rk,
                            label_visibility="collapsed",
                        )

                        ek = f"e_{g}_{di}_{si}"
                        sel_exam = st.selectbox(
                            "ن", EXAM_TYPES, key=ek, label_visibility="collapsed"
                        )

                        mk = f"m_{g}_{di}_{si}"
                        merged = st.checkbox(
                            "جمع", key=mk, help="جمع مجموعتين — لا يُعطي تعارض"
                        )

                        prefix = ""
                        if sel_exam == "Controle":
                            prefix = "[CTRL] "
                        elif sel_exam == "EFM":
                            prefix = "[EFM] "
                        if merged:
                            prefix += "[MERGE] "

                        cell_text = _cell_with_room(
                            f"{prefix}{sel_course}\n({sel_teacher})",
                            sel_room,
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
                                st.markdown(
                                    "<div style='background:#ffe0e0;border-right:3px solid #c00;"
                                    "border-radius:5px;padding:3px 6px;font-size:10px'>"
                                    "⚠️ " + " | ".join(conflicts) + "</div>",
                                    unsafe_allow_html=True,
                                )
                    else:
                        st.session_state.timetables[g].at[day, slot] = ""
                        st.session_state.pop(f"r_{g}_{di}_{si}", None)

        st.write("---")
        with st.expander("👁️ معاينة الجدول", expanded=False):

            def color_cells(val):
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

            st.dataframe(
                st.session_state.timetables[g].style.map(color_cells),
                use_container_width=True,
            )

st.write("---")

# ═══════════════════════════════════════════════════════════════════════════════
# دوال رسم PDF
# ═══════════════════════════════════════════════════════════════════════════════
FONT_LOCATIONS = [
    Path(__file__).resolve().parent / "fonts",
    Path(__file__).resolve().parent / "artifacts" / "timetable" / "fonts",
    Path.cwd() / "fonts",
    Path.cwd() / "artifacts" / "timetable" / "fonts",
]

FONT_DIR = next(
    (
        location
        for location in FONT_LOCATIONS
        if (location / "DejaVuSans.ttf").exists()
        and (location / "DejaVuSans-Bold.ttf").exists()
    ),
    None,
)

if FONT_DIR is None:
    st.error(
        "ملفات الخط العربي غير موجودة. "
        "أضف المجلد fonts وبداخله DejaVuSans.ttf "
        "وDejaVuSans-Bold.ttf إلى مستودع GitHub، "
        "ثم أعد تشغيل التطبيق."
    )
    st.stop()

FONT_REGULAR = FONT_DIR / "DejaVuSans.ttf"
FONT_BOLD = FONT_DIR / "DejaVuSans-Bold.ttf"
PDF_FONT = "DejaVu"

NAVY = (12, 35, 80)
BLUE = (28, 72, 155)
BLUE2 = (45, 95, 175)
HDR_BG = (22, 55, 120)
DAY_BG = (32, 68, 145)
ALT0 = (246, 250, 255)
ALT1 = (255, 255, 255)
GREEN = (208, 240, 215)
YELLOW = (255, 245, 195)
RED = (252, 212, 212)
CYAN = (210, 235, 255)
ORANGE = (255, 231, 168)
WHITE = (255, 255, 255)
LGREY = (170, 170, 170)
MGREY = (110, 110, 130)
PDF_COURSE_SIZE = 8.2
PDF_TEACHER_SIZE = 7.2
PDF_BADGE_SIZE = 6.2
PDF_LEGEND_SIZE = 7.0


def _pdf_text(value: str) -> str:
    """يشكّل العربية ويقلب ترتيبها بصرياً لتظهر صحيحة داخل FPDF."""
    text = str(value or "")
    if not text:
        return ""
    return get_display(arabic_reshaper.reshape(text))


def _box(pdf, x, y, w, h, fill, border=(180, 180, 180), lw=0.25):
    pdf.set_fill_color(*fill)
    pdf.set_draw_color(*border)
    pdf.set_line_width(lw)
    pdf.rect(x, y, w, h, style="FD")


def _cell(
    pdf, x, y, w, h, text, size, bold=False, underline=False, color=(0, 0, 0), align="L"
):
    style = ("B" if bold else "") + ("U" if underline else "")
    pdf.set_font(PDF_FONT, style, size)
    pdf.set_text_color(*color)
    pdf.set_xy(x, y)
    pdf.cell(w, h, _pdf_text(text), align=align)


def _fit_font_size(
    pdf: FPDF, style: str, text: str, target: float, minimum: float, max_width: float
) -> float:
    """يُبقي النص كبيراً مع تصغيره فقط عند الحاجة لاسم طويل."""
    size = target
    pdf.set_font(PDF_FONT, style, size)
    shaped_text = _pdf_text(text)
    while size > minimum and pdf.get_string_width(shaped_text) > max_width:
        size -= 0.25
        pdf.set_font(PDF_FONT, style, size)
    return max(size, minimum)


def _configure_pdf_fonts(pdf: FPDF) -> None:
    """يضمن ظهور أسماء المواد والأساتذة العربية داخل ملفات PDF."""
    if FONT_REGULAR.exists() and FONT_BOLD.exists():
        pdf.add_font("DejaVu", "", str(FONT_REGULAR))
        pdf.add_font("DejaVu", "B", str(FONT_BOLD))


def _header_lines(value: str) -> list[str]:
    return [line.strip() for line in str(value or "").splitlines() if line.strip()]


def _draw_admin_header(
    pdf,
    group_label: str,
    left_header: str,
    right_header: str,
    date_str: str,
    sx: float,
    sy: float,
    TW: float,
    HH: float,
) -> None:
    _box(pdf, sx, sy, TW, HH, (250, 252, 255), (210, 215, 230), 0.3)
    half = TW / 2
    pad = 4

    left_lines = _header_lines(left_header)
    left_area_h = HH - (10 if group_label else 3)
    left_lh = min(3.2, max(1.8, left_area_h / max(len(left_lines), 1)))
    for index, text in enumerate(left_lines):
        fsize = max(5.0, min(8.0, left_lh / 0.42))
        fsize = _fit_font_size(
            pdf, "", text, fsize, max(4.8, fsize * 0.72), half - pad * 2
        )
        _cell(
            pdf,
            sx + pad,
            sy + 2.5 + index * left_lh,
            half - pad * 2,
            left_lh,
            text,
            fsize,
            color=NAVY,
            align="L",
        )

    if group_label:
        group_y = sy + HH - 7
        _box(pdf, sx + pad, group_y, 55, 5.5, NAVY, NAVY, 0)
        _cell(
            pdf,
            sx + pad,
            group_y,
            55,
            5.5,
            f"Group: {group_label}",
            8,
            True,
            color=WHITE,
            align="C",
        )

    pdf.set_draw_color(*BLUE2)
    pdf.set_line_width(0.4)
    pdf.line(sx + half, sy + 4, sx + half, sy + HH - 4)

    rx = sx + half + pad
    rw = half - pad * 2
    right_lines = _header_lines(right_header)
    right_area_h = HH - 11
    right_lh = min(4.8, max(2.4, right_area_h / max(len(right_lines), 1)))
    for index, text in enumerate(right_lines):
        fsize = max(5.2, min(9.0, right_lh / 0.42))
        fsize = _fit_font_size(pdf, "B", text, fsize, max(5.0, fsize * 0.72), rw)
        _cell(
            pdf,
            rx,
            sy + 4 + index * right_lh,
            rw,
            right_lh,
            text,
            fsize,
            bold=True,
            underline=True,
            color=NAVY,
            align="R",
        )
    ty = sy + HH - 9
    _cell(pdf, rx, ty, rw, 5, f"a partir du {date_str}", 8, color=MGREY, align="R")

    pdf.set_draw_color(*BLUE2)
    pdf.set_line_width(0.5)
    pdf.line(sx, sy + HH, sx + TW, sy + HH)


def _draw_group_table(
    pdf,
    df: pd.DataFrame,
    sx: float,
    sy: float,
    TW: float,
    TH: float,
    font_scale: float = 1.0,
) -> None:
    DAY_W = 20 * font_scale
    PAUSE_W = 13 * font_scale
    ACT_W = (TW - DAY_W - PAUSE_W) / 4
    HDR_H = max(8.0, TH * 0.10)
    ROW_H = (TH - HDR_H) / len(DAYS)
    FS = max(5.5, 7 * font_scale)

    _box(pdf, sx, sy, DAY_W, HDR_H, HDR_BG, HDR_BG, 0)
    _cell(
        pdf,
        sx,
        sy + (HDR_H - FS * 0.44) / 2,
        DAY_W,
        FS * 0.44,
        "JOUR",
        FS,
        True,
        color=WHITE,
        align="C",
    )

    cx = sx + DAY_W
    for lbl, _, is_pause in SLOTS:
        cw = PAUSE_W if is_pause else ACT_W
        if is_pause:
            _box(pdf, cx, sy, cw, HDR_H, (195, 155, 25), (195, 155, 25), 0)
            _cell(
                pdf,
                cx,
                sy + (HDR_H - FS * 0.38) / 2,
                cw,
                FS * 0.38,
                "PAUSE",
                FS * 0.82,
                True,
                color=NAVY,
                align="C",
            )
        else:
            _box(pdf, cx, sy, cw, HDR_H, HDR_BG, HDR_BG, 0)
            lines = lbl.split("\n")
            lh = FS * 0.42
            oy = sy + (HDR_H - len(lines) * lh) / 2
            for i, ln in enumerate(lines):
                _cell(
                    pdf, cx, oy + i * lh, cw, lh, ln, FS, True, color=WHITE, align="C"
                )
        cx += cw

    ry = sy + HDR_H
    for di, day in enumerate(DAYS):
        alt = ALT0 if di % 2 == 0 else ALT1
        rx = sx

        _box(pdf, rx, ry, DAY_W, ROW_H, DAY_BG, (20, 50, 115), 0.35)
        _cell(
            pdf,
            rx,
            ry + (ROW_H - FS * 0.44) / 2,
            DAY_W,
            FS * 0.44,
            day,
            FS * 0.9,
            True,
            color=WHITE,
            align="C",
        )
        rx += DAY_W

        for lbl, slot_key, is_pause in SLOTS:
            cw = PAUSE_W if is_pause else ACT_W
            if is_pause:
                _box(pdf, rx, ry, cw, ROW_H, ORANGE, (200, 160, 30), 0.18)
            else:
                val = str(df.at[day, slot_key])
                clean = (
                    val.replace("[CTRL] ", "")
                    .replace("[EFM] ", "")
                    .replace("[MERGE] ", "")
                    .strip()
                )
                if "[EFM]" in val:
                    bg, tag = RED, "EFM"
                elif "[CTRL]" in val:
                    bg, tag = YELLOW, "CTRL"
                elif "[MERGE]" in val:
                    bg, tag = CYAN, "GRPE"
                elif clean:
                    bg, tag = GREEN, ""
                else:
                    bg, tag = alt, ""

                _box(pdf, rx, ry, cw, ROW_H, bg, (185, 185, 185), 0.18)

                if clean:
                    if tag:
                        badge_c = (
                            (210, 40, 40)
                            if tag == "EFM"
                            else (165, 120, 0)
                            if tag == "CTRL"
                            else (0, 80, 160)
                        )
                        bw = 10 * font_scale
                        bh = 3 * font_scale
                        _box(pdf, rx + 1, ry + 1, bw, bh, badge_c, badge_c, 0)
                        badge_size = max(PDF_BADGE_SIZE * font_scale, FS * 0.92)
                        pdf.set_font(PDF_FONT, "B", badge_size)
                        pdf.set_text_color(*WHITE)
                        pdf.set_xy(rx + 1, ry + 1)
                        pdf.cell(bw, bh, tag, align="C")

                    parts = clean.splitlines()
                    course = parts[0][:24]
                    detail = parts[1][:28] if len(parts) > 1 else ""
                    room = parts[2][:28] if len(parts) > 2 else ""

                    course_size = _fit_font_size(
                        pdf,
                        "B",
                        course,
                        max(PDF_COURSE_SIZE * font_scale, FS * 1.12),
                        max(5.8, FS * 0.82),
                        cw - 2,
                    )
                    pdf.set_font(PDF_FONT, "B", course_size)
                    pdf.set_text_color(20, 30, 60)
                    if room:
                        course_y = ry + ROW_H * 0.12
                    else:
                        course_y = ry + ROW_H * (0.28 if detail else 0.38)
                    pdf.set_xy(rx, course_y)
                    pdf.cell(
                        cw,
                        course_size * 0.44,
                        _pdf_text(course),
                        align="C",
                    )

                    if detail:
                        teacher_size = _fit_font_size(
                            pdf,
                            "",
                            detail,
                            max(PDF_TEACHER_SIZE * font_scale, FS),
                            max(5.2, FS * 0.72),
                            cw - 2,
                        )
                        pdf.set_font(PDF_FONT, "", teacher_size)
                        pdf.set_text_color(60, 60, 90)
                        teacher_y = ry + ROW_H * (0.44 if room else 0.60)
                        pdf.set_xy(rx, teacher_y)
                        pdf.cell(
                            cw,
                            teacher_size * 0.40,
                            _pdf_text(detail),
                            align="C",
                        )

                    if room:
                        room_size = _fit_font_size(
                            pdf,
                            "B",
                            room,
                            max(6.2 * font_scale, FS * 0.84),
                            max(5.0, FS * 0.66),
                            cw - 2,
                        )
                        pdf.set_font(PDF_FONT, "B", room_size)
                        pdf.set_text_color(35, 85, 135)
                        pdf.set_xy(rx, ry + ROW_H * 0.73)
                        pdf.cell(
                            cw,
                            room_size * 0.36,
                            _pdf_text(room),
                            align="C",
                        )
            rx += cw

        pdf.set_draw_color(200, 210, 230)
        pdf.set_line_width(0.15)
        pdf.line(sx, ry + ROW_H, sx + TW, ry + ROW_H)
        ry += ROW_H

    pdf.set_draw_color(*BLUE)
    pdf.set_line_width(0.55)
    pdf.rect(sx, sy, TW, TH)


def _draw_footer(pdf):
    H = pdf.h
    W = pdf.w
    pdf.set_draw_color(*BLUE2)
    pdf.set_line_width(0.25)
    pdf.line(8, H - 5, W - 8, H - 5)
    lx = 8
    for bg, label in [
        (GREEN, "Cours"),
        (YELLOW, "Controle"),
        (RED, "EFM"),
        (CYAN, "Gr. Fusionnes"),
        (ORANGE, "Pause"),
    ]:
        _box(pdf, lx, H - 4.2, 4.5, 3.2, bg, LGREY, 0.15)
        pdf.set_font(PDF_FONT, "", PDF_LEGEND_SIZE)
        pdf.set_text_color(*LGREY)
        pdf.set_xy(lx + 5.5, H - 4.2)
        pdf.cell(22, 3.2, label)
        lx += 29
    _box(pdf, 0, H - 1.5, W, 1.5, NAVY, NAVY, 0)


def generate_pdf(
    group_id: str,
    df: pd.DataFrame,
    title: str,
    date_str: str,
    group_label: str,
    left_header: str = "",
    right_header: str = "",
) -> bytes:
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    _configure_pdf_fonts(pdf)
    pdf.set_margins(0, 0, 0)
    pdf.add_page()
    pdf.set_auto_page_break(auto=False)
    W, H = pdf.w, pdf.h
    ML = 8
    MR = 8
    ADMIN_H = 34
    _draw_admin_header(
        pdf,
        group_label,
        left_header or PDF_LEFT_HEADER,
        right_header or title,
        date_str,
        ML,
        3,
        W - ML - MR,
        ADMIN_H,
    )
    TT = 3 + ADMIN_H + 2
    _draw_group_table(pdf, df, ML, TT, W - ML - MR, H - TT - 6, font_scale=1.0)
    _draw_footer(pdf)
    return bytes(pdf.output())


def generate_all_pdf(
    title: str, date_str: str, left_header: str = "", right_header: str = ""
) -> bytes:
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    _configure_pdf_fonts(pdf)
    pdf.set_margins(0, 0, 0)
    pdf.set_auto_page_break(auto=False)
    W, H = 297.0, 210.0
    ML = 8
    MR = 8
    MT = 3
    MB = 1
    ADMIN_H = 30
    TW = W - ML - MR
    GRP_LBL = 6
    GAP = 3
    FH = 6
    avail = H - MT - ADMIN_H - 2 - (GRP_LBL * 2) - GAP - FH - MB
    TH_EA = avail / 2

    for g1, g2 in [("A", "B"), ("C", "D")]:
        pdf.add_page()
        cur_y = MT
        _draw_admin_header(
            pdf,
            "",
            left_header or PDF_LEFT_HEADER,
            right_header or title,
            date_str,
            ML,
            cur_y,
            TW,
            ADMIN_H,
        )
        cur_y += ADMIN_H + 2

        for g in (g1, g2):
            df = st.session_state.timetables[g]
            glbl = GROUP_NAMES.get(g, g)
            _box(pdf, ML, cur_y, TW, GRP_LBL, BLUE, BLUE, 0)
            _box(pdf, ML, cur_y, 4, GRP_LBL, BLUE2, BLUE2, 0)
            pdf.set_font(PDF_FONT, "B", 7.5)
            pdf.set_text_color(*WHITE)
            pdf.set_xy(ML + 6, cur_y + 1)
            pdf.cell(
                0,
                4.5,
                _pdf_text(f"GROUPE  {g}  -  Group: {glbl}"),
                align="L",
            )
            cur_y += GRP_LBL
            _draw_group_table(pdf, df, ML, cur_y, TW, TH_EA, font_scale=1.0)
            cur_y += TH_EA + GAP

        _draw_footer(pdf)

    return bytes(pdf.output())


# ═══════════════════════════════════════════════════════════════════════════════
# تحميل الجداول
# ═══════════════════════════════════════════════════════════════════════════════
st.subheader("⬇️ تحميل الجداول:")

_date_val = st.session_state.get("pdf_date", date.today())
_date_str = (
    _date_val.strftime("%d/%m/%Y") if hasattr(_date_val, "strftime") else str(_date_val)
)

pdf_cols = st.columns(4)
for col, g in zip(pdf_cols, GROUPS):
    with col:
        st.download_button(
            f"📄 PDF — قسم {g}",
            data=generate_pdf(
                g,
                st.session_state.timetables[g],
                PDF_TITLE,
                _date_str,
                GROUP_NAMES[g],
                PDF_LEFT_HEADER,
                PDF_RIGHT_HEADER,
            ),
            file_name=f"emploi_du_temps_groupe_{g}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

st.write("")
c1, c2, c3, c4 = st.columns(4)

with c1:
    st.download_button(
        "📚 PDF — جميع الأقسام (صفحتان)",
        data=generate_all_pdf(PDF_TITLE, _date_str, PDF_LEFT_HEADER, PDF_RIGHT_HEADER),
        file_name="emploi_du_temps_complet.pdf",
        mime="application/pdf",
        use_container_width=True,
    )

excel_buf = io.BytesIO()
with pd.ExcelWriter(excel_buf, engine="openpyxl") as writer:
    for g in GROUPS:
        st.session_state.timetables[g].to_excel(writer, sheet_name=f"Groupe {g}")
excel_buf.seek(0)

with c2:
    st.download_button(
        "📥 Excel — جميع الأقسام",
        data=excel_buf,
        file_name="emploi_du_temps.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

with c4:
    if st.button("🗑️ تفريغ الجداول", use_container_width=True):
        clear_all_data()
        st.rerun()

# ═══════════════════════════════════════════════════════════════════════════════
# حفظ تلقائي في نهاية كل تشغيل
# ═══════════════════════════════════════════════════════════════════════════════
save_data()
