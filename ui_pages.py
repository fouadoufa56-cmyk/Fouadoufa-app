"""واجهة الشريط الجانبي المتعلقة بالصفحات (السنوات/التخصصات)."""

import streamlit as st

import models
import persistence


def render_page_selector(page_ids: list[str], page_labels: dict[str, str]) -> None:
    st.sidebar.selectbox(
        "صفحة الجدول",
        options=page_ids,
        format_func=lambda page_id: page_labels[page_id],
        key="selected_page",
    )


def render_page_management(page_ids: list[str], page_labels: dict[str, str]) -> None:
    with st.sidebar.expander("🗂️ إدارة الصفحات", expanded=False):
        st.caption(
            "حدد عدد الصفحات وامنح كل صفحة اسماً يناسب استعمالك. "
            "يمكن أن تكون الصفحات سنوات أو تخصصات أو أفواجاً أو أي تصنيف آخر."
        )
        st.session_state.setdefault("page_config_count", len(page_ids))
        page_config_count = st.number_input(
            "عدد الصفحات",
            min_value=1,
            max_value=20,
            step=1,
            key="page_config_count",
        )
        page_config_ids = models.page_ids(int(page_config_count))
        current_page_names = st.session_state.get("_page_names", page_labels)
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
            )

        if st.button("💾 حفظ أسماء الصفحات", use_container_width=True):
            page_errors = []
            cleaned_page_names = {}
            for page_id, page_name in page_name_inputs.items():
                page_name = str(page_name).strip()
                if not page_name:
                    page_errors.append(f"أدخل اسم الصفحة {page_id}.")
                elif page_name in cleaned_page_names.values():
                    page_errors.append(f"اسم الصفحة «{page_name}» مكرر.")
                cleaned_page_names[page_id] = page_name

            if page_errors:
                for error in page_errors:
                    st.error(error)
            else:
                persistence.apply_page_configuration(cleaned_page_names)
                st.session_state["_page_config_notice"] = "تم حفظ أسماء الصفحات بنجاح."
                st.rerun()

    if st.session_state.pop("_page_config_notice", None):
        st.success("تم حفظ أسماء الصفحات بنجاح.")
