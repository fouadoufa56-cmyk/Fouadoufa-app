"""أزرار تحميل الجداول: PDF لكل قسم، PDF شامل، Excel، وتفريغ الجداول."""

import io

import pandas as pd
import streamlit as st

import pdf_export
import persistence


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

    date_val = st.session_state.get("pdf_date")
    date_str = date_val.strftime("%d/%m/%Y") if hasattr(date_val, "strftime") else str(
        date_val or ""
    )

    pdf_cols = st.columns(4)
    for col, g in zip(pdf_cols, groups):
        with col:
            st.download_button(
                f"📄 PDF — قسم {g}",
                data=pdf_export.generate_pdf(
                    g,
                    st.session_state.timetables[g],
                    pdf_title,
                    date_str,
                    group_names[g],
                    slots,
                    days,
                    pdf_left_header,
                    pdf_right_header,
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
            data=pdf_export.generate_all_pdf(
                groups,
                group_names,
                st.session_state.timetables,
                pdf_title,
                date_str,
                slots,
                days,
                pdf_left_header,
                pdf_right_header,
            ),
            file_name="emploi_du_temps_complet.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

    excel_buf = io.BytesIO()
    with pd.ExcelWriter(excel_buf, engine="openpyxl") as writer:
        for g in groups:
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
            persistence.clear_all_data()
            st.rerun()
