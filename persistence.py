"""
كل ما يخص القراءة والكتابة: تحميل بيانات المستخدم الحالي، تبديل الصفحات،
تطبيق إعدادات جديدة على الجداول الحالية، وحفظ كل شيء بعد كل تعديل.

التخزين الفعلي (ملفات محلية أو قاعدة Supabase) في ``storage.py``. لكل مستخدم
سجل بيانات خاص به لا يشاركه أحد — راجع ``auth.py`` للحسابات.
"""

import hashlib
import json
from datetime import date, datetime

import pandas as pd
import streamlit as st

import models
import storage
from applog import logger
from constants import (
    DEFAULT_PAGE,
    DEFAULT_PAGE_COUNT,
    DEFAULT_PAGE_NAMES,
    DEFAULT_TIME_SLOTS,
    LEGACY_TIME_SLOT_KEYS,
    PROFILE_KEY_PREFIXES,
)


def _username() -> str:
    return st.session_state.get("auth_user", "")


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
    defaults = models.default_settings(year)
    saved_settings = profile.get("settings", {}) if isinstance(profile, dict) else {}

    pdf_date = saved_settings.get("pdf_date", defaults["pdf_date"])
    try:
        st.session_state["pdf_date"] = date.fromisoformat(str(pdf_date))
    except Exception:
        logger.warning("تاريخ محفوظ غير صالح: %r — استُبدل بتاريخ اليوم.", pdf_date)
        st.session_state["pdf_date"] = date.today()

    st.session_state["include_saturday"] = bool(
        saved_settings.get("include_saturday", defaults.get("include_saturday", False))
    )
    days = models.active_days(st.session_state["include_saturday"])

    try:
        group_count = max(1, min(30, int(saved_settings.get("group_count", 4))))
    except Exception:
        logger.warning(
            "عدد أقسام محفوظ غير صالح: %r — استُبدل بـ 4.",
            saved_settings.get("group_count"),
        )
        group_count = 4
    st.session_state["group_count"] = group_count

    saved_courses = models.normalize_courses(
        saved_settings.get("courses_data", defaults["courses_data"])
    )
    st.session_state["courses_data"] = saved_courses or models.normalize_courses(
        defaults["courses_data"]
    )
    st.session_state["rooms"] = models.normalize_rooms(
        saved_settings.get("rooms", defaults.get("rooms", []))
    )
    st.session_state["time_slots"] = models.normalize_time_slots(
        saved_settings.get("time_slots", DEFAULT_TIME_SLOTS)
    )
    st.session_state["pdf_left_header"] = str(
        saved_settings.get("pdf_left_header", defaults["pdf_left_header"])
    ).strip()
    st.session_state["pdf_right_header"] = str(
        saved_settings.get("pdf_right_header", defaults["pdf_right_header"])
    ).strip()
    st.session_state["group_names"] = models.normalize_group_names(
        saved_settings.get("group_names", defaults["group_names"]),
        group_count,
        models.page_group_prefix(year),
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

    group_ids = models.group_ids(group_count)
    st.session_state.timetables = {
        gid: models.empty_df(st.session_state["time_slots"], days) for gid in group_ids
    }
    current_slot_keys = models.all_time_slot_keys(st.session_state["time_slots"])
    for gid in group_ids:
        raw = profile.get("timetables", {}).get(gid)
        if raw:
            source_df = pd.DataFrame(raw).reindex(index=days, fill_value="")
            df = models.empty_df(st.session_state["time_slots"], days)
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
                    for day in days:
                        df.at[day, slot_key] = source_df.at[day, source_key]
            df["PAUSE DEJEUNER"] = "PAUSE DEJEUNER"
            df.index.name = None
            for day in days:
                for slot in current_slot_keys:
                    if slot != "PAUSE DEJEUNER":
                        df.at[day, slot] = models.cell_with_room(df.at[day, slot])
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
        "time_slots": models.normalize_time_slots(
            st.session_state.get("time_slots", DEFAULT_TIME_SLOTS)
        ),
        "include_saturday": bool(st.session_state.get("include_saturday", False)),
        "pdf_left_header": str(st.session_state.get("pdf_left_header", "")).strip(),
        "pdf_right_header": str(st.session_state.get("pdf_right_header", "")).strip(),
    }
    # ملاحظة: نستثني مفاتيح "config_" عمداً — هذي حقول مسودة نموذج الإعدادات
    # (قبل الضغط على زر الحفظ)، ولا يصح حفظها كقيم نهائية دائمة.
    persisted_prefixes = tuple(p for p in PROFILE_KEY_PREFIXES if p != "config_")
    widgets = {
        key: value
        for key, value in st.session_state.items()
        if isinstance(key, str) and key.startswith(persisted_prefixes)
    }
    timetables = {
        gid: df.to_dict()
        for gid, df in st.session_state.get("timetables", {}).items()
        if df is not None
    }
    return {"settings": settings, "widgets": widgets, "timetables": timetables}


def _browser_copy() -> dict | None:
    """نسخة البيانات المحفوظة بالمتصفح (إن وُجدت وكانت صالحة)."""
    raw = st.session_state.get("_browser_raw")
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        logger.warning("نسخة المتصفح غير صالحة، تم تجاهلها.")
        return None


def _pick_newest(server: dict | None, browser: dict | None):
    """يختار الأحدث (بحسب saved_at) بين نسخة السيرفر ونسخة المتصفح."""
    if server is None:
        return browser, ("browser" if browser is not None else None)
    if browser is None:
        return server, "server"
    if str(browser.get("saved_at", "")) > str(server.get("saved_at", "")):
        return browser, "browser"
    return server, "server"


def load_saved_data() -> None:
    """يحمّل ملف حساب المستخدم الحالي، مع تحويل الملف القديم إلى الصفحة الثانية."""
    requested_page = st.session_state.get("selected_page", DEFAULT_PAGE)

    if "_page_profiles" not in st.session_state:
        profiles = {}
        page_count = DEFAULT_PAGE_COUNT
        page_names = dict(DEFAULT_PAGE_NAMES)
        try:
            saved = storage.get("data", _username())
        except storage.StorageError:
            # لا نبدأ ببيانات فارغة: أي حفظ لاحق كان سيمسح بياناتك الحقيقية
            st.error(
                "⚠️ تعذّر تحميل بياناتك من مكان التخزين. لم يتغيّر شيء، ولن يُحفظ "
                "أي شيء الآن حتى لا تُستبدل بياناتك. أعد تحميل الصفحة بعد قليل، "
                "ولو استمرت المشكلة راجع ملف app_errors.log."
            )
            st.stop()
        saved, source = _pick_newest(saved, _browser_copy())
        if source == "browser":
            st.session_state["_restored_from_browser"] = True
        if saved is not None:
            try:
                page_config = saved.get("page_config", {})
                try:
                    page_count = max(
                        1, min(20, int(page_config.get("page_count", page_count)))
                    )
                except Exception:
                    logger.warning(
                        "عدد صفحات محفوظ غير صالح: %r — استُبدل بالقيمة الافتراضية.",
                        page_config.get("page_count"),
                    )
                    page_count = DEFAULT_PAGE_COUNT
                page_names = models.page_names(
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
                logger.exception("بنية بياناتك المحفوظة غير مفهومة.")
                st.error(
                    "⚠️ بياناتك المحفوظة بصيغة غير متوقعة، فتوقف التطبيق حفاظاً عليها. "
                    "راجع ملف app_errors.log."
                )
                st.stop()
            st.session_state["_saved_at"] = saved.get("saved_at", "")
            st.session_state["_browser_payload"] = json.dumps(saved, ensure_ascii=False)
        st.session_state["_page_profiles"] = profiles
        st.session_state["_page_count"] = page_count
        st.session_state["_page_names"] = page_names

    if (
        st.session_state.get("_data_loaded")
        and st.session_state.get("_loaded_page") == requested_page
    ):
        return

    page_id_list = models.page_ids(
        int(st.session_state.get("_page_count", DEFAULT_PAGE_COUNT))
    )
    if requested_page not in page_id_list:
        requested_page = page_id_list[0]
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


def _build_payload_data() -> dict:
    """يبني بنية البيانات القابلة للحفظ (بدون طابع الوقت، يُستخدم في المقارنة)."""
    return {
        "page_config": {
            "page_count": int(st.session_state.get("_page_count", DEFAULT_PAGE_COUNT)),
            "page_names": st.session_state.get("_page_names", {}),
        },
        "pages": st.session_state["_page_profiles"],
    }


def save_data() -> None:
    """يحفظ إعدادات وجداول كل صفحات المستخدم في سجل واحد.

    يتجاهل الحفظ إن كانت البيانات مطابقة تماماً لآخر نسخة محفوظة (مثلاً فتح
    المستخدم قائمة منسدلة دون تغيير أي قيمة فعلية) لتفادي إعادة كتابة الملف
    كاملاً في كل تفاعل بسيط بالواجهة.
    """
    current_page = st.session_state.get("_loaded_page", DEFAULT_PAGE)
    st.session_state["_page_profiles"][current_page] = _current_profile()
    payload_data = _build_payload_data()
    fingerprint = hashlib.sha256(
        json.dumps(payload_data, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    if st.session_state.get("_last_saved_fingerprint") == fingerprint:
        return  # لا شيء تغيّر فعلياً منذ آخر حفظ — لا داعي لإعادة الكتابة

    payload = {"saved_at": datetime.now().isoformat(), **payload_data}
    # نسخة المتصفح تُحدَّث أولاً، فتبقى تعديلاتك محفوظة حتى لو تعذّر الحفظ على السيرفر
    st.session_state["_browser_payload"] = json.dumps(payload, ensure_ascii=False)
    try:
        storage.put("data", _username(), payload)
    except storage.StorageError:
        st.warning("⚠️ تعذّر حفظ البيانات. حاول مرة أخرى بعد قليل.")
        return
    st.session_state["_saved_at"] = payload["saved_at"]
    st.session_state["_last_saved_fingerprint"] = fingerprint


def clear_all_data() -> None:
    """يفرّغ جداول الصفحة الحالية فقط، مع إبقاء إعداداتها محفوظة."""
    persisted_prefixes = tuple(p for p in PROFILE_KEY_PREFIXES if p != "config_")
    for key in list(st.session_state.keys()):
        if isinstance(key, str) and key.startswith(persisted_prefixes):
            del st.session_state[key]
    for gid in st.session_state.get("timetables", {}):
        st.session_state.timetables[gid] = models.empty_df(
            st.session_state.get("time_slots"),
            models.active_days(st.session_state.get("include_saturday", False)),
        )
    save_data()
    st.session_state["_data_loaded"] = True


def apply_configuration(
    new_group_names: dict[str, str],
    new_courses: dict[str, list[str]],
    new_rooms: list[str],
    new_time_slots: list[dict[str, str]],
    new_pdf_left_header: str,
    new_pdf_right_header: str,
    new_include_saturday: bool,
) -> None:
    """يحفظ الإعدادات ويُبقي الخانات الصالحة من الجداول الحالية."""
    old_timetables = st.session_state.get("timetables", {})
    new_group_ids = list(new_group_names)
    valid_courses = set(new_courses)
    normalized_time_slots = models.normalize_time_slots(new_time_slots)
    all_slots = models.all_time_slot_keys(normalized_time_slots)
    new_days = models.active_days(new_include_saturday)
    new_timetables = {}

    for gid in new_group_ids:
        old_df = old_timetables.get(gid)
        if old_df is not None:
            # reindex يضيف صف السبت فارغاً لو فُعِّل جديداً، أو يحذفه لو أُلغي —
            # بقية أيام الأسبوع وقيمها تبقى كما هي دون أي تغيير.
            df = old_df.reindex(index=new_days, fill_value="")
        else:
            df = models.empty_df(normalized_time_slots, new_days)
        for day in new_days:
            for slot in all_slots:
                if slot == "PAUSE DEJEUNER":
                    df.at[day, slot] = "PAUSE DEJEUNER"
                    continue
                value = str(df.at[day, slot]) if slot in df.columns else ""
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
    st.session_state["time_slots"] = normalized_time_slots
    st.session_state["include_saturday"] = new_include_saturday
    st.session_state["pdf_left_header"] = new_pdf_left_header
    st.session_state["pdf_right_header"] = new_pdf_right_header
    st.session_state["timetables"] = new_timetables
    save_data()


def apply_page_configuration(new_page_names: dict[str, str]) -> None:
    """يحفظ أسماء الصفحات وعددها دون خلط بيانات الصفحات الموجودة."""
    st.session_state["_page_count"] = len(new_page_names)
    st.session_state["_page_names"] = new_page_names
    if st.session_state.get("selected_page") not in new_page_names:
        st.session_state["selected_page"] = next(iter(new_page_names))
    save_data()
