"""
MIDA Manufacturing Investment Report Generator — Streamlit UI
Run: streamlit run app.py
"""

import streamlit as st
import os
import sys
import datetime
import io
import tempfile
import warnings
warnings.filterwarnings('ignore')

# ── PAGE CONFIG ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="MIDA Report Generator",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CUSTOM CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main-title {
        font-size: 1.8rem;
        font-weight: 700;
        color: #003087;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        font-size: 1rem;
        color: #555;
        margin-bottom: 1.5rem;
    }
    .info-box {
        background: #EEF4FF;
        border-left: 4px solid #003087;
        padding: 0.8rem 1rem;
        border-radius: 4px;
        margin-bottom: 1rem;
        font-size: 0.9rem;
        color: #003087;
    }
    .success-box {
        background: #EAFAF1;
        border-left: 4px solid #1E8449;
        padding: 0.8rem 1rem;
        border-radius: 4px;
        margin-bottom: 1rem;
        font-size: 0.9rem;
    }
    .stat-card {
        background: #F5F8FF;
        border: 1px solid #BDD7EE;
        border-radius: 8px;
        padding: 1rem;
        text-align: center;
    }
    .stat-val {
        font-size: 1.5rem;
        font-weight: 700;
        color: #003087;
    }
    .stat-label {
        font-size: 0.8rem;
        color: #555;
        margin-top: 0.2rem;
    }
    div[data-testid="stDownloadButton"] > button {
        background-color: #003087;
        color: white;
        font-weight: 600;
        border-radius: 6px;
        padding: 0.6rem 1.5rem;
        font-size: 1rem;
        width: 100%;
    }
    div[data-testid="stDownloadButton"] > button:hover {
        background-color: #002060;
    }
</style>
""", unsafe_allow_html=True)


# ── LAZY IMPORTS (only after upload so Streamlit boots fast) ─────────────────
@st.cache_resource
def _import_core():
    """Import heavy dependencies once and cache them."""
    import pandas as pd
    import numpy as np
    import pickle
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, KeepTogether, Flowable, Image as RLImage
    )
    from reportlab.platypus.tableofcontents import TableOfContents
    return True  # just trigger the import


# ── LOAD THE CORE LOGIC ──────────────────────────────────────────────────────
# We import the report functions from mida_report_core.py which is the
# original script with main() stripped out (or we import selectively).
# We'll import the whole module but override main() behaviour.

def load_report_module():
    """Import the core report module, suppressing its __main__ block."""
    import importlib.util, sys
    spec = importlib.util.spec_from_file_location(
        "mida_core",
        os.path.join(os.path.dirname(__file__), "mida_report_core.py")
    )
    mod = importlib.util.load_from_spec = spec
    module = importlib.util.module_from_spec(spec)
    # Prevent the script from running its if __name__=='__main__' block
    spec.loader.exec_module(module)
    return module


@st.cache_data(show_spinner=False)
def cached_load_excel(file_bytes: bytes, filename: str):
    """
    Load and process the Excel file.
    Cached by file content hash so re-uploads of the same file are instant.
    """
    import tempfile, pandas as pd

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        mod = load_report_module()
        df = mod.load_excel(tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
            # Remove cache file if created
            cache_path = tmp_path + '.cache9.pkl'
            if os.path.exists(cache_path):
                os.unlink(cache_path)
        except Exception:
            pass

    return df


def generate_pdf(df, year: int, period_key: str) -> bytes:
    """Run the full report generation and return PDF bytes."""
    import tempfile

    mod = load_report_module()

    pl, months = mod.PERIODS[period_key]
    cur, prev = mod.filt(df, year, months)
    prev_pl, prev_qoq = mod.filt_qoq(df, year, months)

    out_path = os.path.join(tempfile.gettempdir(),
                            f"MIDA_{year}_{period_key}_{datetime.datetime.now().strftime('%H%M%S')}.pdf")

    story = []
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate
    from reportlab.lib.units import cm

    LW  = landscape(A4)[0]
    MAR = 1.4 * cm

    doc = SimpleDocTemplate(
        out_path,
        pagesize=landscape(A4),
        leftMargin=MAR, rightMargin=MAR,
        topMargin=1.2*cm, bottomMargin=1.8*cm,
        title=f'MIDA Manufacturing {year}', author='MIDA'
    )

    mod.sec_cover(story, year, pl)
    mod.sec_toc(story, year, pl)
    mod.sec_yoy(story, cur, prev, year, pl)
    mod.sec_qoq(story, cur, prev_qoq, year, pl, prev_pl)
    mod.sec_overview(story, cur, prev, year, pl)
    mod.sec_cipe(story, cur, year, pl)
    mod.sec_emp_category(story, cur, prev, year, pl)
    mod.sec_mts(story, cur, prev, year, pl)
    mod.sec_mts_local_foreign(story, cur, prev, year, pl)
    mod.sec_salary(story, cur, prev, year, pl)
    mod.sec_salary_local_foreign(story, cur, prev, year, pl)
    mod.sec_export(story, cur, prev, year, pl)
    mod.sec_rawmat(story, cur, prev, year, pl)
    mod.sec_i40(story, cur, prev, year, pl)
    mod.sec_indicators(story, cur, prev, year, pl)
    mod.sec_green(story, cur, prev, year, pl)
    mod.sec_state(story, cur, prev, year, pl)
    mod.sec_lds_state(story, cur, prev, year, pl)
    mod.sec_state_top3(story, cur, prev, year, pl)
    mod.sec_country(story, cur, prev, year, pl)
    mod.sec_top5(story, cur, year, pl)

    footer = mod.footer_fn(year, pl)
    doc.multiBuild(story, onFirstPage=footer, onLaterPages=footer)

    with open(out_path, 'rb') as f:
        pdf_bytes = f.read()

    try:
        os.unlink(out_path)
    except Exception:
        pass

    return pdf_bytes


# ── HEADER ───────────────────────────────────────────────────────────────────
col_logo, col_title = st.columns([1, 5])
with col_logo:
    st.markdown(
        "<div style='background:#003087;border-radius:10px;padding:14px 10px;"
        "text-align:center;margin-top:6px;'>"
        "<span style='font-size:2rem;'>📊</span></div>",
        unsafe_allow_html=True
    )
with col_title:
    st.markdown('<div class="main-title">MIDA Manufacturing Investment Report Generator</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Malaysia Investment Development Authority — Automated PDF Report</div>', unsafe_allow_html=True)

st.divider()

# ── SIDEBAR ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Report Settings")
    st.markdown("---")

    uploaded_file = st.file_uploader(
        "📂 Upload Excel Data File",
        type=["xlsx"],
        help="Upload the MIDA investment data Excel file. Must contain an 'All' sheet with a 'Date Approved' header."
    )

    st.markdown("---")
    st.markdown("#### 📅 Report Period")

    PERIOD_OPTIONS = {
        "Q1 — Jan to Mar": "1",
        "H1 — Jan to Jun": "2",
        "Q3 — Jan to Sep": "3",
        "Full Year — Jan to Dec": "4",
    }

    selected_period_label = st.selectbox(
        "Period",
        list(PERIOD_OPTIONS.keys()),
        index=3,
        help="Select the reporting period to include in the report."
    )
    period_key = PERIOD_OPTIONS[selected_period_label]

    st.markdown("---")
    st.markdown(
        "<div class='info-box'>ℹ️ The report compares the selected period "
        "against the same period in the prior year (YoY) and against the "
        "immediately preceding quarter/half (QoQ).</div>",
        unsafe_allow_html=True
    )

    st.markdown("---")
    st.caption("MIDA Report Generator v1.0  |  Streamlit Edition")


# ── MAIN AREA ─────────────────────────────────────────────────────────────────
if uploaded_file is None:
    # Welcome / instructions state
    st.markdown("### 👋 Welcome")
    c1, c2, c3 = st.columns(3)
    steps = [
        ("1️⃣", "Upload Excel", "Use the sidebar to upload your MIDA investment data `.xlsx` file."),
        ("2️⃣", "Select Period", "Choose the reporting period (Q1, H1, Q3, or Full Year)."),
        ("3️⃣", "Generate & Download", "Select the year, click **Generate Report**, then download the PDF."),
    ]
    for col, (icon, title, desc) in zip([c1, c2, c3], steps):
        with col:
            st.markdown(
                f"<div class='stat-card'>"
                f"<div style='font-size:2rem'>{icon}</div>"
                f"<div style='font-weight:700;color:#003087;margin:0.5rem 0'>{title}</div>"
                f"<div style='font-size:0.85rem;color:#555'>{desc}</div>"
                f"</div>",
                unsafe_allow_html=True
            )

    st.markdown("---")
    st.markdown("#### 📋 Required Excel Format")
    st.markdown(
        "The Excel file must contain a sheet named **`All`** (or the first sheet will be used). "
        "The data must have a **`Date Approved`** header row and include columns such as "
        "`Main Sector`, `Total Investment (RM)`, `Total Employment`, `State`, `Ultimate Country`, etc."
    )

else:
    # ── FILE LOADED ──────────────────────────────────────────────────────────
    file_bytes = uploaded_file.read()
    file_size_kb = len(file_bytes) / 1024

    st.markdown(f"### 📂 File: `{uploaded_file.name}`  &nbsp; ({file_size_kb:,.0f} KB)")

    with st.spinner("🔄 Loading and processing Excel data..."):
        try:
            df = cached_load_excel(file_bytes, uploaded_file.name)
            load_ok = True
        except Exception as e:
            st.error(f"❌ Failed to load Excel file: {e}")
            st.stop()

    # ── DATA SUMMARY ─────────────────────────────────────────────────────────
    mod = load_report_module()

    mfg = df[df[mod.CSEC] == 'Manufacturing']
    avail_years = sorted(mfg['_y'].dropna().unique().astype(int), reverse=True)

    if not avail_years:
        st.error("❌ No Manufacturing sector data found in this file.")
        st.stop()

    # Stats row
    st.markdown("#### 📊 Dataset Overview")
    s1, s2, s3, s4 = st.columns(4)
    with s1:
        st.markdown(
            f"<div class='stat-card'><div class='stat-val'>{len(df):,}</div>"
            f"<div class='stat-label'>Total Projects (All Sectors)</div></div>",
            unsafe_allow_html=True
        )
    with s2:
        st.markdown(
            f"<div class='stat-card'><div class='stat-val'>{len(mfg):,}</div>"
            f"<div class='stat-label'>Manufacturing Projects</div></div>",
            unsafe_allow_html=True
        )
    with s3:
        st.markdown(
            f"<div class='stat-card'><div class='stat-val'>{avail_years[0]}</div>"
            f"<div class='stat-label'>Latest Year</div></div>",
            unsafe_allow_html=True
        )
    with s4:
        st.markdown(
            f"<div class='stat-card'><div class='stat-val'>{len(avail_years)}</div>"
            f"<div class='stat-label'>Years Available</div></div>",
            unsafe_allow_html=True
        )

    st.markdown("---")

    # ── YEAR SELECTOR ────────────────────────────────────────────────────────
    st.markdown("#### 📅 Select Report Year")

    col_yr, col_info = st.columns([2, 3])
    with col_yr:
        selected_year = st.selectbox(
            "Year",
            avail_years,
            index=0,
            help="Select the target year for the report. The prior year is used automatically for YoY comparison."
        )
    with col_info:
        pl, months = mod.PERIODS[period_key]
        cur_preview, prev_preview = mod.filt(df, selected_year, months)
        st.markdown(
            f"<div class='info-box'>"
            f"<b>{selected_year} ({pl}):</b> {len(cur_preview):,} projects &nbsp;|&nbsp; "
            f"<b>{selected_year-1} ({pl}):</b> {len(prev_preview):,} projects<br>"
            f"<b>Investment {selected_year}:</b> RM {cur_preview[mod.CTRM].sum()/1e9:,.1f} bil &nbsp;|&nbsp; "
            f"<b>{selected_year-1}:</b> RM {prev_preview[mod.CTRM].sum()/1e9:,.1f} bil"
            f"</div>",
            unsafe_allow_html=True
        )

    # ── GENERATE BUTTON ──────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 📄 Generate Report")

    output_filename = f"MIDA_Manufacturing_{selected_year}_{pl.split()[0]}.pdf"

    gen_col, dl_col = st.columns([1, 1])

    with gen_col:
        generate = st.button(
            "🚀 Generate PDF Report",
            type="primary",
            use_container_width=True,
            help=f"Generate the full manufacturing investment report for {selected_year} {pl}"
        )

    if generate:
        progress_bar = st.progress(0, text="Starting report generation...")
        status_area  = st.empty()

        sections = [
            (5,  "Cover & Table of Contents"),
            (12, "YoY Summary"),
            (20, "QoQ Summary"),
            (28, "Sector Overview & CIPE"),
            (38, "Employment Breakdown (MTS, Salary)"),
            (50, "Export & Raw Materials"),
            (60, "Industry 4.0 & Indicators"),
            (70, "Green Investment"),
            (80, "State Analysis"),
            (90, "Country Analysis"),
            (98, "Top 10 Projects"),
        ]

        try:
            # We run generation step by step to update the progress bar
            import threading

            pdf_result = [None]
            error_result = [None]

            def _run():
                try:
                    pdf_result[0] = generate_pdf(df, selected_year, period_key)
                except Exception as exc:
                    error_result[0] = exc

            thread = threading.Thread(target=_run)
            thread.start()

            import time
            sec_idx = 0
            while thread.is_alive():
                if sec_idx < len(sections):
                    pct, label = sections[sec_idx]
                    progress_bar.progress(pct, text=f"⏳ Processing: {label}...")
                    sec_idx += 1
                time.sleep(1.2)
                thread.join(timeout=0)

            thread.join()
            progress_bar.progress(100, text="✅ Report complete!")

            if error_result[0]:
                raise error_result[0]

            pdf_bytes = pdf_result[0]
            st.session_state["pdf_bytes"]    = pdf_bytes
            st.session_state["pdf_filename"] = output_filename

            st.markdown(
                f"<div class='success-box'>"
                f"✅ <b>Report generated successfully!</b><br>"
                f"File: <code>{output_filename}</code> &nbsp; ({len(pdf_bytes)/1024:,.0f} KB)"
                f"</div>",
                unsafe_allow_html=True
            )

        except Exception as e:
            progress_bar.empty()
            st.error(f"❌ Report generation failed: {e}")
            import traceback
            with st.expander("Show error details"):
                st.code(traceback.format_exc())

    # ── DOWNLOAD BUTTON ──────────────────────────────────────────────────────
    if "pdf_bytes" in st.session_state:
        with dl_col:
            st.markdown("<br>", unsafe_allow_html=True)
        st.download_button(
            label=f"⬇️ Download PDF — {st.session_state['pdf_filename']}",
            data=st.session_state["pdf_bytes"],
            file_name=st.session_state["pdf_filename"],
            mime="application/pdf",
            use_container_width=True,
        )

        st.markdown("---")
        st.markdown("#### 📑 Report Contents")
        toc_items = [
            "Cover Page & Table of Contents",
            "1. Year-on-Year (YoY) Summary",
            "1B. Quarter-on-Quarter (QoQ) Summary",
            "2. Sector Overview",
            "2E. CIPE by Sector",
            "3. Employment by Category",
            "3A. MTS Breakdown",
            "3B–3C. MTS Local & Foreign",
            "3D. Salary Breakdown",
            "3E–3F. Salary Local & Foreign",
            "4A. Export Analysis",
            "4B. Raw Materials",
            "4C. Industry 4.0",
            "4D. Quality Indicators",
            "4E. Green Investment",
            "5A. State Analysis",
            "5B. LDS State",
            "5C. Top State Breakdown",
            "6. Country Analysis",
            "7. Top 10 Projects by Investment",
        ]
        cols = st.columns(2)
        for i, item in enumerate(toc_items):
            with cols[i % 2]:
                st.markdown(f"- {item}")
