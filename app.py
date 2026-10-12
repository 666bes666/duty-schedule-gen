from __future__ import annotations

import streamlit as st

from duty_schedule.logging import setup_logging
from duty_schedule.ui.components import render_application

setup_logging()
st.set_page_config(page_title="График дежурств", page_icon=None, layout="wide")

st.markdown(
    """
<style>
:root {
    --fs-section:    1.05rem;
    --fs-tab:        0.9rem;
    --fs-body:       0.875rem;
    --fs-caption:    0.78rem;
    --fs-alert:      0.82rem;
}

/* Tabs: full-width stretch */
.stTabs [data-baseweb="tab-list"] {
    gap: 0;
    width: 100%;
    display: flex;
}
.stTabs [data-baseweb="tab"] {
    flex: 1 1 0;
    justify-content: center;
    height: 2.75rem;
    padding: 0 1rem;
    font-size: var(--fs-tab);
    font-weight: 600;
    border-radius: 4px 4px 0 0;
}

/* Section headers (st.subheader → h3) */
h3 {
    font-size: var(--fs-section) !important;
    font-weight: 600 !important;
    margin-top: 0.75rem !important;
    margin-bottom: 0.25rem !important;
}

/* Captions */
.stCaption, small {
    font-size: var(--fs-caption) !important;
}

/* Alert banners */
.stAlert > div {
    padding: 0.45rem 0.75rem !important;
    font-size: var(--fs-alert) !important;
}
</style>
""",
    unsafe_allow_html=True,
)

st.title("График дежурств")
render_application()
