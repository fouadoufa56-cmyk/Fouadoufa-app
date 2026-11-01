"""قوالب HTML صغيرة قابلة لإعادة الاستخدام لخلايا الجدول (رؤوس، استراحة، تحذيرات)."""

import streamlit as st

PAUSE_BG = "#ffe599"
HEADER_BG = "#1e50a0"
DAY_BG = "#1e3d7a"
LINK_BG = "#d2ebff"
LINK_BORDER = "#1c66a8"
WARNING_BG = "#ffe0e0"
WARNING_BORDER = "#c00"
MUTED = "#999"
MERGE_BG = "#efe3ff"
MERGE_BORDER = "#7a3fc4"


def header_badge(text: str, is_pause: bool = False) -> None:
    bg = PAUSE_BG if is_pause else HEADER_BG
    color = "black" if is_pause else "white"
    st.markdown(
        f"<div style='background:{bg};color:{color};text-align:center;"
        f"padding:5px 2px;border-radius:6px;font-size:11px;font-weight:bold'>"
        f"{text}</div>",
        unsafe_allow_html=True,
    )


def day_badge(day: str) -> None:
    st.markdown(
        f"<div style='background:{DAY_BG};color:white;text-align:center;"
        f"padding:8px 4px;border-radius:6px;font-size:12px;font-weight:bold'>"
        f"{day}</div>",
        unsafe_allow_html=True,
    )


def pause_cell() -> None:
    st.markdown(
        f"<div style='background:{PAUSE_BG};text-align:center;padding:28px 0;"
        f"border-radius:6px;font-size:11px;font-weight:bold'>🍽️</div>",
        unsafe_allow_html=True,
    )


def linked_summary(course: str, teacher: str, room: str) -> None:
    room_html = f"<br><small>{room}</small>" if room else ""
    st.markdown(
        f"<div style='background:{LINK_BG};border-right:3px solid {LINK_BORDER};"
        f"border-radius:5px;padding:6px 4px;font-size:11px;text-align:center'>"
        f"🔗 {course}<br>{teacher}{room_html}</div>",
        unsafe_allow_html=True,
    )


def empty_placeholder(text: str = "-- فارغ --") -> None:
    st.markdown(
        f"<div style='color:{MUTED};font-size:10px;text-align:center;padding:8px 0'>"
        f"{text}</div>",
        unsafe_allow_html=True,
    )


def conflict_warning(messages: list[str]) -> None:
    st.markdown(
        f"<div style='background:{WARNING_BG};border-right:3px solid {WARNING_BORDER};"
        f"border-radius:5px;padding:3px 6px;font-size:10px'>⚠️ "
        + " | ".join(messages)
        + "</div>",
        unsafe_allow_html=True,
    )


def merged_summary(owner_label: str, course: str, teacher: str, room: str) -> None:
    """خانة قسم تم جمعها مع قسم آخر: تظهر القيم المنسوخة (للقراءة فقط)."""
    room_html = f"<br><small>{room}</small>" if room else ""
    st.markdown(
        f"<div style='background:{MERGE_BG};border-right:3px solid {MERGE_BORDER};"
        f"border-radius:5px;padding:6px 4px;font-size:11px;text-align:center'>"
        f"🧷 جمع مع {owner_label}<br><b>{course}</b><br>{teacher}{room_html}</div>",
        unsafe_allow_html=True,
    )
