"""
كل ما يخص رسم وتوليد ملفات PDF لجدول الحصص.

هذه الوحدة لا تعتمد على ``st.session_state`` إطلاقاً: كل ما تحتاجه (الجدول،
العنوان، أسماء الأقسام، الفترات الزمنية...) يُمرَّر إليها كمعاملات صريحة من
واجهة المستخدم. هذا يجعلها قابلة للاختبار والاستدعاء بمعزل عن Streamlit،
ويمنع أي تعارض خفي مع بقية التطبيق.
"""

from pathlib import Path

import pandas as pd
import streamlit as st
from fpdf import FPDF
import arabic_reshaper
from bidi.algorithm import get_display

from constants import DAYS as DEFAULT_DAYS

# ═══════════════════════════════════════════════════════════════════════════
# الخطوط
# ═══════════════════════════════════════════════════════════════════════════
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

FONT_REGULAR = FONT_DIR / "DejaVuSans.ttf" if FONT_DIR else None
FONT_BOLD = FONT_DIR / "DejaVuSans-Bold.ttf" if FONT_DIR else None
PDF_FONT = "DejaVu"


def fonts_ready() -> bool:
    """يتحقق من وجود ملفات الخط العربي قبل محاولة توليد أي PDF."""
    return FONT_DIR is not None


def ensure_fonts_or_stop() -> None:
    """يوقف تشغيل الصفحة برسالة واضحة إن كانت ملفات الخط غير موجودة."""
    if not fonts_ready():
        st.error(
            "ملفات الخط العربي غير موجودة. "
            "أضف المجلد fonts وبداخله DejaVuSans.ttf "
            "وDejaVuSans-Bold.ttf إلى مستودع GitHub، "
            "ثم أعد تشغيل التطبيق."
        )
        st.stop()


# ═══════════════════════════════════════════════════════════════════════════
# الألوان والأحجام
# ═══════════════════════════════════════════════════════════════════════════
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


# ═══════════════════════════════════════════════════════════════════════════
# أدوات رسم مساعدة
# ═══════════════════════════════════════════════════════════════════════════
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
    if FONT_REGULAR and FONT_BOLD and FONT_REGULAR.exists() and FONT_BOLD.exists():
        pdf.add_font("DejaVu", "", str(FONT_REGULAR))
        pdf.add_font("DejaVu", "B", str(FONT_BOLD))


def _header_lines(value: str) -> list[str]:
    return [line.strip() for line in str(value or "").splitlines() if line.strip()]


# ═══════════════════════════════════════════════════════════════════════════
# رسم رأس الصفحة
# ═══════════════════════════════════════════════════════════════════════════
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


# ═══════════════════════════════════════════════════════════════════════════
# رسم جدول قسم واحد
# ═══════════════════════════════════════════════════════════════════════════
def _draw_group_table(
    pdf,
    df: pd.DataFrame,
    sx: float,
    sy: float,
    TW: float,
    TH: float,
    slots: list[tuple[str, str, bool]],
    days: list[str] | None = None,
    font_scale: float = 1.0,
) -> None:
    days = list(days) if days else list(DEFAULT_DAYS)
    DAY_W = 20 * font_scale
    PAUSE_W = 13 * font_scale
    ACT_W = (TW - DAY_W - PAUSE_W) / 4
    HDR_H = max(8.0, TH * 0.10)
    ROW_H = (TH - HDR_H) / len(days)
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
    for lbl, _, is_pause in slots:
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
    for di, day in enumerate(days):
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

        for lbl, slot_key, is_pause in slots:
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


# ═══════════════════════════════════════════════════════════════════════════
# نقطتا الدخول العامتان
# ═══════════════════════════════════════════════════════════════════════════
# ─── هندسة الصفحة المشتركة بين ملف القسم الواحد وملف «جميع الأقسام» ───────────
_PAGE_W, _PAGE_H = 297.0, 210.0
_ML = _MR = 8
_MT = 3
_MB = 1
_ADMIN_H = 30
_GRP_LBL = 6
_GAP = 3
_FOOTER_H = 6
_TABLE_W = _PAGE_W - _ML - _MR
# ارتفاع جدول واحد = نصف المساحة المتاحة (صفحة تتسع لجدولين)
_TABLE_H = (
    _PAGE_H - _MT - _ADMIN_H - 2 - (_GRP_LBL * 2) - _GAP - _FOOTER_H - _MB
) / 2


def _draw_group_block(pdf, g, group_label, df, slots, days, y) -> float:
    """يرسم شريط اسم القسم ثم جدوله بنصف ورقة، ويعيد الإحداثي Y بعد الكتلة."""
    _box(pdf, _ML, y, _TABLE_W, _GRP_LBL, BLUE, BLUE, 0)
    _box(pdf, _ML, y, 4, _GRP_LBL, BLUE2, BLUE2, 0)
    pdf.set_font(PDF_FONT, "B", 7.5)
    pdf.set_text_color(*WHITE)
    pdf.set_xy(_ML + 6, y + 1)
    pdf.cell(0, 4.5, _pdf_text(f"GROUPE  {g}  -  Group: {group_label}"), align="L")
    y += _GRP_LBL
    _draw_group_table(pdf, df, _ML, y, _TABLE_W, _TABLE_H, slots, days, font_scale=1.0)
    return y + _TABLE_H + _GAP


def generate_pdf(
    group_id: str,
    df: pd.DataFrame,
    title: str,
    date_str: str,
    group_label: str,
    slots: list[tuple[str, str, bool]],
    days: list[str] | None = None,
    left_header: str = "",
    right_header: str = "",
) -> bytes:
    """يولّد PDF لقسم واحد: الجدول بنصف ورقة (أعلى الصفحة)، تماماً كما يظهر
    كل جدول في ملف «جميع الأقسام»، ويبقى النصف الأسفل فارغاً."""
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    _configure_pdf_fonts(pdf)
    pdf.set_margins(0, 0, 0)
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()
    _draw_admin_header(
        pdf,
        "",
        left_header,
        right_header or title,
        date_str,
        _ML,
        _MT,
        _TABLE_W,
        _ADMIN_H,
    )
    _draw_group_block(pdf, group_id, group_label, df, slots, days, _MT + _ADMIN_H + 2)
    _draw_footer(pdf)
    return bytes(pdf.output())


def generate_all_pdf(
    groups: list[str],
    group_names: dict[str, str],
    timetables: dict[str, pd.DataFrame],
    title: str,
    date_str: str,
    slots: list[tuple[str, str, bool]],
    days: list[str] | None = None,
    left_header: str = "",
    right_header: str = "",
) -> bytes:
    """يولّد PDF بصفحتين: كل صفحة تضم جدولي قسمين فوق بعضهما."""
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    _configure_pdf_fonts(pdf)
    pdf.set_margins(0, 0, 0)
    pdf.set_auto_page_break(auto=False)

    # يُقسَّم الأقسام إلى صفحات من قسمين، بترتيب الظهور في ``groups``.
    pairs = [groups[i : i + 2] for i in range(0, len(groups), 2)]

    for pair in pairs:
        pdf.add_page()
        _draw_admin_header(
            pdf,
            "",
            left_header,
            right_header or title,
            date_str,
            _ML,
            _MT,
            _TABLE_W,
            _ADMIN_H,
        )
        cur_y = _MT + _ADMIN_H + 2
        for g in pair:
            df = timetables.get(g)
            if df is None:
                continue
            cur_y = _draw_group_block(
                pdf, g, group_names.get(g, g), df, slots, days, cur_y
            )
        _draw_footer(pdf)

    return bytes(pdf.output())
