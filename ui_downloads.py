"""
أزرار تحميل الجداول: PDF لكل قسم، PDF شامل، وتفريغ الجداول.

الملفات **لا تُبنى تلقائياً** مع كل تعديل (كان هذا أثقل جزء في التطبيق). تضغط
«جهّز» فيُبنى الملف مرة واحدة ويظهر زر التحميل. وإن عدّلت الجدول بعدها يُلغى
الملف الجاهز (لئلا تحمّل نسخة قديمة) ويُطلب منك تجهيزه من جديد.
"""

import hashlib
import json

import streamlit as st

import pdf_export
import persistence

GROUP_BUTTONS_PER_ROW = 4


def _fingerprint(groups, group_names, slots, days, title, left, right, date_str) -> str:
    """بصمة لكل ما يدخل في الملفات: لو تغيّرت، الملف الجاهز قديم."""
    payload = {
        "tables": {g: st.session_state.timetables[g].to_dict() for g in groups},
        "meta": [group_names, slots, days, title, left, right, date_str],
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _file_slot(container, cache, fingerprint, key, prepare_label, download_label,
               file_name, mime, make) -> None:
    """زر «جهّز» يتحوّل إلى زر تحميل بعد بناء الملف (ويُعاد بناؤه لو تغيّرت البيانات)."""
    with container:
        placeholder = st.empty()
        entry = cache.get(key)
        data = entry[1] if entry and entry[0] == fingerprint else None
        if data is None:
            if not placeholder.button(
                prepare_label, key=f"prep_{key}", use_container_width=True
            ):
                return
            with st.spinner("جاري تجهيز الملف..."):
                data = make()
            cache[key] = (fingerprint, data)
        placeholder.download_button(
            download_label,
            data=data,
            file_name=file_name,
            mime=mime,
            key=f"dl_{key}",
            use_container_width=True,
        )


def render_downloads(
    groups: list[str],
    group_names: dict[str, str],
    slots: list[tuple[str, str, bool]],
    days: list[str],
    pdf_title: str,
    pdf_left_header: str,
    pdf_right_header: str,
) -> None:
    st.subheader("⬇️ تحميل الجداول:")
    st.caption(
        "اضغط «جهّز» أولاً (يُبنى الملف عند الضغط فقط ليبقى التطبيق سريعاً)، "
        "ثم يظهر زر التحميل. لو عدّلت الجدول بعدها جهّزه من جديد."
    )

    date_val = st.session_state.get("pdf_date")
    date_str = date_val.strftime("%d/%m/%Y") if hasattr(date_val, "strftime") else str(
        date_val or ""
    )
    cache = st.session_state.setdefault("_file_cache", {})
    fingerprint = _fingerprint(
        groups, group_names, slots, days, pdf_title, pdf_left_header,
        pdf_right_header, date_str,
    )

    for start in range(0, len(groups), GROUP_BUTTONS_PER_ROW):
        columns = st.columns(GROUP_BUTTONS_PER_ROW)
        for column, g in zip(columns, groups[start : start + GROUP_BUTTONS_PER_ROW]):
            _file_slot(
                column, cache, fingerprint, f"pdf_{g}",
                f"⚙️ جهّز PDF — قسم {g}", f"📄 تحميل PDF — قسم {g}",
                f"emploi_du_temps_groupe_{g}.pdf", "application/pdf",
                lambda g=g: pdf_export.generate_pdf(
                    g, st.session_state.timetables[g], pdf_title, date_str,
                    group_names[g], slots, days, pdf_left_header, pdf_right_header,
                ),
            )

    st.write("")
    c1, _c2, _c3, c4 = st.columns(4)

    _file_slot(
        c1, cache, fingerprint, "pdf_all",
        "⚙️ جهّز PDF — جميع الأقسام", "📚 تحميل PDF — جميع الأقسام",
        "emploi_du_temps_complet.pdf", "application/pdf",
        lambda: pdf_export.generate_all_pdf(
            groups, group_names, st.session_state.timetables, pdf_title, date_str,
            slots, days, pdf_left_header, pdf_right_header,
        ),
    )

    with c4:
        if st.button("🗑️ تفريغ الجداول", use_container_width=True):
            persistence.clear_all_data()
            st.rerun()
