"""
MIDA Manufacturing Investment Report Generator
Run: python mida_report.py
"""

import pandas as pd
import numpy as np
import os, sys, datetime, warnings, pickle
warnings.filterwarnings('ignore')

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, Flowable, Image as RLImage
)
from reportlab.platypus.tableofcontents import TableOfContents

# ── TOC ENTRY FLOWABLE ───────────────────────────────────────────────────────
_toc_ref = [None]  # holds the active TableOfContents object

class TocEntry(Flowable):
    """Zero-height marker that registers a TOC entry on the current page."""
    def __init__(self, level, text):
        Flowable.__init__(self)
        self.level = level
        self.text  = text
        self.width = self.height = 0
    def wrap(self, *args): return 0, 0
    def draw(self):
        key = f'te_{id(self)}'
        self.canv.bookmarkPage(key)
        if _toc_ref[0] is not None:
            _toc_ref[0].notify('TOCEntry', (self.level, self.text, self.canv._pageNumber, key))

# ── COLOURS ──────────────────────────────────────────────────────────────────
CB    = colors.HexColor('#003087')
CLB   = colors.HexColor('#BDD7EE')
CORA  = colors.HexColor('#F4B942')
CTOT  = colors.HexColor('#D6E4F0')
CGRAY = colors.HexColor('#CCCCCC')
CRED  = colors.HexColor('#C0392B')
CGRN  = colors.HexColor('#1E8449')
CW    = colors.white

LW  = landscape(A4)[0]
MAR = 1.4 * cm
TW  = LW - 2 * MAR

# ── COLUMN NAMES ─────────────────────────────────────────────────────────────
CD    = 'Date Approved'
CY    = 'Year of Approval'
CST   = 'Status'
CSEC  = 'Main Sector'
CDIV  = 'Division'
CSCTR = 'Sector'
CSUB  = 'Sub-Sector'
COWN  = 'Ownership'
CEXP  = 'Export (%)'
CVA   = 'Value Added (%)'
CRML  = 'Raw Materials and Components Local (%)'
CRMI  = 'Raw Materials and Components Import (%)'
CPROD = 'Production Value (RM)'
CLE   = 'Local Employment'
CFE   = 'Foreign Employment'
CTE   = 'Total Employment'
CDRM  = 'Domestic Investment\n(RM)'
CFRM  = 'Foreign Investment\n(RM)'
CTRM  = 'Total\nInvestment\n(RM)'
CCNT  = 'Ultimate Country'
CSTA  = 'State'
CI40  = 'Industry 4.0 Pillars'
CNSS  = 'NSS'
CEV   = 'EV'
CGRNI = 'Green Investment'
CHAL  = 'Halal'
CFIA  = 'FIAF Project'
CHIP  = 'High Impact Project'
CKB   = 'Knowledge Based Project'
CBIO  = 'Biomass Project'
CMGL  = 'Managerial (Local)'
CMGF  = 'Managerial (Foreign)'
CMGT  = 'Managerial (Total)'
CPTL  = 'Professionals/ Technical & Supervisory (Local)'
CPTF  = 'Professionals/ Technical & Supervisory (Foreign)'
CPTT  = 'Professionals/ Technical & Supervisory (Total)'
CCKL  = 'Craft Skills (Local)'
CCKF  = 'Craft Skills (Foreign)'
CCKT  = 'Craft Skills (Total)'
CSCLL = 'Sales, Clerical & Others (Local)'
CSCLF = 'Sales, Clerical & Others (Foreign)'
CSCLT = 'Sales, Clerical & Others (Total)'
CPML  = 'Plant & Machine Operators & Assemblers (Local)'
CPMF  = 'Plant & Machine Operators & Assemblers (Foreign)'
CPMT  = 'Plant & Machine Operators & Assemblers (Total)'
CELML = 'Elementary Workers (Local)'
CELMF = 'Elementary Workers (Foreign)'
CELMT = 'Elementary Workers (Total)'

CNAM  = 'Name of Company'
CPACT = 'Product/Activity'
CLOC  = 'Location'

SAL = [
    ('<RM3,000',      'RM < 3,000 (Total)',           'RM < 3,000 (Local)',           'RM < 3,000 (Foreign)'),
    ('RM3,000-4,999', 'RM3,000 - < RM5,000 (Total)', 'RM3,000 - < RM5,000 (Local)', 'RM3,000 - < RM5,000 (Foreign)'),
    ('RM5,000-9,999', 'RM5,000 - < RM10,000 (Total)','RM5,000 - < RM10,000 (Local)','RM5,000 - < RM10,000 (Foreign)'),
    ('>=RM10,000',    'RM10,000 & Above (Total)',     'RM10,000 & Above (Local)',     'RM10,000 & Above (Foreign)'),
]

I40P = [
    'Cybersecurity','Autonomous Robot','Internet of Things (IoT)',
    'Artificial Intelligence','Cloud Computing','System Integration',
    'Advanced Materials','Automation','Big Data Analytics','Augmented Reality'
]

PERIODS = {
    '1': ('Jan-Mar (Q1)',    3),
    '2': ('Jan-Jun (H1)',    6),
    '3': ('Jan-Sep (Q3)',    9),
    '4': ('Jan-Dec (Full)', 12),
}

CGRNI_ALT = 'Green Investment Strategy (GIS)'   # alternate name in newer files

NEED = [
    CD, CY, CST, CSEC, CDIV, CSCTR, CSUB, COWN,
    CEXP, CVA, CRML, CRMI, CPROD,
    CLE, CFE, CTE, CDRM, CFRM, CTRM,
    CCNT, CSTA, CI40,
    CNSS, CEV, CGRNI, CGRNI_ALT, CHAL, CFIA, CHIP, CKB, CBIO,
    CMGL, CMGF, CMGT, CPTL, CPTF, CPTT, CCKL, CCKF, CCKT,
    CSCLL, CSCLF, CSCLT, CPML, CPMF, CPMT, CELML, CELMF, CELMT,
    CNAM, CPACT, CLOC,
] + [b[1] for b in SAL] + [b[2] for b in SAL] + [b[3] for b in SAL]

# ── FORMATTERS ───────────────────────────────────────────────────────────────
def fn(v, d=0):
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))): return '-'
    return f"{v:,.{d}f}"

def fp(v, d=1):
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))): return '-'
    return f"{v:.{d}f}%"

def fb(v):    return f"{v/1e9:.1f}"
def fm(v):    return f"{v/1e6:.1f}"
def sd(a, b): return a / b if b else 0

def fmt_rm(v):
    if abs(v) >= 1e9: return f"RM {v/1e9:,.1f} bil"
    if abs(v) >= 1e6: return f"RM {v/1e6:,.1f} mil"
    return f"RM {v:,.0f}"

def yoy_str(c, p):
    """Plain-text YoY for stat lines; use yoy_cell() for table cells."""
    if p == 0: return '+N/A' if c > 0 else '-'
    v = (c - p) / abs(p) * 100
    return f"+{v:.1f}%" if v >= 0 else f"{v:.1f}%"

# ── DATA LOADER ───────────────────────────────────────────────────────────────
def load_excel(path):
    cache = path + '.cache9.pkl'
    mtime = os.path.getmtime(path)
    if os.path.exists(cache):
        try:
            with open(cache, 'rb') as f:
                d = pickle.load(f)
            if d.get('mtime') == mtime:
                print('  Loading from cache...')
                return d['df']
        except Exception:
            pass

    print('  Reading Excel (first time — will cache for future runs)...')
    xl = pd.ExcelFile(path, engine='calamine')
    sheet = 'All' if 'All' in xl.sheet_names else xl.sheet_names[0]
    print(f'  Sheet: {sheet}')

    # Auto-detect header row by scanning first 15 rows for 'Date Approved'
    raw = xl.parse(sheet, header=None, nrows=15)
    header_row = 4  # fallback default
    for i, row in raw.iterrows():
        if any(str(v).strip() == 'Date Approved' for v in row.values):
            header_row = i
            break
    print(f'  Header at Excel row {header_row + 1}')
    df = xl.parse(sheet, header=header_row, usecols=lambda c: c in NEED)

    df[CD] = pd.to_datetime(df[CD], errors='coerce')
    df['_m'] = df[CD].dt.month
    df['_y'] = df[CD].dt.year

    num_cols = [
        CTE, CLE, CFE, CDRM, CFRM, CTRM,
        CMGL, CMGF, CMGT, CPTL, CPTF, CPTT, CCKL, CCKF, CCKT,
        CEXP, CVA, CRML, CRMI, CPROD,
    ] + [b[1] for b in SAL] + [b[2] for b in SAL] + [b[3] for b in SAL]

    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)

    # Rename alternate Green column name to canonical CGRNI
    if CGRNI not in df.columns and CGRNI_ALT in df.columns:
        df = df.rename(columns={CGRNI_ALT: CGRNI})

    # Save raw category text for EV and Green (for breakdown tables)
    df['_ev_cat']  = df[CEV].fillna('-').astype(str).str.strip()  if CEV  in df.columns else '-'
    df['_gis_cat'] = df[CGRNI].fillna('-').astype(str).str.strip() if CGRNI in df.columns else '-'

    # Simple flag indicators: *, X, YES, Y, 1, TRUE
    yes_vals = {'YES', 'Y', '1', 'TRUE', 'X', '*'}
    no_vals  = {'-', '', 'NA', 'N/A', 'NO', 'NONE', 'NAN', 'FALSE', '0'}
    for c in [CNSS, CHAL, CFIA, CHIP, CKB, CBIO]:
        if c in df.columns:
            df[c] = df[c].apply(lambda x: str(x).strip().upper() in yes_vals if pd.notna(x) else False)
        else:
            df[c] = False

    # Category indicators: any non-empty, non-dash text = True (EV type, GIS type)
    for c in [CEV, CGRNI]:
        if c in df.columns:
            df[c] = df[c].apply(lambda x: pd.notna(x) and str(x).strip().upper() not in no_vals)
        else:
            df[c] = False

    df['_new'] = df[CST].isin(['New', 'New (Regularisation)'])
    df['_div'] = df[CST] == 'Expansion/Diversification/Extension'
    df['_for'] = df[COWN].isin(['Wholly Foreign', 'Foreign Majority', 'Joint Venture 50/50'])

    if CI40 in df.columns:
        for p in I40P:
            df[f'_p_{p}'] = df[CI40].fillna('').str.contains(p, case=False, na=False)
        df['_i40'] = df[[f'_p_{p}' for p in I40P]].any(axis=1)
    else:
        for p in I40P:
            df[f'_p_{p}'] = False
        df['_i40'] = False

    try:
        with open(cache, 'wb') as f:
            pickle.dump({'mtime': mtime, 'df': df}, f)
        print('  Cached. Next run will be faster.')
    except Exception:
        pass

    return df

def filt(df, year, months):
    m = df[CSEC] == 'Manufacturing'
    c = df[m & (df['_y'] == year)     & (df['_m'] <= months)].copy()
    p = df[m & (df['_y'] == year - 1) & (df['_m'] <= months)].copy()
    return c, p

def filt_qoq(df, year, months):
    """Return (prev_period_label, prev_df) for the period immediately preceding current."""
    m = df[CSEC] == 'Manufacturing'
    mfg = df[m]
    if months == 3:
        prev_pl = 'Oct-Dec (Q4)'
        prev = mfg[(mfg['_y'] == year-1) & (mfg['_m'] >= 10)].copy()
    elif months == 6:
        prev_pl = 'Jul-Dec (H2)'
        prev = mfg[(mfg['_y'] == year-1) & (mfg['_m'] >= 7)].copy()
    elif months == 9:
        prev_pl = 'Apr-Dec'
        prev = mfg[(mfg['_y'] == year-1) & (mfg['_m'] >= 4)].copy()
    else:
        prev_pl = 'Jan-Dec (Full)'
        prev = mfg[mfg['_y'] == year-1].copy()
    return prev_pl, prev

# ── STYLES ────────────────────────────────────────────────────────────────────
SP    = ParagraphStyle
STAT  = SP('stat',  fontSize=9,   textColor=CB,  fontName='Helvetica-Bold',  leading=12)
TITLE = SP('title', fontSize=20,  textColor=CW,  fontName='Helvetica-Bold',  alignment=TA_CENTER, leading=28)
SUB   = SP('sub',   fontSize=13,  textColor=colors.HexColor('#CCE0FF'), fontName='Helvetica', alignment=TA_CENTER, leading=18)
WRAP    = SP('wrap',   fontSize=8.5, fontName='Helvetica',      leading=11)
WRAP_C  = SP('wrap_c', fontSize=8.5, fontName='Helvetica', leading=11, alignment=TA_CENTER)
WRAPHDR = SP('wraphdr',fontSize=8.5, fontName='Helvetica-Bold', textColor=CW, leading=11)
WRAPHDR_C = SP('wraphdr_c', fontSize=8.5, fontName='Helvetica-Bold', textColor=CW, leading=11, alignment=TA_CENTER)
WRAP_UP = SP('wrapup', fontSize=8.5, fontName='Helvetica-Bold', textColor=CGRN, leading=11, alignment=TA_CENTER)
WRAP_DN = SP('wrapdn', fontSize=8.5, fontName='Helvetica-Bold', textColor=CRED, leading=11, alignment=TA_CENTER)

def _esc(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def pw(text):
    return Paragraph(_esc(text), WRAP)

def ph(text):
    return Paragraph(_esc(text), WRAPHDR)

def _color_yoy(s):
    """Wrap data cell as Paragraph; colour if it looks like a +/- YoY value."""
    if isinstance(s, str):
        if len(s) > 1 and s[0] == '+':
            return Paragraph(_esc(s), WRAP_UP)
        if len(s) > 1 and s[0] == '-' and (s[1].isdigit() or s[1] == 'N'):
            return Paragraph(_esc(s), WRAP_DN)
        return Paragraph(_esc(s), WRAP_C)
    return s

def stat_line(text):
    return Paragraph(text, STAT)

def sec_bar(text):
    t = Table([[Paragraph(text, SP('sb', fontSize=10, textColor=CW, fontName='Helvetica-Bold', leading=14))]],
              colWidths=[TW])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), CB),
        ('TOPPADDING', (0,0), (-1,-1), 5), ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
    ]))
    return t

# ── TABLE BUILDER ─────────────────────────────────────────────────────────────
BASE_TS = [
    ('BACKGROUND',    (0,0), (-1,0),  CB),
    ('TEXTCOLOR',     (0,0), (-1,0),  CW),
    ('FONTNAME',      (0,0), (-1,0),  'Helvetica-Bold'),
    ('FONTSIZE',      (0,0), (-1,-1), 8.5),
    ('ALIGN',         (0,0), (-1,-1), 'CENTER'),
    ('ALIGN',         (0,1), (0,-1),  'LEFT'),
    ('VALIGN',        (0,0), (-1,-1), 'TOP'),
    ('FONTNAME',      (0,1), (-1,-2), 'Helvetica'),
    ('ROWBACKGROUNDS',(0,1), (-1,-2), [CW, CLB]),
    ('BACKGROUND',    (0,-1),(-1,-1), CTOT),
    ('FONTNAME',      (0,-1),(-1,-1), 'Helvetica-Bold'),
    ('LINEABOVE',     (0,-1),(-1,-1), 0.8, CB),
    ('GRID',          (0,0), (-1,-1), 0.3, CGRAY),
    ('TOPPADDING',    (0,0), (-1,-1), 3),
    ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ('LEFTPADDING',   (0,0), (-1,-1), 4),
    ('RIGHTPADDING',  (0,0), (-1,-1), 4),
]

def dtable(rows, cw, orange_cells=None):
    wrapped = []
    for ri, row in enumerate(rows):
        new_row = list(row)
        for ci, cell in enumerate(new_row):
            if not isinstance(cell, str):
                continue
            if ri == 0 and ci == 0:
                new_row[ci] = ph(cell)
            elif ri == 0 and ci > 0:
                new_row[ci] = Paragraph(_esc(cell), WRAPHDR_C)
            elif ri > 0 and ci == 0:
                new_row[ci] = pw(cell)
            elif ri > 0 and ci > 0:
                new_row[ci] = _color_yoy(cell)
        wrapped.append(new_row)
    t = Table(wrapped, colWidths=cw, repeatRows=1)
    style = list(BASE_TS)
    if orange_cells:
        for (ri, ci) in orange_cells:
            style += [
                ('BACKGROUND', (ci,ri), (ci,ri), CORA),
                ('FONTNAME',   (ci,ri), (ci,ri), 'Helvetica-Bold'),
            ]
    t.setStyle(TableStyle(style))
    return t

def _cw(*vals):
    s = sum(vals)
    return [v / s * TW for v in vals]

def footer_fn(year, pl):
    def f(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 6.5)
        canvas.setFillColor(colors.HexColor('#888888'))
        canvas.drawCentredString(LW/2, 1.0*cm,
            f'MIDA Manufacturing Investment Report  |  {pl}  {year}  |  Page {doc.page}  |  CONFIDENTIAL')
        canvas.setStrokeColor(CGRAY); canvas.setLineWidth(0.4)
        canvas.line(MAR, 1.3*cm, LW-MAR, 1.3*cm)
        canvas.restoreState()
    return f

# ── SECTIONS ──────────────────────────────────────────────────────────────────
def sec_cover(story, year, pl):
    story.append(Spacer(1, 3.5*cm))
    c = Table([
        [Paragraph('MALAYSIA INVESTMENT DEVELOPMENT AUTHORITY', SUB)],
        [Paragraph('Manufacturing Sector Investment Performance Report', TITLE)],
        [Paragraph(f'{pl}  |  Year {year}', SUB)],
        [Paragraph(f'Year-on-Year Comparison: {year} vs {year-1}', SUB)],
        [Paragraph(f'Prepared: {datetime.datetime.now().strftime("%d %B %Y")}  |  CONFIDENTIAL', SUB)],
    ], colWidths=[TW])
    c.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (-1,-1), CB),
        ('TOPPADDING',    (0,0), (-1,-1), 22),
        ('BOTTOMPADDING', (0,0), (-1,-1), 22),
        ('LEFTPADDING',   (0,0), (-1,-1), 8),
        ('RIGHTPADDING',  (0,0), (-1,-1), 8),
    ]))
    story.append(c)


def sec_toc(story, year, pl):
    story.append(PageBreak())
    story.append(sec_bar('TABLE OF CONTENTS'))
    story.append(Spacer(1, 0.5*cm))

    toc = TableOfContents()
    _toc_ref[0] = toc
    toc.dotsMinLevel = 0
    toc.levelStyles = [
        ParagraphStyle('toc_l0', fontName='Helvetica-Bold', fontSize=9, leading=18,
                       leftIndent=0, spaceAfter=1, spaceBefore=2),
        ParagraphStyle('toc_l1', fontName='Helvetica', fontSize=8.5, leading=14,
                       leftIndent=20, spaceAfter=0,
                       textColor=colors.HexColor('#444444')),
    ]
    story.append(toc)


def sec_yoy(story, cur, prev, year, pl):
    story.append(PageBreak())
    story.append(TocEntry(0, f'1.  Year-on-Year Summary  —  {pl} {year} vs {year-1}'))
    story.append(sec_bar(f'1.  YEAR-ON-YEAR SUMMARY  —  {pl}  ({year} vs {year-1})'))
    story.append(Spacer(1, 0.15*cm))

    ic = cur[CTRM].sum();  ip = prev[CTRM].sum()
    ec = cur[CTE].sum();   ep = prev[CTE].sum()
    lc = cur[CLE].sum();   lp = prev[CLE].sum()
    fc = cur[CFE].sum();   fp_ = prev[CFE].sum()
    dc = cur[CDRM].sum();  dp = prev[CDRM].sum()
    fc2= cur[CFRM].sum();  fp2= prev[CFRM].sum()
    nc = cur['_new'].sum();  np_ = prev['_new'].sum()
    dvc= cur['_div'].sum();  dvp = prev['_div'].sum()
    mtc= cur[[CMGT,CPTT,CCKT]].sum().sum()
    mtp= prev[[CMGT,CPTT,CCKT]].sum().sum()
    s5c= sum(cur[b[1]].sum() for b in SAL[2:])
    s5p= sum(prev[b[1]].sum() for b in SAL[2:])
    mtlc= cur[[CMGL,CPTL,CCKL]].sum().sum()
    mtlp= prev[[CMGL,CPTL,CCKL]].sum().sum()
    s5lc= sum(cur[b[2]].sum() for b in SAL[2:])
    s5lp= sum(prev[b[2]].sum() for b in SAL[2:])

    GSEP_STYLE = SP('gsep', fontSize=8.5, fontName='Helvetica-Bold', textColor=CW, leading=11)
    CLB2 = colors.HexColor('#D6E4F0')

    sections = [
        ('PROJECTS', [
            ['Total Projects Approved',        fn(len(cur)),              fn(len(prev)),             yoy_str(len(cur), len(prev))],
            ['  – New (incl. Regularisation)', fn(nc),                    fn(np_),                   yoy_str(nc, np_)],
            ['  – Diversification/Expansion',  fn(dvc),                   fn(dvp),                   yoy_str(dvc, dvp)],
        ]),
        ('INVESTMENT', [
            ['Total Investment',               fmt_rm(ic),                fmt_rm(ip),                yoy_str(ic, ip)],
            ['  – Domestic Investment',        f"{fmt_rm(dc)} ({fp(sd(dc,ic)*100)})",    f"{fmt_rm(dp)} ({fp(sd(dp,ip)*100)})",    yoy_str(dc,  dp)],
            ['  – Foreign Investment',         f"{fmt_rm(fc2)} ({fp(sd(fc2,ic)*100)})", f"{fmt_rm(fp2)} ({fp(sd(fp2,ip)*100)})", yoy_str(fc2, fp2)],
        ]),
        ('EMPLOYMENT', [
            ['Total\nEmployment',               fn(ec),                                              fn(ep),                                              yoy_str(ec, ep)],
            ['  – Local Employment',           f"{fn(lc)} ({fp(sd(lc,ec)*100)})",                   f"{fn(lp)} ({fp(sd(lp,ep)*100)})",                   yoy_str(lc, lp)],
            ['  – Foreign Employment',         f"{fn(fc)} ({fp(sd(fc,ec)*100)})",                   f"{fn(fp_)} ({fp(sd(fp_,ep)*100)})",                 yoy_str(fc, fp_)],
            ['MTS Workers',                    fn(mtc),                   fn(mtp),                   yoy_str(mtc, mtp)],
            ['MTS Ratio',                      fp(sd(mtc,ec)*100),        fp(sd(mtp,ep)*100),        yoy_str(sd(mtc,ec), sd(mtp,ep))],
            ['Workers ≥ RM5,000',             fn(s5c),                   fn(s5p),                   yoy_str(s5c, s5p)],
            ['≥ RM5K Ratio',                  fp(sd(s5c,ec)*100),        fp(sd(s5p,ep)*100),        yoy_str(sd(s5c,ec), sd(s5p,ep))],
            ['  – Local MTS Workers',          fn(mtlc),                  fn(mtlp),                  yoy_str(mtlc, mtlp)],
            ['  – Local MTS Ratio',            fp(sd(mtlc,lc)*100),       fp(sd(mtlp,lp)*100),       yoy_str(sd(mtlc,lc), sd(mtlp,lp))],
            ['  – Local Workers ≥ RM5,000',   fn(s5lc),                  fn(s5lp),                  yoy_str(s5lc, s5lp)],
            ['  – Local ≥ RM5K Ratio',        fp(sd(s5lc,lc)*100),       fp(sd(s5lp,lp)*100),       yoy_str(sd(s5lc,lc), sd(s5lp,lp))],
        ]),
        ('PRODUCTIVITY & QUALITY INDICATORS', [
            ['CIPE (Capital Inv. / Worker)',   fmt_rm(sd(ic,ec)),         fmt_rm(sd(ip,ep)),         yoy_str(sd(ic,ec), sd(ip,ep))],
            ['Export-Oriented (≥ 80%)',        fn((cur[CEXP]>=80).sum()), fn((prev[CEXP]>=80).sum()),yoy_str((cur[CEXP]>=80).sum(),(prev[CEXP]>=80).sum())],
            ['I4.0 Adopters',                  fn(cur['_i40'].sum()),     fn(prev['_i40'].sum()),    yoy_str(cur['_i40'].sum(), prev['_i40'].sum())],
        ]),
    ]

    hdr = ['Indicator', f'{year}', f'{year-1}', 'YoY Change']
    rows = [hdr]
    sep_rows = []

    for group_name, data_rows in sections:
        sep_rows.append(len(rows))
        rows.append([group_name, '', '', ''])
        rows.extend(data_rows)

    cw = _cw(7, 3.5, 3.5, 3)

    wrapped = []
    for ri, row in enumerate(rows):
        new_row = list(row)
        if new_row and isinstance(new_row[0], str):
            if ri == 0:
                new_row[0] = ph(new_row[0])
            elif ri in sep_rows:
                new_row[0] = Paragraph(new_row[0], GSEP_STYLE)
            else:
                new_row[0] = pw(new_row[0])
        # Colour the YoY column
        if ri > 0 and ri not in sep_rows and len(new_row) > 3:
            new_row[3] = _color_yoy(new_row[3])
        wrapped.append(new_row)

    t = Table(wrapped, colWidths=cw, repeatRows=1)
    style = [
        ('BACKGROUND',    (0,0),  (-1,0),  CB),
        ('TEXTCOLOR',     (0,0),  (-1,0),  CW),
        ('FONTNAME',      (0,0),  (-1,0),  'Helvetica-Bold'),
        ('FONTSIZE',      (0,0),  (-1,-1), 8.5),
        ('ALIGN',         (0,0),  (-1,-1), 'CENTER'),
        ('ALIGN',         (0,1),  (0,-1),  'LEFT'),
        ('VALIGN',        (0,0),  (-1,-1), 'TOP'),
        ('FONTNAME',      (0,1),  (-1,-1), 'Helvetica'),
        ('ROWBACKGROUNDS',(0,1),  (-1,-1), [CW, CLB2]),
        ('GRID',          (0,0),  (-1,-1), 0.3, CGRAY),
        ('TOPPADDING',    (0,0),  (-1,-1), 3),
        ('BOTTOMPADDING', (0,0),  (-1,-1), 3),
        ('LEFTPADDING',   (0,0),  (-1,-1), 4),
        ('RIGHTPADDING',  (0,0),  (-1,-1), 4),
    ]
    for ri in sep_rows:
        style += [
            ('BACKGROUND',    (0,ri),  (-1,ri), CB),
            ('TEXTCOLOR',     (0,ri),  (-1,ri), CW),
            ('FONTNAME',      (0,ri),  (-1,ri), 'Helvetica-Bold'),
            ('SPAN',          (0,ri),  (-1,ri)),
            ('TOPPADDING',    (0,ri),  (-1,ri), 4),
            ('BOTTOMPADDING', (0,ri),  (-1,ri), 4),
            ('LEFTPADDING',   (0,ri),  (-1,ri), 8),
        ]
    t.setStyle(TableStyle(style))
    story.append(t)


def sec_qoq(story, cur, prev_qoq, year, pl, prev_pl):
    story.append(PageBreak())
    story.append(TocEntry(0, f'1B.  Quarter-on-Quarter Summary  —  {pl} {year}'))
    _bar = sec_bar(f'1B.  QUARTER-ON-QUARTER SUMMARY  —  {pl} {year} vs {prev_pl} {year-1}')
    _sp  = Spacer(1, 0.15*cm)

    ic = cur[CTRM].sum();   ip = prev_qoq[CTRM].sum()
    ec = cur[CTE].sum();    ep = prev_qoq[CTE].sum()
    lc = cur[CLE].sum();    lp = prev_qoq[CLE].sum()
    fc = cur[CFE].sum();    fp_ = prev_qoq[CFE].sum()
    dc = cur[CDRM].sum();   dp = prev_qoq[CDRM].sum()
    fc2= cur[CFRM].sum();   fp2= prev_qoq[CFRM].sum()
    nc = cur['_new'].sum(); np_ = prev_qoq['_new'].sum()
    dvc= cur['_div'].sum(); dvp = prev_qoq['_div'].sum()
    mtc= cur[[CMGT,CPTT,CCKT]].sum().sum()
    mtp= prev_qoq[[CMGT,CPTT,CCKT]].sum().sum()
    s5c= sum(cur[b[1]].sum() for b in SAL[2:])
    s5p= sum(prev_qoq[b[1]].sum() for b in SAL[2:])
    mtlc= cur[[CMGL,CPTL,CCKL]].sum().sum()
    mtlp= prev_qoq[[CMGL,CPTL,CCKL]].sum().sum()
    s5lc= sum(cur[b[2]].sum() for b in SAL[2:])
    s5lp= sum(prev_qoq[b[2]].sum() for b in SAL[2:])

    GSEP_STYLE = SP('gsep_qoq', fontSize=8.5, fontName='Helvetica-Bold', textColor=CW, leading=11)

    sections = [
        ('PROJECTS', [
            ['Total Projects Approved',        fn(len(cur)),              fn(len(prev_qoq)),              yoy_str(len(cur), len(prev_qoq))],
            ['  – New (incl. Regularisation)', fn(nc),                    fn(np_),                        yoy_str(nc, np_)],
            ['  – Diversification/Expansion',  fn(dvc),                   fn(dvp),                        yoy_str(dvc, dvp)],
        ]),
        ('INVESTMENT', [
            ['Total Investment',               fmt_rm(ic),                fmt_rm(ip),                     yoy_str(ic, ip)],
            ['  – Domestic Investment',        f"{fmt_rm(dc)} ({fp(sd(dc,ic)*100)})",    f"{fmt_rm(dp)} ({fp(sd(dp,ip)*100)})",    yoy_str(dc,  dp)],
            ['  – Foreign Investment',         f"{fmt_rm(fc2)} ({fp(sd(fc2,ic)*100)})", f"{fmt_rm(fp2)} ({fp(sd(fp2,ip)*100)})", yoy_str(fc2, fp2)],
        ]),
        ('EMPLOYMENT', [
            ['Total\nEmployment',               fn(ec),                                              fn(ep),                                              yoy_str(ec, ep)],
            ['  – Local Employment',           f"{fn(lc)} ({fp(sd(lc,ec)*100)})",                   f"{fn(lp)} ({fp(sd(lp,ep)*100)})",                   yoy_str(lc, lp)],
            ['  – Foreign Employment',         f"{fn(fc)} ({fp(sd(fc,ec)*100)})",                   f"{fn(fp_)} ({fp(sd(fp_,ep)*100)})",                 yoy_str(fc, fp_)],
            ['MTS Workers',                    fn(mtc),                   fn(mtp),                        yoy_str(mtc, mtp)],
            ['MTS Ratio',                      fp(sd(mtc,ec)*100),        fp(sd(mtp,ep)*100),             yoy_str(sd(mtc,ec), sd(mtp,ep))],
            ['Workers ≥ RM5,000',             fn(s5c),                   fn(s5p),                        yoy_str(s5c, s5p)],
            ['≥ RM5K Ratio',                  fp(sd(s5c,ec)*100),        fp(sd(s5p,ep)*100),             yoy_str(sd(s5c,ec), sd(s5p,ep))],
            ['  – Local MTS Workers',          fn(mtlc),                  fn(mtlp),                       yoy_str(mtlc, mtlp)],
            ['  – Local MTS Ratio',            fp(sd(mtlc,lc)*100),       fp(sd(mtlp,lp)*100),            yoy_str(sd(mtlc,lc), sd(mtlp,lp))],
            ['  – Local Workers ≥ RM5,000',   fn(s5lc),                  fn(s5lp),                       yoy_str(s5lc, s5lp)],
            ['  – Local ≥ RM5K Ratio',        fp(sd(s5lc,lc)*100),       fp(sd(s5lp,lp)*100),            yoy_str(sd(s5lc,lc), sd(s5lp,lp))],
        ]),
        ('PRODUCTIVITY & QUALITY INDICATORS', [
            ['CIPE (Capital Inv. / Worker)',   fmt_rm(sd(ic,ec)),         fmt_rm(sd(ip,ep)),              yoy_str(sd(ic,ec), sd(ip,ep))],
            ['Export-Oriented (≥ 80%)',        fn((cur[CEXP]>=80).sum()), fn((prev_qoq[CEXP]>=80).sum()),yoy_str((cur[CEXP]>=80).sum(),(prev_qoq[CEXP]>=80).sum())],
            ['I4.0 Adopters',                  fn(cur['_i40'].sum()),     fn(prev_qoq['_i40'].sum()),     yoy_str(cur['_i40'].sum(), prev_qoq['_i40'].sum())],
        ]),
    ]

    hdr = ['Indicator', f'{pl}\n{year}', f'{prev_pl}\n{year-1}', 'QoQ Change']
    rows = [hdr]
    sep_rows = []

    for group_name, data_rows in sections:
        sep_rows.append(len(rows))
        rows.append([group_name, '', '', ''])
        rows.extend(data_rows)

    cw = _cw(7, 3.5, 3.5, 3)

    wrapped = []
    for ri, row in enumerate(rows):
        new_row = list(row)
        if new_row and isinstance(new_row[0], str):
            if ri == 0:
                new_row[0] = ph(new_row[0])
            elif ri in sep_rows:
                new_row[0] = Paragraph(new_row[0], GSEP_STYLE)
            else:
                new_row[0] = pw(new_row[0])
        if ri > 0 and ri not in sep_rows and len(new_row) > 3:
            new_row[3] = _color_yoy(new_row[3])
        wrapped.append(new_row)

    t = Table(wrapped, colWidths=cw, repeatRows=1)
    style = [
        ('BACKGROUND',    (0,0),  (-1,0),  CB),
        ('TEXTCOLOR',     (0,0),  (-1,0),  CW),
        ('FONTNAME',      (0,0),  (-1,0),  'Helvetica-Bold'),
        ('FONTSIZE',      (0,0),  (-1,-1), 8.5),
        ('ALIGN',         (0,0),  (-1,-1), 'CENTER'),
        ('ALIGN',         (0,1),  (0,-1),  'LEFT'),
        ('VALIGN',        (0,0),  (-1,-1), 'TOP'),
        ('FONTNAME',      (0,1),  (-1,-1), 'Helvetica'),
        ('ROWBACKGROUNDS',(0,1),  (-1,-1), [CW, CTOT]),
        ('GRID',          (0,0),  (-1,-1), 0.3, CGRAY),
        ('TOPPADDING',    (0,0),  (-1,-1), 2),
        ('BOTTOMPADDING', (0,0),  (-1,-1), 2),
        ('LEFTPADDING',   (0,0),  (-1,-1), 4),
        ('RIGHTPADDING',  (0,0),  (-1,-1), 4),
    ]
    for ri in sep_rows:
        style += [
            ('BACKGROUND',    (0,ri),  (-1,ri), CB),
            ('TEXTCOLOR',     (0,ri),  (-1,ri), CW),
            ('FONTNAME',      (0,ri),  (-1,ri), 'Helvetica-Bold'),
            ('SPAN',          (0,ri),  (-1,ri)),
            ('TOPPADDING',    (0,ri),  (-1,ri), 3),
            ('BOTTOMPADDING', (0,ri),  (-1,ri), 3),
            ('LEFTPADDING',   (0,ri),  (-1,ri), 8),
        ]
    t.setStyle(TableStyle(style))
    story.append(KeepTogether([_bar, _sp, t]))


def _subsector_groups(cur):
    """Return list of (main_sector, division, sub_sector, df_slice)."""
    # Group hierarchy: Main Sector > Division > Sub-Sector
    result = []
    for (div, sub), g in cur.groupby([CDIV, CSUB], dropna=False, sort=False):
        result.append((div, sub, g))
    return sorted(result, key=lambda x: len(x[2]), reverse=True)


def sec_overview(story, cur, prev, year, pl):
    story.append(PageBreak())
    story.append(TocEntry(0, f'2.  Sector Overview  —  {pl} {year} vs {year-1}'))
    story.append(TocEntry(1, f'2A  Projects & Investment'))
    tc = len(cur); tp = len(prev)
    ic = cur[CTRM].sum(); ip = prev[CTRM].sum()
    ec = cur[CTE].sum();  ep = prev[CTE].sum()
    e80c = (cur[CEXP]>=80).sum()
    mtc  = cur[[CMGT,CPTT,CCKT]].sum().sum()
    s5c  = sum(cur[b[1]].sum() for b in SAL[2:])

    story.append(sec_bar(f'2.  SECTOR OVERVIEW  —  {pl}  {year} vs {year-1}'))
    story.append(Spacer(1, 0.15*cm))
    story.append(stat_line(
        f"Total: {fn(tc)} projects  |  Employment: {fn(ec)}  |  Investment: RM {fb(ic)} bil  |  "
        f"Export>=80%: {fn(e80c)}  |  MTS: {fp(sd(mtc,ec))}  |  >=RM5K: {fp(sd(s5c,ec))}  |  "
        f"YoY Projects: {yoy_str(tc,tp)}  |  YoY Investment: {yoy_str(ic,ip)}  |  YoY Employment: {yoy_str(ec,ep)}"
    ))
    story.append(Spacer(1, 0.2*cm))

    def agg(df):
        return df.groupby(CSCTR, dropna=False).agg(
            proj=(CSCTR,'count'), inv=(CTRM,'sum'), dom=(CDRM,'sum'),
            for_=(CFRM,'sum'), emp=(CTE,'sum'), lemp=(CLE,'sum'), femp=(CFE,'sum'),
            va=(CVA,'mean'), prod=(CPROD,'sum')
        ).reset_index()

    g  = agg(cur)
    gp = agg(prev).rename(columns={'proj':'projp','inv':'invp','emp':'empp'})
    g  = g.merge(gp[[CSCTR,'projp','invp','empp']], on=CSCTR, how='left').fillna(0)

    g['exp80']  = cur[cur[CEXP]>=80].groupby(CSCTR, dropna=False).size().reindex(g[CSCTR]).fillna(0).values
    g['avg_exp']= cur.groupby(CSCTR, dropna=False)[CEXP].mean().reindex(g[CSCTR]).fillna(0).values
    g['mts']    = cur.groupby(CSCTR, dropna=False).apply(
                      lambda x: x[[CMGT,CPTT,CCKT]].sum().sum()).reindex(g[CSCTR]).fillna(0).values
    g['sal5']   = cur.groupby(CSCTR, dropna=False).apply(
                      lambda x: sum(x[b[1]].sum() for b in SAL[2:])).reindex(g[CSCTR]).fillna(0).values
    g = g.sort_values('inv', ascending=False)

    total_proj = g['proj'].sum() or 1
    total_inv  = g['inv'].sum()  or 1

    # ── Table 2A: Projects & Investment ──────────────────────────────────────
    story.append(stat_line(f"2A   Projects & Investment"))
    story.append(Spacer(1, 0.1*cm))

    hdr_a = ['Sector',
             f'Projects\n{year}', f'Projects\n{year-1}', 'YoY Proj',
             f'Total Investment\n(RM bil)\n{year}', f'Total Investment\n(RM bil)\n{year-1}',
             'Domestic\nInvestment (RM bil)', 'Foreign\nInvestment (RM bil)', 'YoY\nInvestment']
    rows_a = [hdr_a]
    for _, r in g.iterrows():
        proj_sh = sd(r['proj'], total_proj) * 100
        inv_sh  = sd(r['inv'],  total_inv)  * 100
        rows_a.append([
            str(r[CSCTR]),
            f"{fn(r['proj'])} ({fp(proj_sh)})",   fn(r['projp']),  yoy_str(r['proj'], r['projp']),
            f"{fb(r['inv'])} ({fp(inv_sh)})",    fb(r['invp']),   fb(r['dom']),    fb(r['for_']),    yoy_str(r['inv'], r['invp']),
        ])
    rows_a.append([
        'TOTAL',
        f"{fn(g['proj'].sum())} (100.0%)", fn(g['projp'].sum()), yoy_str(g['proj'].sum(), g['projp'].sum()),
        f"{fb(g['inv'].sum())} (100.0%)", fb(g['invp'].sum()), fb(g['dom'].sum()),   fb(g['for_'].sum()),  yoy_str(g['inv'].sum(), g['invp'].sum()),
    ])
    cw_a = _cw(5.0, 2.5, 1.8, 1.5, 2.8, 2.4, 2.0, 2.0, 1.5)
    story.append(dtable(rows_a, cw_a))

    # ── Table 2B: Employment Breakdown ───────────────────────────────────────
    story.append(PageBreak())
    story.append(TocEntry(1, f'2B  Employment by Local / Foreign'))
    story.append(sec_bar(f'2.  SECTOR OVERVIEW (CONT.)  —  Employment  |  {pl}  {year} vs {year-1}'))
    story.append(Spacer(1, 0.15*cm))
    story.append(stat_line(f"2B   Employment by Local / Foreign"))
    story.append(Spacer(1, 0.1*cm))

    g_b = g.sort_values('emp', ascending=False)

    hdr_b = ['Sector',
             f'Total Employment\n{year}', f'Total Employment\n{year-1}', 'YoY\nEmployment',
             'Local\nEmployment', 'Foreign\nEmployment',
             'MTS Workers', '>=RM5K Workers']
    rows_b = [hdr_b]
    for _, r in g_b.iterrows():
        lp_  = sd(r['lemp'], r['emp']) * 100
        fep_ = sd(r['femp'], r['emp']) * 100
        rows_b.append([
            str(r[CSCTR]),
            fn(r['emp']),   fn(r['empp']),   yoy_str(r['emp'], r['empp']),
            f"{fn(r['lemp'])} ({fp(lp_)})",
            f"{fn(r['femp'])} ({fp(fep_)})",
            f"{fn(r['mts'])} ({fp(sd(r['mts'],  r['emp'])*100)})",
            f"{fn(r['sal5'])} ({fp(sd(r['sal5'], r['emp'])*100)})",
        ])
    rows_b.append([
        'TOTAL',
        fn(g_b['emp'].sum()),   fn(g_b['empp'].sum()),   yoy_str(g_b['emp'].sum(), g_b['empp'].sum()),
        f"{fn(g_b['lemp'].sum())} ({fp(sd(g_b['lemp'].sum(), g_b['emp'].sum())*100)})",
        f"{fn(g_b['femp'].sum())} ({fp(sd(g_b['femp'].sum(), g_b['emp'].sum())*100)})",
        f"{fn(g_b['mts'].sum())} ({fp(sd(g_b['mts'].sum(),  g_b['emp'].sum())*100)})",
        f"{fn(g_b['sal5'].sum())} ({fp(sd(g_b['sal5'].sum(), g_b['emp'].sum())*100)})",
    ])
    cw_b = _cw(4.5, 2.0, 2.0, 1.5, 3.2, 3.2, 2.8, 2.8)
    story.append(dtable(rows_b, cw_b))

    # ── Overview: New vs Expansion ────────────────────────────────────────────
    story.append(PageBreak())
    story.append(Spacer(1, 0.3*cm))
    story.append(stat_line("Overview — New vs Expansion Types"))
    story.append(Spacer(1, 0.1*cm))

    _nv = cur[cur['_new']]
    _dv = cur[cur['_div']]
    _pnv = prev[prev['_new']]
    _pdv = prev[prev['_div']]
    _ov_inv  = cur[CTRM].sum()
    _ov_invp = prev[CTRM].sum()
    _ov_dom  = cur[CDRM].sum()
    _ov_for  = cur[CFRM].sum()

    def _ov_row(label, df, df_p):
        inv  = df[CTRM].sum()
        invp = df_p[CTRM].sum()
        dom  = df[CDRM].sum()
        for_ = df[CFRM].sum()
        return [label, fn(len(df)), fn(df[CTE].sum()),
                fb(inv), fb(invp), yoy_str(inv, invp), fb(dom), fp(sd(dom, _ov_dom)*100), fb(for_), fp(sd(for_, _ov_for)*100)]

    rows_ov = [
        ['Type', 'No. of\nProjects', 'Total\nEmployment',
         f'Total Investment\n(RM bil) {year}', f'Total Investment\n(RM bil) {year-1}', 'YoY\nInvestment',
         'Domestic\nInvestment (RM bil)', 'Domestic %',
         'Foreign\nInvestment (RM bil)', 'Foreign %'],
        _ov_row('New (incl. Regularisation)', _nv, _pnv),
        _ov_row('Expansion / Diversification', _dv, _pdv),
        ['TOTAL', fn(len(cur)), fn(cur[CTE].sum()),
         fb(_ov_inv), fb(_ov_invp), yoy_str(_ov_inv, _ov_invp), fb(_ov_dom), fp(100.0), fb(_ov_for), fp(100.0)],
    ]
    story.append(dtable(rows_ov, _cw(4.5, 2.0, 2.5, 2.5, 2.5, 1.6, 2.0, 1.3, 2.0, 1.3)))
    story.append(Spacer(1, 0.5*cm))

    # ── Table 2C: New Projects by Sector ─────────────────────────────────────
    story.append(TocEntry(1, f'2C  New Projects by Sector'))
    story.append(stat_line(f"2C   New Projects by Sector"))
    story.append(Spacer(1, 0.1*cm))

    cur_new  = cur[cur['_new']].copy()
    prev_new = prev[prev['_new']].copy()

    def _agg_type(df):
        return df.groupby(CSCTR, dropna=False).agg(
            proj=(CSCTR,'count'), emp=(CTE,'sum'), inv=(CTRM,'sum')
        ).reset_index()

    gn  = _agg_type(cur_new)
    gnp = _agg_type(prev_new).rename(columns={'proj':'projp','emp':'empp','inv':'invp'})
    gn  = gn.merge(gnp, on=CSCTR, how='outer').fillna(0).sort_values('inv', ascending=False)
    gn['dom']  = cur_new.groupby(CSCTR, dropna=False)[CDRM].sum().reindex(gn[CSCTR]).fillna(0).values
    gn['for_'] = cur_new.groupby(CSCTR, dropna=False)[CFRM].sum().reindex(gn[CSCTR]).fillna(0).values

    _dom_n = gn['dom'].sum()
    _for_n = gn['for_'].sum()

    hdr_c = ['Sector', 'No. of\nProjects', 'Total\nEmployment',
             f'Total Investment\n(RM bil) {year}', f'Total Investment\n(RM bil) {year-1}', 'YoY\nInvestment',
             'Domestic\nInvestment (RM bil)', 'Domestic %',
             'Foreign\nInvestment (RM bil)', 'Foreign %']
    rows_c = [hdr_c]
    for _, r in gn.iterrows():
        rows_c.append([str(r[CSCTR]), fn(r['proj']), fn(r['emp']),
                       fb(r['inv']), fb(r['invp']), yoy_str(r['inv'], r['invp']),
                       fb(r['dom']),  fp(sd(r['dom'],  _dom_n)*100),
                       fb(r['for_']), fp(sd(r['for_'], _for_n)*100)])
    rows_c.append(['TOTAL', fn(gn['proj'].sum()), fn(gn['emp'].sum()),
                   fb(gn['inv'].sum()), fb(gn['invp'].sum()), yoy_str(gn['inv'].sum(), gn['invp'].sum()),
                   fb(gn['dom'].sum()),  fp(100.0),
                   fb(gn['for_'].sum()), fp(100.0)])
    cw_c = _cw(4.0, 1.8, 2.3, 2.5, 2.5, 1.6, 2.0, 1.3, 2.0, 1.3)
    story.append(dtable(rows_c, cw_c))

    # ── Table 2D: Expansion Projects by Sector ────────────────────────────────
    story.append(PageBreak())
    story.append(TocEntry(1, f'2D  Expansion Projects by Sector'))
    story.append(Spacer(1, 0.3*cm))
    story.append(stat_line(f"2D   Expansion Projects by Sector"))
    story.append(Spacer(1, 0.1*cm))

    cur_div  = cur[cur['_div']].copy()
    prev_div = prev[prev['_div']].copy()

    gd  = _agg_type(cur_div)
    gdp = _agg_type(prev_div).rename(columns={'proj':'projp','emp':'empp','inv':'invp'})
    gd  = gd.merge(gdp, on=CSCTR, how='outer').fillna(0).sort_values('inv', ascending=False)
    gd['dom']  = cur_div.groupby(CSCTR, dropna=False)[CDRM].sum().reindex(gd[CSCTR]).fillna(0).values
    gd['for_'] = cur_div.groupby(CSCTR, dropna=False)[CFRM].sum().reindex(gd[CSCTR]).fillna(0).values

    _dom_d = gd['dom'].sum()
    _for_d = gd['for_'].sum()

    hdr_d = ['Sector', 'No. of\nProjects', 'Total\nEmployment',
             f'Total Investment\n(RM bil) {year}', f'Total Investment\n(RM bil) {year-1}', 'YoY\nInvestment',
             'Domestic\nInvestment (RM bil)', 'Domestic %',
             'Foreign\nInvestment (RM bil)', 'Foreign %']
    rows_d2 = [hdr_d]
    for _, r in gd.iterrows():
        rows_d2.append([str(r[CSCTR]), fn(r['proj']), fn(r['emp']),
                        fb(r['inv']), fb(r['invp']), yoy_str(r['inv'], r['invp']),
                        fb(r['dom']),  fp(sd(r['dom'],  _dom_d)*100),
                        fb(r['for_']), fp(sd(r['for_'], _for_d)*100)])
    rows_d2.append(['TOTAL', fn(gd['proj'].sum()), fn(gd['emp'].sum()),
                    fb(gd['inv'].sum()), fb(gd['invp'].sum()), yoy_str(gd['inv'].sum(), gd['invp'].sum()),
                    fb(gd['dom'].sum()),  fp(100.0),
                    fb(gd['for_'].sum()), fp(100.0)])
    cw_d = _cw(4.0, 1.8, 2.3, 2.5, 2.5, 1.6, 2.0, 1.3, 2.0, 1.3)
    story.append(dtable(rows_d2, cw_d))


def sec_export(story, cur, prev, year, pl):
    story.append(PageBreak())
    story.append(TocEntry(0, f'4A.  Export Analysis  —  {pl} {year}'))
    e80c = (cur[CEXP]>=80).sum()
    emp80= cur[cur[CEXP]>=80][CTE].sum()
    story.append(sec_bar(f'4A.  EXPORT ANALYSIS  —  {pl} {year}'))
    story.append(Spacer(1, 0.15*cm))
    story.append(stat_line(
        f"High export (≥80%): {fn(e80c)} of {fn(len(cur))} ({fp(sd(e80c,len(cur))*100)})  |  "
        f"Employment in high-export: {fn(emp80)}"
    ))
    story.append(Spacer(1, 0.15*cm))

    rows_d = []
    for sub, g in cur.groupby(CSCTR, dropna=False):
        tot = len(g)
        e80 = (g[CEXP]>=80).sum()
        e60 = ((g[CEXP]>=60)&(g[CEXP]<80)).sum()
        elt = (g[CEXP]<60).sum()
        rows_d.append((sub, tot, e80, e60, elt, g[CEXP].mean(), g[g[CEXP]>=80][CTE].sum()))
    rows_d.sort(key=lambda x: x[2], reverse=True)

    hdr = ['Sector', 'Projects',
           'Export\n≥80%', '% of Proj',
           'Export\n60-<80%', '% of Proj',
           'Export\n<60%', '% of Proj',
           'Avg\nExport %', 'Employment in\nExp ≥80%']
    rows = [hdr]
    ora  = []
    ri   = 1
    for sub, tot, e80, e60, elt, avg, emp_ in rows_d:
        rows.append([str(sub)[:35], fn(tot),
                     fn(e80), fp(sd(e80,tot)*100),
                     fn(e60), fp(sd(e60,tot)*100),
                     fn(elt), fp(sd(elt,tot)*100),
                     fp(avg), fn(emp_)])
        if e80 > 0: ora.append((ri, 2))
        ri += 1

    t80=sum(r[2] for r in rows_d); t60=sum(r[3] for r in rows_d)
    tlt=sum(r[4] for r in rows_d); tta=sum(r[1] for r in rows_d)
    rows.append(['TOTAL', fn(tta),
                 fn(t80), fp(sd(t80,tta)*100),
                 fn(t60), fp(sd(t60,tta)*100),
                 fn(tlt), fp(sd(tlt,tta)*100),
                 '', fn(sum(r[6] for r in rows_d))])

    cw = _cw(4, 1.6, 1.6, 1.6, 1.8, 1.6, 1.6, 1.6, 1.5, 2.2)
    story.append(dtable(rows, cw, ora))


def sec_emp_category(story, cur, prev, year, pl):
    """Total Employment by Category — Local / Foreign / Total, current vs previous year."""
    story.append(PageBreak())
    story.append(TocEntry(0, f'3.  Total Employment by Category  —  {pl} {year} vs {year-1}'))
    story.append(sec_bar(f'3.  TOTAL EMPLOYMENT BY CATEGORY  —  {pl}  {year} vs {year-1}'))
    story.append(Spacer(1, 0.15*cm))

    te_c  = cur[CTE].sum();  te_p  = prev[CTE].sum()
    mts_c = cur[[CMGT,CPTT,CCKT]].sum().sum()
    mts_p = prev[[CMGT,CPTT,CCKT]].sum().sum()
    story.append(stat_line(
        f"Total Employment {year}: {fn(te_c)}  |  "
        f"{year-1}: {fn(te_p)}  |  "
        f"YoY: {yoy_str(te_c, te_p)}  |  "
        f"MTS {year}: {fn(mts_c)} ({fp(sd(mts_c, te_c)*100)})"
    ))
    story.append(Spacer(1, 0.15*cm))

    CATS = [
        ('Managerial',                              CMGL,  CMGF,  CMGT),
        ('Professionals/ Technical & Supervisory',  CPTL,  CPTF,  CPTT),
        ('Craft Skills',                            CCKL,  CCKF,  CCKT),
        ('Sales, Clerical & Others',                CSCLL, CSCLF, CSCLT),
        ('Plant & Machine Operators & Assemblers',  CPML,  CPMF,  CPMT),
        ('Elementary Workers',                      CELML, CELMF, CELMT),
    ]

    # ── 2-row header ──────────────────────────────────────────────────────────
    hdr1 = [
        Paragraph('Category', WRAPHDR_C),
        Paragraph(f'Q1 {year-1}', WRAPHDR_C), '', '',
        Paragraph(f'Q1 {year}',   WRAPHDR_C), '', '',
        Paragraph('YoY\nTotal',   WRAPHDR_C),
    ]
    hdr2 = [
        '',
        Paragraph('Local',   WRAPHDR_C), Paragraph('Foreign', WRAPHDR_C), Paragraph('Total', WRAPHDR_C),
        Paragraph('Local',   WRAPHDR_C), Paragraph('Foreign', WRAPHDR_C), Paragraph('Total', WRAPHDR_C),
        '',
    ]
    rows = [hdr1, hdr2]

    tot_pl = tot_pf = tot_pt = tot_cl = tot_cf = tot_ct = 0

    for name, cl, cf, ct in CATS:
        pl_v = int(prev[cl].sum()); pf_v = int(prev[cf].sum()); pt_v = int(prev[ct].sum())
        ql_v = int(cur[cl].sum());  qf_v = int(cur[cf].sum());  qt_v = int(cur[ct].sum())
        tot_pl += pl_v; tot_pf += pf_v; tot_pt += pt_v
        tot_cl += ql_v; tot_cf += qf_v; tot_ct += qt_v
        rows.append([
            pw(name),
            _color_yoy(fn(pl_v)), _color_yoy(fn(pf_v)), _color_yoy(fn(pt_v)),
            _color_yoy(fn(ql_v)), _color_yoy(fn(qf_v)), _color_yoy(fn(qt_v)),
            _color_yoy(yoy_str(qt_v, pt_v)),
        ])

    rows.append([
        pw('TOTAL'),
        _color_yoy(fn(tot_pl)), _color_yoy(fn(tot_pf)), _color_yoy(fn(tot_pt)),
        _color_yoy(fn(tot_cl)), _color_yoy(fn(tot_cf)), _color_yoy(fn(tot_ct)),
        _color_yoy(yoy_str(tot_ct, tot_pt)),
    ])

    cw = _cw(5.0, 2.6, 2.0, 2.6, 2.6, 2.0, 2.6, 1.8)
    t  = Table(rows, colWidths=cw, repeatRows=2)
    t.setStyle(TableStyle([
        ('FONTSIZE',      (0,0),  (-1,-1), 8.5),
        ('TOPPADDING',    (0,0),  (-1,-1), 3),
        ('BOTTOMPADDING', (0,0),  (-1,-1), 3),
        ('LEFTPADDING',   (0,0),  (-1,-1), 4),
        ('RIGHTPADDING',  (0,0),  (-1,-1), 4),
        ('ALIGN',         (0,0),  (-1,-1), 'CENTER'),
        ('VALIGN',        (0,0),  (-1,-1), 'MIDDLE'),
        # Header rows 0 & 1
        ('BACKGROUND',    (0,0),  (-1,1),  CB),
        ('TEXTCOLOR',     (0,0),  (-1,1),  CW),
        ('FONTNAME',      (0,0),  (-1,1),  'Helvetica-Bold'),
        # Spans
        ('SPAN',          (0,0),  (0,1)),   # Category label spans 2 header rows
        ('SPAN',          (1,0),  (3,0)),   # Q1 prev spans 3 cols
        ('SPAN',          (4,0),  (6,0)),   # Q1 curr spans 3 cols
        ('SPAN',          (7,0),  (7,1)),   # YoY spans 2 header rows
        # Data rows
        ('FONTNAME',      (0,2),  (-1,-2), 'Helvetica'),
        ('ALIGN',         (0,2),  (0,-1),  'LEFT'),
        ('ROWBACKGROUNDS',(0,2),  (-1,-2), [CW, CLB]),
        # Total row
        ('BACKGROUND',    (0,-1), (-1,-1), CTOT),
        ('FONTNAME',      (0,-1), (-1,-1), 'Helvetica-Bold'),
        ('LINEABOVE',     (0,-1), (-1,-1), 0.8, CB),
        # Grid + vertical separator between the two period groups
        ('GRID',          (0,0),  (-1,-1), 0.3, CGRAY),
        ('LINEAFTER',     (3,0),  (3,-1),  1.0, CB),
    ]))
    story.append(t)


def sec_mts(story, cur, prev, year, pl):
    story.append(PageBreak())
    story.append(TocEntry(0, f'3A.  MTS Breakdown  —  {pl} {year} vs {year-1}'))
    mtc = cur[[CMGT,CPTT,CCKT]].sum().sum()
    mtp = prev[[CMGT,CPTT,CCKT]].sum().sum()
    ec  = cur[CTE].sum()
    ep  = prev[CTE].sum()
    story.append(sec_bar(f'3A.  MTS BREAKDOWN  —  {pl}  {year} vs {year-1}'))
    story.append(Spacer(1, 0.15*cm))
    story.append(stat_line(
        f"MTS {year}: {fn(mtc)} ({fp(sd(mtc,ec)*100)})  |  "
        f"MTS {year-1}: {fn(mtp)} ({fp(sd(mtp,ep)*100)})  |  "
        f"YoY Count: {yoy_str(mtc,mtp)}  |  Non-MTS: {fn(ec-mtc)}"
    ))
    story.append(Spacer(1, 0.15*cm))

    rows_d = []
    for sub, g in cur.groupby(CSCTR, dropna=False):
        tot = g[CTE].sum(); mgr = g[CMGT].sum()
        tec = g[CPTT].sum(); cft = g[CCKT].sum()
        mts = mgr+tec+cft
        rows_d.append((sub, len(g), tot, mgr, tec, cft, mts, tot-mts,
                        sd(mts,tot)*100, sd(g[CLE].sum(),tot)*100, g[CTRM].sum()))
    rows_d.sort(key=lambda x: x[6], reverse=True)

    hdr = ['Sector','Projects','Total\nEmployment',
           'Managerial','Prof/Tech\n& Supervisory','Craft Skills',
           'MTS Total','Non-MTS','MTS %','Local %']
    rows = [hdr]
    ora  = []
    ri   = 1
    for r in rows_d:
        rows.append([str(r[0])[:35]] + [fn(v) for v in r[1:8]] + [fp(r[8]), fp(r[9])])
        ora.append((ri, 6))
        ri += 1

    tc=cur[CTE].sum(); mg=cur[CMGT].sum(); te=cur[CPTT].sum(); ck=cur[CCKT].sum(); mt=mg+te+ck
    rows.append(['TOTAL',fn(len(cur)),fn(tc),fn(mg),fn(te),fn(ck),
                 fn(mt),fn(tc-mt),fp(sd(mt,tc)*100),fp(sd(cur[CLE].sum(),tc)*100)])

    cw = _cw(4.2, 1.5, 1.8, 1.8, 2.2, 1.8, 1.8, 1.8, 1.4, 1.4)
    story.append(dtable(rows, cw, ora))


def sec_mts_local_foreign(story, cur, prev, year, pl):
    # ── 4A: MTS Local ──────────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(TocEntry(0, f'3B.  MTS Local Breakdown  —  {pl} {year} vs {year-1}'))
    mtlc = cur[[CMGL, CPTL, CCKL]].sum().sum()
    mtlp = prev[[CMGL, CPTL, CCKL]].sum().sum()
    lec  = cur[CLE].sum()
    lep  = prev[CLE].sum()

    story.append(sec_bar(f'3B.  MTS LOCAL BREAKDOWN  —  {pl}  {year} vs {year-1}'))
    story.append(Spacer(1, 0.15*cm))
    story.append(stat_line(
        f"Local MTS {year}: {fn(mtlc)} ({fp(sd(mtlc,lec)*100)} of local emp)  |  "
        f"{year-1}: {fn(mtlp)} ({fp(sd(mtlp,lep)*100)})  |  "
        f"YoY: {yoy_str(mtlc,mtlp)}  |  Non-MTS Local: {fn(lec-mtlc)}"
    ))
    story.append(Spacer(1, 0.15*cm))

    rows_d = []
    for sub, g in cur.groupby(CSCTR, dropna=False):
        tot_l = g[CLE].sum()
        mgrl  = g[CMGL].sum()
        tecl  = g[CPTL].sum()
        cftl  = g[CCKL].sum()
        mtsl  = mgrl + tecl + cftl
        rows_d.append((sub, len(g), tot_l, mgrl, tecl, cftl, mtsl, tot_l - mtsl, sd(mtsl, tot_l)*100, g[CTRM].sum()))
    rows_d.sort(key=lambda x: x[6], reverse=True)

    hdr = ['Sector', 'Projects', 'Local\nEmployment',
           'Managerial\n(Local)', 'Prof/Tech\n(Local)', 'Craft Skills\n(Local)',
           'MTS Local\nTotal', 'Non-MTS\nLocal', 'MTS\nLocal %']
    rows = [hdr]
    ora  = []
    ri   = 1
    for r in rows_d:
        rows.append([str(r[0])[:35]] + [fn(v) for v in r[1:8]] + [fp(r[8])])
        ora.append((ri, 6))
        ri += 1

    tc_l = cur[CLE].sum()
    mg_l = cur[CMGL].sum(); te_l = cur[CPTL].sum(); ck_l = cur[CCKL].sum()
    mt_l = mg_l + te_l + ck_l
    rows.append(['TOTAL', fn(len(cur)), fn(tc_l), fn(mg_l), fn(te_l), fn(ck_l),
                 fn(mt_l), fn(tc_l - mt_l), fp(sd(mt_l, tc_l)*100)])

    cw = _cw(4.5, 1.5, 1.8, 1.8, 2.5, 2.0, 1.8, 1.8, 1.6)
    story.append(dtable(rows, cw, ora))

    # ── 4B: MTS Foreign ────────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(TocEntry(0, f'3C.  MTS Foreign Breakdown  —  {pl} {year} vs {year-1}'))
    mtfc = cur[[CMGF, CPTF, CCKF]].sum().sum()
    mtfp = prev[[CMGF, CPTF, CCKF]].sum().sum()
    fec  = cur[CFE].sum()
    fep  = prev[CFE].sum()

    story.append(sec_bar(f'3C.  MTS FOREIGN BREAKDOWN  —  {pl}  {year} vs {year-1}'))
    story.append(Spacer(1, 0.15*cm))
    story.append(stat_line(
        f"Foreign MTS {year}: {fn(mtfc)} ({fp(sd(mtfc,fec)*100)} of foreign emp)  |  "
        f"{year-1}: {fn(mtfp)} ({fp(sd(mtfp,fep)*100)})  |  "
        f"YoY: {yoy_str(mtfc,mtfp)}  |  Non-MTS Foreign: {fn(fec-mtfc)}"
    ))
    story.append(Spacer(1, 0.15*cm))

    rows_d = []
    for sub, g in cur.groupby(CSCTR, dropna=False):
        tot_f = g[CFE].sum()
        mgrf  = g[CMGF].sum()
        tecf  = g[CPTF].sum()
        cftf  = g[CCKF].sum()
        mtsf  = mgrf + tecf + cftf
        rows_d.append((sub, len(g), tot_f, mgrf, tecf, cftf, mtsf, tot_f - mtsf, sd(mtsf, tot_f)*100, g[CTRM].sum()))
    rows_d.sort(key=lambda x: x[6], reverse=True)

    hdr = ['Sector', 'Projects', 'Foreign\nEmployment',
           'Managerial\n(Foreign)', 'Prof/Tech\n(Foreign)', 'Craft\nSkills (For)',
           'MTS Foreign\nTotal', 'Non-MTS\nForeign', 'MTS\nForeign %']
    rows = [hdr]
    ora  = []
    ri   = 1
    for r in rows_d:
        rows.append([str(r[0])[:35]] + [fn(v) for v in r[1:8]] + [fp(r[8])])
        ora.append((ri, 6))
        ri += 1

    tc_f = cur[CFE].sum()
    mg_f = cur[CMGF].sum(); te_f = cur[CPTF].sum(); ck_f = cur[CCKF].sum()
    mt_f = mg_f + te_f + ck_f
    rows.append(['TOTAL', fn(len(cur)), fn(tc_f), fn(mg_f), fn(te_f), fn(ck_f),
                 fn(mt_f), fn(tc_f - mt_f), fp(sd(mt_f, tc_f)*100)])

    cw = _cw(4.5, 1.5, 1.8, 2.0, 2.5, 2.0, 2.0, 2.0, 1.8)
    story.append(dtable(rows, cw, ora))


def sec_salary(story, cur, prev, year, pl):
    story.append(PageBreak())
    story.append(TocEntry(0, f'3D.  Salary Breakdown  —  {pl} {year}'))
    s5c = sum(cur[b[1]].sum() for b in SAL[2:])
    s5p = sum(prev[b[1]].sum() for b in SAL[2:])
    ec  = cur[CTE].sum()
    story.append(sec_bar(f'3D.  SALARY BREAKDOWN  —  {pl} {year}'))
    story.append(Spacer(1, 0.15*cm))
    story.append(stat_line(
        f"Workers ≥RM5,000: {fn(s5c)} ({fp(sd(s5c,ec)*100)})  |  YoY: {yoy_str(s5c,s5p)}"
    ))
    story.append(Spacer(1, 0.15*cm))

    rows_d = []
    for sub, g in cur.groupby(CSCTR, dropna=False):
        tot = g[CTE].sum()
        bands = [(g[b[1]].sum(), g[b[2]].sum(), g[b[3]].sum()) for b in SAL]
        s5 = bands[2][0] + bands[3][0]
        rows_d.append((sub, len(g), tot, bands, s5, g[CTRM].sum()))
    rows_d.sort(key=lambda x: x[2], reverse=True)

    hdr = ['Sector','Projects','Total\nEmployment',
           '<RM3,000','<RM3K\n%','RM3K-5K','RM3K-5K\n%',
           'RM5K-10K','RM5K-10K\n%','≥RM10K','≥RM10K\n%',
           '≥RM5K\nTotal','≥RM5K\n%']
    rows = [hdr]
    for sub, proj, tot, bands, s5, _ in rows_d:
        rows.append([str(sub)[:32], fn(proj), fn(tot),
                     fn(bands[0][0]), fp(sd(bands[0][0],tot)*100),
                     fn(bands[1][0]), fp(sd(bands[1][0],tot)*100),
                     fn(bands[2][0]), fp(sd(bands[2][0],tot)*100),
                     fn(bands[3][0]), fp(sd(bands[3][0],tot)*100),
                     fn(s5),          fp(sd(s5,tot)*100)])

    tsal = [sum(cur[b[1]].sum() for b in [SAL[i]]) for i in range(4)]
    te = cur[CTE].sum(); ts5 = sum(tsal[2:])
    rows.append(['TOTAL',fn(len(cur)),fn(te),
                 fn(tsal[0]),fp(sd(tsal[0],te)*100),
                 fn(tsal[1]),fp(sd(tsal[1],te)*100),
                 fn(tsal[2]),fp(sd(tsal[2],te)*100),
                 fn(tsal[3]),fp(sd(tsal[3],te)*100),
                 fn(ts5),    fp(sd(ts5,te)*100)])

    cw = _cw(3.5, 1.4, 1.6, 1.6, 1.3, 1.6, 1.3, 1.6, 1.4, 1.6, 1.3, 1.6, 1.2)
    story.append(dtable(rows, cw))


def sec_salary_local_foreign(story, cur, prev, year, pl):
    # ── 5A: Salary Local ───────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(TocEntry(0, f'3E.  Salary Breakdown (Local)  —  {pl} {year}'))
    s5lc = sum(cur[b[2]].sum() for b in SAL[2:])
    lec  = cur[CLE].sum()

    story.append(sec_bar(f'3E.  SALARY BREAKDOWN (LOCAL)  —  {pl} {year}'))
    story.append(Spacer(1, 0.15*cm))
    story.append(stat_line(
        f"Local Workers >=RM5,000: {fn(s5lc)} ({fp(sd(s5lc,lec)*100)} of local emp)"
    ))
    story.append(Spacer(1, 0.15*cm))

    rows_d = []
    for sub, g in cur.groupby(CSCTR, dropna=False):
        tot_l = g[CLE].sum()
        bands = [g[b[2]].sum() for b in SAL]
        s5 = bands[2] + bands[3]
        rows_d.append((sub, len(g), tot_l, bands, s5, g[CTRM].sum()))
    rows_d.sort(key=lambda x: x[2], reverse=True)

    hdr = ['Sector', 'Projects', 'Local\nEmployment',
           '<RM3K\n(Local)', '<RM3K\n%', 'RM3K-5K\n(Local)', 'RM3K-5K\n%',
           'RM5K-10K\n(Local)', 'RM5K-10K\n%', '>=RM10K\n(Local)', '>=RM10K\n%',
           '>=RM5K\nTotal', '>=RM5K\n%']
    rows = [hdr]
    for sub, proj, tot, bands, s5, _ in rows_d:
        rows.append([str(sub)[:32], fn(proj), fn(tot),
                     fn(bands[0]), fp(sd(bands[0], tot)*100),
                     fn(bands[1]), fp(sd(bands[1], tot)*100),
                     fn(bands[2]), fp(sd(bands[2], tot)*100),
                     fn(bands[3]), fp(sd(bands[3], tot)*100),
                     fn(s5),       fp(sd(s5, tot)*100)])

    tsal_l = [cur[b[2]].sum() for b in SAL]
    te_l = cur[CLE].sum(); ts5_l = sum(tsal_l[2:])
    rows.append(['TOTAL', fn(len(cur)), fn(te_l),
                 fn(tsal_l[0]), fp(sd(tsal_l[0], te_l)*100),
                 fn(tsal_l[1]), fp(sd(tsal_l[1], te_l)*100),
                 fn(tsal_l[2]), fp(sd(tsal_l[2], te_l)*100),
                 fn(tsal_l[3]), fp(sd(tsal_l[3], te_l)*100),
                 fn(ts5_l),     fp(sd(ts5_l, te_l)*100)])

    cw = _cw(3.5, 1.4, 1.6, 1.6, 1.3, 1.6, 1.3, 1.6, 1.4, 1.6, 1.3, 1.6, 1.2)
    story.append(dtable(rows, cw))

    # ── 5B: Salary Foreign ─────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(TocEntry(0, f'3F.  Salary Breakdown (Foreign)  —  {pl} {year}'))
    s5fc = sum(cur[b[3]].sum() for b in SAL[2:])
    fec  = cur[CFE].sum()

    story.append(sec_bar(f'3F.  SALARY BREAKDOWN (FOREIGN)  —  {pl} {year}'))
    story.append(Spacer(1, 0.15*cm))
    story.append(stat_line(
        f"Foreign Workers >=RM5,000: {fn(s5fc)} ({fp(sd(s5fc,fec)*100)} of foreign emp)"
    ))
    story.append(Spacer(1, 0.15*cm))

    rows_d = []
    for sub, g in cur.groupby(CSCTR, dropna=False):
        tot_f = g[CFE].sum()
        bands = [g[b[3]].sum() for b in SAL]
        s5 = bands[2] + bands[3]
        rows_d.append((sub, len(g), tot_f, bands, s5, g[CTRM].sum()))
    rows_d.sort(key=lambda x: x[2], reverse=True)

    hdr = ['Sector', 'Projects', 'Foreign\nEmployment',
           '<RM3K\n(Foreign)', '<RM3K\n%', 'RM3K-5K\n(Foreign)', 'RM3K-5K\n%',
           'RM5K-10K\n(Foreign)', 'RM5K-10K\n%', '>=RM10K\n(Foreign)', '>=RM10K\n%',
           '>=RM5K\nTotal', '>=RM5K\n%']
    rows = [hdr]
    for sub, proj, tot, bands, s5, _ in rows_d:
        rows.append([str(sub)[:32], fn(proj), fn(tot),
                     fn(bands[0]), fp(sd(bands[0], tot)*100),
                     fn(bands[1]), fp(sd(bands[1], tot)*100),
                     fn(bands[2]), fp(sd(bands[2], tot)*100),
                     fn(bands[3]), fp(sd(bands[3], tot)*100),
                     fn(s5),       fp(sd(s5, tot)*100)])

    tsal_f = [cur[b[3]].sum() for b in SAL]
    te_f = cur[CFE].sum(); ts5_f = sum(tsal_f[2:])
    rows.append(['TOTAL', fn(len(cur)), fn(te_f),
                 fn(tsal_f[0]), fp(sd(tsal_f[0], te_f)*100),
                 fn(tsal_f[1]), fp(sd(tsal_f[1], te_f)*100),
                 fn(tsal_f[2]), fp(sd(tsal_f[2], te_f)*100),
                 fn(tsal_f[3]), fp(sd(tsal_f[3], te_f)*100),
                 fn(ts5_f),     fp(sd(ts5_f, te_f)*100)])

    cw = _cw(3.5, 1.4, 1.6, 1.8, 1.3, 1.8, 1.3, 1.8, 1.4, 1.8, 1.3, 1.6, 1.2)
    story.append(dtable(rows, cw))


def sec_cipe(story, cur, year, pl):
    story.append(PageBreak())
    story.append(TocEntry(0, f'2E.  CIPE by Sector  —  {pl} {year}'))
    ic = cur[CTRM].sum()
    ec = cur[CTE].sum()
    story.append(sec_bar(f'2E.  CIPE BY SECTOR  —  {pl} {year}'))
    story.append(Spacer(1, 0.15*cm))
    story.append(stat_line(
        f"Overall CIPE: {fmt_rm(sd(ic,ec))}  |  Total Investment: {fmt_rm(ic)}  |  Total Employment: {fn(ec)}  |  "
        f"Sorted by CIPE (highest first)"
    ))
    story.append(Spacer(1, 0.15*cm))

    rows_d = []
    for sub, g in cur.groupby(CSCTR, dropna=False):
        proj = len(g)
        inv  = g[CTRM].sum()
        dom  = g[CDRM].sum()
        for_ = g[CFRM].sum()
        emp  = g[CTE].sum()
        lemp = g[CLE].sum()
        femp = g[CFE].sum()
        cipe = sd(inv, emp)
        rows_d.append((sub, proj, inv, dom, for_, emp, lemp, femp, cipe))
    rows_d.sort(key=lambda x: x[8], reverse=True)

    hdr = ['Sector', 'Projects',
           'Total\nInvestment (RM bil)', 'Domestic\nInvestment (RM bil)', 'Foreign\nInvestment (RM bil)',
           'Total\nEmployment', 'Local\nEmployment', 'Foreign\nEmployment',
           'CIPE\n(RM/Worker)']
    rows = [hdr]
    ora  = []
    ri   = 1
    for r in rows_d:
        rows.append([
            str(r[0])[:35],
            fn(r[1]),
            fb(r[2]), fb(r[3]), fb(r[4]),
            fn(r[5]), fn(r[6]), fn(r[7]),
            fmt_rm(r[8]),
        ])
        ora.append((ri, 8))
        ri += 1
    rows.append([
        'TOTAL',
        fn(len(cur)),
        fb(ic), fb(cur[CDRM].sum()), fb(cur[CFRM].sum()),
        fn(ec), fn(cur[CLE].sum()), fn(cur[CFE].sum()),
        fmt_rm(sd(ic, ec)),
    ])

    cw = _cw(4.5, 1.4, 2.2, 2.0, 2.0, 1.6, 1.6, 1.8, 3.2)
    story.append(dtable(rows, cw, ora))


def sec_rawmat(story, cur, prev, year, pl):
    story.append(PageBreak())
    story.append(TocEntry(0, f'4B.  Raw Materials & Components  —  {pl} {year}'))
    story.append(sec_bar(f'4B.  RAW MATERIALS & COMPONENTS CONTENT  —  {pl} {year}'))
    story.append(Spacer(1, 0.15*cm))
    story.append(stat_line(
        f"Avg Local Content: {fp(cur[CRML].mean())}  |  Avg Import Content: {fp(cur[CRMI].mean())}"
    ))
    story.append(Spacer(1, 0.15*cm))

    rows_d = []
    for sub, g in cur.groupby(CSCTR, dropna=False):
        rows_d.append((sub, len(g),
            g[CRML].mean(), g[CRMI].mean(),
            g[CRML].max(),  g[CRML].min(),
            g[CRMI].max(),  g[CRMI].min(), g[CTRM].sum(), g[CVA].mean()))
    rows_d.sort(key=lambda x: x[8], reverse=True)

    hdr = ['Sector','Projects',
           'Avg Local\nRM %','Avg Import\nRM %',
           'Max Local %','Min Local %','Max Import %','Min Import %','Avg VA %']
    rows = [hdr]
    for r in rows_d:
        rows.append([str(r[0])[:35], fn(r[1]),
                     fp(r[2]),fp(r[3]),fp(r[4]),fp(r[5]),fp(r[6]),fp(r[7]),fp(r[9])])
    rows.append(['TOTAL',fn(len(cur)),fp(cur[CRML].mean()),fp(cur[CRMI].mean()),'','','','',fp(cur[CVA].mean())])

    cw = _cw(5, 1.6, 2.2, 2.2, 1.8, 1.8, 1.8, 1.8, 1.8)
    story.append(dtable(rows, cw))


def sec_i40(story, cur, prev, year, pl):
    story.append(PageBreak())
    story.append(TocEntry(0, f'4C.  Industry 4.0 Adoption  —  {pl} {year}'))
    i40c = cur['_i40'].sum()
    story.append(sec_bar(f'4C.  INDUSTRY 4.0 ADOPTION  —  {pl} {year}'))
    story.append(Spacer(1, 0.15*cm))
    story.append(stat_line(
        f"I4.0 adopters: {fn(i40c)} of {fn(len(cur))} ({fp(sd(i40c,len(cur))*100)})  |  "
        f"Adoption % = projects with at least 1 pillar / total projects  |  "
        f"YoY: {yoy_str(i40c, prev['_i40'].sum())}"
    ))
    story.append(Spacer(1, 0.15*cm))

    rows_d = []
    for sub, g in cur.groupby(CSCTR, dropna=False):
        adp = g['_i40'].sum()
        pil = [g[f'_p_{p}'].sum() for p in I40P]
        rows_d.append((sub, len(g), adp, pil, g[CTRM].sum()))
    rows_d.sort(key=lambda x: x[4], reverse=True)

    short_p = ['Cyber','Auto\nRobot','IoT','AI','Cloud','Sys\nInteg',
               'Adv\nMat','Auto-\nmation','Big\nData','AR']
    hdr = ['Sector','Total\nProj','I4.0 Adopters\n(%)'] + short_p
    rows = [hdr]
    ora  = []
    ri   = 1
    for sub, proj, adp, pils, _ in rows_d:
        rows.append([str(sub)[:30], fn(proj), f"{fn(adp)} ({fp(sd(adp,proj)*100)})"] +
                    [fn(p) for p in pils])
        if adp > 0: ora.append((ri, 2))
        ri += 1

    rows.append(['TOTAL', fn(len(cur)), f"{fn(i40c)} ({fp(sd(i40c,len(cur))*100)})"] +
                [fn(cur[f'_p_{p}'].sum()) for p in I40P])

    pillar_w = (TW - 4*cm - 1.5*cm - 2.5*cm) / len(I40P)
    cw  = [4*cm,1.5*cm,2.5*cm] + [pillar_w]*len(I40P)
    story.append(dtable(rows, cw, ora))


def sec_indicators(story, cur, prev, year, pl):
    story.append(PageBreak())
    story.append(TocEntry(0, f'4D.  Project Indicators  —  {pl} {year}'))
    story.append(sec_bar(f'4D.  PROJECT INDICATORS  —  {pl} {year}'))
    story.append(Spacer(1, 0.15*cm))

    inds = [(CNSS,'NSS'),(CEV,'EV'),(CGRNI,'Green'),(CHAL,'Halal'),
            (CHIP,'Hi-Impact'),(CKB,'KBased'),(CBIO,'Biomass'),(CFIA,'FIAF')]

    rows_d = []
    for sub, g in cur.groupby(CSCTR, dropna=False):
        rows_d.append((sub, len(g), [g[c].sum() for c,_ in inds], g[CTRM].sum()))
    rows_d.sort(key=lambda x: x[3], reverse=True)

    hdr = ['Sector', 'Projects'] + [lbl for _, lbl in inds]
    rows = [hdr]
    for sub, proj, cnts, _ in rows_d:
        rows.append([str(sub)[:32], fn(proj)] +
                    [f"{fn(c)}\n({fp(sd(c,proj)*100)})" for c in cnts])

    tcnts = [cur[c].sum() for c,_ in inds]; tp = len(cur)
    rows.append(['TOTAL', fn(tp)] + [f"{fn(c)}\n({fp(sd(c,tp)*100)})" for c in tcnts])

    ni = len(inds)
    ind_w = (TW - 4.5*cm - 1.5*cm) / ni
    cw = [4.5*cm, 1.5*cm] + [ind_w]*ni
    story.append(dtable(rows, cw))


def sec_green(story, cur, prev, year, pl):
    story.append(PageBreak())
    story.append(TocEntry(0, f'4E.  Green Investment (GIS)  —  {pl} {year} vs {year-1}'))
    gc   = cur[CGRNI].sum();  gp_  = prev[CGRNI].sum()
    tc   = len(cur);           tp   = len(prev)
    gi_c = cur[cur[CGRNI]][CTRM].sum()
    gi_p = prev[prev[CGRNI]][CTRM].sum()

    story.append(sec_bar(f'4E.  GREEN INVESTMENT (GIS)  —  {pl}  {year} vs {year-1}'))
    story.append(Spacer(1, 0.15*cm))
    story.append(stat_line(
        f"Green Projects {year}: {fn(gc)} ({fp(sd(gc,tc)*100)} of total)  |  "
        f"{year-1}: {fn(gp_)} ({fp(sd(gp_,tp)*100)})  |  "
        f"YoY Projects: {yoy_str(gc,gp_)}  |  "
        f"Green Investment {year}: RM {fb(gi_c)} bil  |  YoY Inv: {yoy_str(gi_c,gi_p)}"
    ))
    story.append(Spacer(1, 0.2*cm))

    cur_g  = cur[cur[CGRNI]].copy()
    prev_g = prev[prev[CGRNI]].copy()
    total_green  = int(gc);    total_greenp = int(gp_)
    total_gi     = gi_c;       total_gip    = gi_p

    # ── 9A: By GIS Type ───────────────────────────────────────────────────────
    story.append(stat_line("4EA   Breakdown by Green Investment Strategy (GIS) Type"))
    story.append(Spacer(1, 0.1*cm))

    def grp_gis(df):
        return df.groupby('_gis_cat', dropna=False).agg(
            proj=('_gis_cat','count'), inv=(CTRM,'sum'), emp=(CTE,'sum')
        ).reset_index().rename(columns={'_gis_cat': 'gis'})

    cg  = grp_gis(cur_g)
    pg  = grp_gis(prev_g).rename(columns={'proj':'projp','inv':'invp'})
    mg  = cg.merge(pg[['gis','projp','invp']], on='gis', how='outer').fillna(0)
    mg  = mg[mg['gis'] != '-'].sort_values('proj', ascending=False)

    hdr_t = ['GIS Type', f'Projects\n{year}', '% of Green', f'Projects\n{year-1}', 'YoY',
             'Investment\n(RM bil)', '% of Green\nInvestment', 'Employment', 'YoY\nInvestment']
    rows_t = [hdr_t]
    for _, r in mg.iterrows():
        rows_t.append([
            str(r['gis']),
            fn(r['proj']),  fp(sd(r['proj'], total_green)*100),
            fn(r['projp']), yoy_str(r['proj'], r['projp']),
            fb(r['inv']),   fp(sd(r['inv'], total_gi)*100),
            fn(r['emp']),   yoy_str(r['inv'], r['invp']),
        ])
    rows_t.append([
        'TOTAL', fn(total_green), '100.0%', fn(total_greenp),
        yoy_str(total_green, total_greenp),
        fb(total_gi), '100.0%',
        fn(cur_g[CTE].sum()), yoy_str(total_gi, total_gip),
    ])
    cw_t = _cw(5, 1.8, 1.6, 1.8, 1.4, 2.2, 1.8, 2, 1.4)
    story.append(dtable(rows_t, cw_t))

    story.append(Spacer(1, 0.3*cm))

    # ── 9B: By Sector ─────────────────────────────────────────────────────────
    story.append(stat_line("4EB   Green Projects by Sector"))
    story.append(Spacer(1, 0.1*cm))

    def grp_sec(df):
        return df.groupby(CSCTR, dropna=False).agg(
            total=(CSCTR,'count'), green=(CGRNI,'sum'), inv=(CTRM,'sum')
        ).reset_index()

    cs = grp_sec(cur)
    ps = grp_sec(prev).rename(columns={'green':'greenp','inv':'invp'})
    ms = cs.merge(ps[[CSCTR,'greenp','invp']], on=CSCTR, how='left').fillna(0)
    ms['green_inv']  = cur_g.groupby(CSCTR, dropna=False)[CTRM].sum().reindex(ms[CSCTR]).fillna(0).values
    ms['green_invp'] = prev_g.groupby(CSCTR, dropna=False)[CTRM].sum().reindex(ms[CSCTR]).fillna(0).values
    ms = ms.sort_values('green', ascending=False)

    hdr_a = ['Sector', f'Total\nProj', 'Green\nProj', 'Green %',
             'Green\nInvestment (RM bil)', 'Green\nInvestment %',
             'YoY\nProj', 'YoY\nInv']
    rows_a = [hdr_a]
    for _, r in ms.iterrows():
        rows_a.append([
            str(r[CSCTR]),
            fn(r['total']),  fn(r['green']),
            fp(sd(r['green'], r['total'])*100),
            fb(r['green_inv']),
            fp(sd(r['green_inv'], total_gi)*100),
            yoy_str(r['green'], r['greenp']),
            yoy_str(r['green_inv'], r['green_invp']),
        ])
    rows_a.append([
        'TOTAL', fn(tc), fn(total_green), fp(sd(total_green,tc)*100),
        fb(total_gi), '100.0%',
        yoy_str(total_green, total_greenp), yoy_str(total_gi, total_gip),
    ])
    cw_a = _cw(5.5, 1.8, 1.8, 1.6, 2.2, 1.8, 1.8, 1.8)
    story.append(dtable(rows_a, cw_a))

    story.append(Spacer(1, 0.3*cm))

    # ── 9C: By State ──────────────────────────────────────────────────────────
    story.append(stat_line("9C   Green Projects by State"))
    story.append(Spacer(1, 0.1*cm))

    css = cur_g.groupby(CSTA, dropna=False).agg(
        green=(CSTA,'count'), inv=(CTRM,'sum'), emp=(CTE,'sum')).reset_index()
    pss = prev_g.groupby(CSTA, dropna=False).agg(
        greenp=(CSTA,'count'), invp=(CTRM,'sum')).reset_index()
    mss = css.merge(pss, on=CSTA, how='outer').fillna(0).sort_values('green', ascending=False)

    hdr_b = ['State', f'Green Proj\n{year}', '% of Green', f'Green Proj\n{year-1}', 'YoY',
             'Green\nInvestment (RM bil)', 'YoY\nInvestment', 'Green\nEmployment']
    rows_b = [hdr_b]
    for _, r in mss.iterrows():
        rows_b.append([
            str(r[CSTA]),
            fn(r['green']), fp(sd(r['green'], total_green)*100),
            fn(r['greenp']), yoy_str(r['green'], r['greenp']),
            fb(r['inv']),    yoy_str(r['inv'], r['invp']),
            fn(r['emp']),
        ])
    rows_b.append([
        'TOTAL', fn(total_green), '100.0%', fn(total_greenp),
        yoy_str(total_green, total_greenp),
        fb(total_gi), yoy_str(total_gi, total_gip),
        fn(cur_g[CTE].sum()),
    ])
    cw_b = _cw(4, 2, 1.8, 2, 1.5, 2.5, 1.5, 2)
    story.append(dtable(rows_b, cw_b))


def sec_country(story, cur, prev, year, pl):
    story.append(PageBreak())
    story.append(TocEntry(0, f'6.  Foreign Investment by Country  —  {pl} {year} vs {year-1}'))
    cur_f = cur[cur['_for']]; prev_f = prev[prev['_for']]
    fc = cur_f[CFRM].sum(); fp_ = prev_f[CFRM].sum()
    story.append(sec_bar(f'6.  FOREIGN INVESTMENT BY ULTIMATE COUNTRY  —  {pl} {year} vs {year-1}'))
    story.append(Spacer(1, 0.15*cm))
    story.append(stat_line(
        f"Total Foreign Investment {year}: {fmt_rm(fc)}  |  "
        f"{year-1}: {fmt_rm(fp_)}  |  YoY: {yoy_str(fc,fp_)}"
    ))
    story.append(Spacer(1, 0.15*cm))

    c = cur_f.groupby(CCNT,dropna=False).agg(proj=(CCNT,'count'),inv=(CFRM,'sum')).reset_index()
    p = prev_f.groupby(CCNT,dropna=False).agg(projp=(CCNT,'count'),invp=(CFRM,'sum')).reset_index()
    m = c.merge(p,on=CCNT,how='outer').fillna(0).sort_values('inv',ascending=False)
    m['share'] = m['inv']/fc*100 if fc else 0

    hdr = ['Country (Ultimate)',
           f'Proj {year}', f'Proj {year-1}','YoY',
           f'Investment (RM bil)\n{year}','Share %',
           f'Investment (RM bil)\n{year-1}','YoY\nInvestment']
    rows = [hdr]
    for _, r in m.iterrows():
        rows.append([str(r[CCNT]),
                     fn(r['proj']),fn(r['projp']),yoy_str(r['proj'],r['projp']),
                     fb(r['inv']),fp(r['share']),fb(r['invp']),yoy_str(r['inv'],r['invp'])])
    rows.append(['TOTAL',
                 fn(m['proj'].sum()),fn(m['projp'].sum()),yoy_str(m['proj'].sum(),m['projp'].sum()),
                 fb(m['inv'].sum()),'100.0%',fb(m['invp'].sum()),yoy_str(m['inv'].sum(),m['invp'].sum())])

    cw = _cw(4.5, 1.8, 1.8, 1.4, 2.5, 1.5, 2.5, 1.4)
    story.append(dtable(rows, cw))


def sec_state(story, cur, prev, year, pl):
    story.append(PageBreak())
    story.append(TocEntry(0, f'5A.  Distribution by State  —  {pl} {year} vs {year-1}'))
    story.append(sec_bar(f'5A.  DISTRIBUTION BY STATE  —  {pl} {year} vs {year-1}'))
    story.append(Spacer(1, 0.15*cm))

    c = cur.groupby(CSTA,dropna=False).agg(proj=(CSTA,'count'),inv=(CTRM,'sum'),emp=(CTE,'sum')).reset_index()
    p = prev.groupby(CSTA,dropna=False).agg(projp=(CSTA,'count'),invp=(CTRM,'sum'),empp=(CTE,'sum')).reset_index()
    m = c.merge(p,on=CSTA,how='outer').fillna(0).sort_values('inv',ascending=False)

    hdr = ['State',
           f'Proj {year}',f'Proj {year-1}','YoY',
           f'Investment (RM bil) {year}',f'Investment (RM bil) {year-1}','YoY\nInvestment',
           f'Employment {year}',f'Employment {year-1}','YoY\nEmployment']
    rows = [hdr]
    for _, r in m.iterrows():
        rows.append([str(r[CSTA]),
                     fn(r['proj']),fn(r['projp']),yoy_str(r['proj'],r['projp']),
                     fb(r['inv']),fb(r['invp']),yoy_str(r['inv'],r['invp']),
                     fn(r['emp']),fn(r['empp']),yoy_str(r['emp'],r['empp'])])
    rows.append(['TOTAL',
                 fn(m['proj'].sum()),fn(m['projp'].sum()),yoy_str(m['proj'].sum(),m['projp'].sum()),
                 fb(m['inv'].sum()),fb(m['invp'].sum()),yoy_str(m['inv'].sum(),m['invp'].sum()),
                 fn(m['emp'].sum()),fn(m['empp'].sum()),yoy_str(m['emp'].sum(),m['empp'].sum())])

    cw = _cw(3.5, 1.8, 1.8, 1.3, 2.3, 2.3, 1.3, 2, 2, 1.3)
    story.append(dtable(rows, cw))


def sec_lds_state(story, cur, prev, year, pl):
    story.append(PageBreak())
    story.append(TocEntry(0, f'5B.  LDS State  —  {pl} {year} vs {year-1}'))
    LDS_STATES = ['Perlis', 'Kedah', 'Terengganu', 'Kelantan', 'Sabah', 'Sarawak']

    cur_lds  = cur[cur[CSTA].isin(LDS_STATES)]
    prev_lds = prev[prev[CSTA].isin(LDS_STATES)]
    tc = len(cur_lds); ic = cur_lds[CTRM].sum(); ec = cur_lds[CTE].sum()
    tp = len(prev_lds); ip = prev_lds[CTRM].sum()

    story.append(sec_bar(f'5B.  LDS STATE  —  {pl} {year} vs {year-1}'))
    story.append(Spacer(1, 0.15*cm))
    story.append(stat_line(
        f"LDS: {fn(tc)} projek  |  Pelaburan: {fmt_rm(ic)}  |  "
        f"Pekerjaan: {fn(ec)}  |  YoY Projek: {yoy_str(tc,tp)}  |  YoY Investment: {yoy_str(ic,ip)}"
    ))
    story.append(Spacer(1, 0.15*cm))

    rows_d = []
    for state in LDS_STATES:
        sc = cur[cur[CSTA] == state]
        sp = prev[prev[CSTA] == state]
        proj  = len(sc)
        projp = len(sp)
        lemp  = sc[CLE].sum()
        femp  = sc[CFE].sum()
        emp   = sc[CTE].sum()
        inv_f = sc[CFRM].sum()
        inv_d = sc[CDRM].sum()
        inv_t = sc[CTRM].sum()
        mts   = sc[[CMGT, CPTT, CCKT]].sum().sum()
        sal5  = sum(sc[b[1]].sum() for b in SAL[2:])
        rows_d.append((state, proj, lemp, femp, emp, inv_f, inv_d, inv_t,
                       mts, sal5, projp, sp[CTRM].sum()))

    rows_d.sort(key=lambda x: x[7], reverse=True)

    hdr = ['State', 'Projects',
           'Total\nEmployment', 'Local\nEmployment', 'Foreign\nEmployment',
           'Local\nInvestment (RM bil)', 'Foreign\nInvestment (RM bil)', 'Total\nInvestment (RM bil)',
           'MTS', 'MTS %', 'Salary\n>=RM5K', '>=RM5K %']
    rows = [hdr]
    for r in rows_d:
        rows.append([
            str(r[0]),
            fn(r[1]),
            fn(r[4]), fn(r[2]), fn(r[3]),
            fb(r[6]), fb(r[5]), fb(r[7]),
            fn(r[8]), fp(sd(r[8], r[4])*100),
            fn(r[9]), fp(sd(r[9], r[4])*100),
        ])

    tot_emp_lds  = sum(r[4] for r in rows_d)
    tot_mts_lds  = sum(r[8] for r in rows_d)
    tot_sal5_lds = sum(r[9] for r in rows_d)
    rows.append([
        'TOTAL',
        fn(sum(r[1] for r in rows_d)),
        fn(tot_emp_lds),
        fn(sum(r[2] for r in rows_d)), fn(sum(r[3] for r in rows_d)),
        fb(sum(r[6] for r in rows_d)), fb(sum(r[5] for r in rows_d)), fb(sum(r[7] for r in rows_d)),
        fn(tot_mts_lds),  fp(sd(tot_mts_lds,  tot_emp_lds)*100),
        fn(tot_sal5_lds), fp(sd(tot_sal5_lds, tot_emp_lds)*100),
    ])

    cw = _cw(3.0, 1.4, 2.0, 2.0, 2.0, 2.5, 2.5, 2.5, 1.8, 1.5, 1.8, 1.5)
    story.append(dtable(rows, cw))


def sec_state_top3(story, cur, prev, year, pl):
    state_inv = cur.groupby(CSTA, dropna=False)[CTRM].sum().sort_values(ascending=False)
    top3 = state_inv.head(3).index.tolist()

    for rank, state in enumerate(top3, 1):
        sc  = cur[cur[CSTA] == state].copy()
        sp  = prev[prev[CSTA] == state].copy()
        n   = len(sc);  np_ = len(sp)
        ic  = sc[CTRM].sum(); ip = sp[CTRM].sum()
        ec  = sc[CTE].sum()
        lec = sc[CLE].sum(); fec = sc[CFE].sum()

        # ── Page: Projects, Investment, Employment by sector ──────────────
        story.append(PageBreak())
        if rank == 1:
            story.append(TocEntry(0, f'5C.  Top State Breakdown  —  {pl} {year} vs {year-1}'))
        story.append(sec_bar(
            f'5C{chr(64+rank)}.  TOP STATE #{rank}: {state}  —  {pl} {year} vs {year-1}'
        ))
        story.append(Spacer(1, 0.15*cm))
        story.append(stat_line(
            f"{state}  |  Projects: {fn(n)} (YoY: {yoy_str(n,np_)})  |  "
            f"Investment: {fmt_rm(ic)} (YoY: {yoy_str(ic,ip)})  |  "
            f"Total Employment: {fn(ec)}  |  Local: {fn(lec)} ({fp(sd(lec,ec)*100)})  |  "
            f"Foreign: {fn(fec)} ({fp(sd(fec,ec)*100)})"
        ))
        story.append(Spacer(1, 0.15*cm))

        rows_d = []
        for sub, g in sc.groupby(CSCTR, dropna=False):
            proj  = len(g)
            inv   = g[CTRM].sum()
            lemp  = g[CLE].sum()
            femp  = g[CFE].sum()
            temp  = g[CTE].sum()
            mts_l = g[[CMGL, CPTL, CCKL]].sum().sum()
            mts_f = g[[CMGF, CPTF, CCKF]].sum().sum()
            mts_t = g[[CMGT, CPTT, CCKT]].sum().sum()
            s5    = sum(g[b[1]].sum() for b in SAL[2:])
            bands = [g[b[1]].sum() for b in SAL]
            rows_d.append((sub, proj, inv, temp, lemp, femp, mts_l, mts_f, mts_t, s5, bands))
        rows_d.sort(key=lambda x: x[2], reverse=True)

        total_n   = n or 1
        total_inv = ic or 1

        # Table A: Projects & Employment
        story.append(stat_line(f"A   Projects & Employment by Sector"))
        story.append(Spacer(1, 0.1*cm))

        hdr_a = ['Sector', 'Projects', '% Proj', 'Investment\n(RM bil)', '% Investment',
                 'Total\nEmployment', 'Local\nEmployment', 'Local %', 'Foreign\nEmployment', 'Foreign %']
        rows_a = [hdr_a]
        for r in rows_d:
            rows_a.append([
                str(r[0])[:32],
                fn(r[1]),  fp(sd(r[1], total_n)*100),
                fb(r[2]),  fp(sd(r[2], total_inv)*100),
                fn(r[3]),  fn(r[4]),  fp(sd(r[4], r[3])*100),
                fn(r[5]),  fp(sd(r[5], r[3])*100),
            ])
        rows_a.append([
            'TOTAL', fn(n), '100.0%', fb(ic), '100.0%',
            fn(ec), fn(lec), fp(sd(lec, ec)*100),
            fn(fec), fp(sd(fec, ec)*100),
        ])
        cw_a = _cw(5.0, 1.6, 1.3, 2.2, 1.3, 2.0, 2.0, 1.5, 2.0, 1.5)
        story.append(dtable(rows_a, cw_a))

        story.append(Spacer(1, 0.3*cm))

        # Table B: MTS & Salary
        story.append(stat_line(f"B   MTS & Salary by Sector"))
        story.append(Spacer(1, 0.1*cm))

        hdr_b = ['Sector', 'MTS\nLocal', 'MTS\nForeign', 'MTS\nTotal', 'MTS %',
                 '>=RM5K', '>=RM5K %',
                 '<RM3K', 'RM3K-5K', 'RM5K-10K', '>=RM10K']
        rows_b = [hdr_b]
        for r in rows_d:
            temp    = r[3]
            s5      = r[9]
            bands_t = r[10]
            rows_b.append([
                str(r[0])[:32],
                fn(r[6]),  fn(r[7]),  fn(r[8]),  fp(sd(r[8], temp)*100),
                fn(s5),    fp(sd(s5, temp)*100),
                fn(bands_t[0]), fn(bands_t[1]), fn(bands_t[2]), fn(bands_t[3]),
            ])
        mts_lt = sc[[CMGL, CPTL, CCKL]].sum().sum()
        mts_ft = sc[[CMGF, CPTF, CCKF]].sum().sum()
        mts_tt = sc[[CMGT, CPTT, CCKT]].sum().sum()
        s5t    = sum(sc[b[1]].sum() for b in SAL[2:])
        tsal   = [sc[b[1]].sum() for b in SAL]
        rows_b.append([
            'TOTAL',
            fn(mts_lt), fn(mts_ft), fn(mts_tt), fp(sd(mts_tt, ec)*100),
            fn(s5t),    fp(sd(s5t, ec)*100),
            fn(tsal[0]), fn(tsal[1]), fn(tsal[2]), fn(tsal[3]),
        ])
        cw_b = _cw(5.0, 1.8, 1.8, 1.8, 1.4, 1.8, 1.4, 1.6, 1.6, 1.8, 1.8)
        story.append(dtable(rows_b, cw_b))


def sec_top5(story, cur, year, pl):
    story.append(PageBreak())
    story.append(TocEntry(0, f'7.  Top 10 Projects by Investment  —  {pl} {year}'))
    story.append(sec_bar(f'7.  TOP 10 PROJECTS BY INVESTMENT  —  {pl} {year}'))
    story.append(Spacer(1, 0.15*cm))

    top10 = cur.nlargest(10, CTRM).copy()

    story.append(stat_line(
        f"Top 10 projects by Total Investment  |  "
        f"Combined Investment: {fmt_rm(top10[CTRM].sum())}  |  "
        f"Combined Emp: {fn(top10[CTE].sum())}"
    ))
    story.append(Spacer(1, 0.15*cm))

    hdr = ['No.', 'Company Name', 'Date\nApproved', 'Sector', 'State', 'Ultimate\nCountry',
           'Product / Activity', 'Total\nInvestment (RM bil)']
    rows = [hdr]
    for i, (_, r) in enumerate(top10.iterrows(), 1):
        date_str = r[CD].strftime('%d %b %Y') if pd.notna(r[CD]) else '-'
        rows.append([
            str(i),
            str(r[CNAM]),
            date_str,
            str(r[CSCTR]),
            str(r[CSTA]),
            str(r[CCNT]),
            str(r[CPACT]),
            fb(r[CTRM]),
        ])

    cw = _cw(0.7, 5.0, 2.0, 3.0, 2.0, 2.5, 7.5, 2.3)
    story.append(dtable(rows, cw))


def sec_nia(story, cur, prev, year, pl):
    """Section 8: National Investment Aspirations (NIA) — E&E, Pharmaceutical, Aerospace, Chemical."""
    story.append(PageBreak())
    story.append(TocEntry(0, f'8.  National Investment Aspirations (NIA)  —  {pl} {year} vs {year-1}'))
    story.append(sec_bar(f'8.  NATIONAL INVESTMENT ASPIRATIONS (NIA)  —  {pl}  {year} vs {year-1}'))
    story.append(Spacer(1, 0.15*cm))

    # ── NIA sector filters ──────────────────────────────────────────────────
    def _ee(df):
        return df[df[CSCTR].str.contains('Electrical', case=False, na=False)]

    def _ph(df):
        return df[df[CSCTR].str.contains('Pharma', case=False, na=False)]

    def _ae(df):
        return df[df[CSCTR].str.contains('Aerospace', case=False, na=False)]

    def _ch(df):
        chem = df[CSCTR].str.contains('Chemical', case=False, na=False)
        if CSUB in df.columns:
            pharma_sub = df[CSUB].str.contains('Pharma', case=False, na=False)
            return df[chem & ~pharma_sub]
        return df[chem]

    NIA_DEFS = [
        ('Electrical &\nElectronic', _ee),
        ('Pharmaceutical', _ph),
        ('Aerospace', _ae),
        ('Chemical &\nChemical Products\n(excl. Pharma\nSub-Sector)', _ch),
    ]

    # ── YoY helpers: absolute change + % change ─────────────────────────────
    def _yoy_n(c, p):
        diff = c - p
        diff_s = fn(diff)
        if p == 0:
            pct_s = 'N/A' if c > 0 else '-'
        else:
            pct_v = (c - p) / abs(p) * 100
            pct_s = f"+{pct_v:.1f}%" if pct_v >= 0 else f"{pct_v:.1f}%"
        return (f"+{diff_s}\n({pct_s})" if diff >= 0 else f"{diff_s}\n({pct_s})")

    def _yoy_b(c, p):
        diff = c - p
        diff_s = fb(diff)
        if p == 0:
            pct_s = 'N/A' if c > 0 else '-'
        else:
            pct_v = (c - p) / abs(p) * 100
            pct_s = f"+{pct_v:.1f}%" if pct_v >= 0 else f"{pct_v:.1f}%"
        return (f"+{diff_s}\n({pct_s})" if diff >= 0 else f"{diff_s}\n({pct_s})")

    # ── Aggregate per NIA sector ────────────────────────────────────────────
    rows_agg = []
    for label, flt in NIA_DEFS:
        c = flt(cur)
        p = flt(prev)
        proj_c = len(c);        proj_p = len(p)
        emp_c  = c[CTE].sum();  emp_p  = p[CTE].sum()
        dom_c  = c[CDRM].sum(); dom_p  = p[CDRM].sum()
        for_c  = c[CFRM].sum(); for_p  = p[CFRM].sum()
        tot_c  = c[CTRM].sum(); tot_p  = p[CTRM].sum()
        va_c   = c[CVA].mean()  if len(c) > 0 else 0.0
        mts_c  = c[[CMGT, CPTT, CCKT]].sum().sum()
        cipe_c = sd(tot_c, emp_c)
        sal5l  = sum(c[b[2]].sum() for b in SAL[2:])
        sal5f  = sum(c[b[3]].sum() for b in SAL[2:])
        rows_agg.append(dict(
            label=label,
            proj_c=proj_c, proj_p=proj_p,
            emp_c=emp_c,   emp_p=emp_p,
            dom_c=dom_c,   dom_p=dom_p,
            for_c=for_c,   for_p=for_p,
            tot_c=tot_c,   tot_p=tot_p,
            va_c=va_c, mts_c=mts_c, cipe_c=cipe_c,
            sal5l=sal5l, sal5f=sal5f,
        ))

    tot_proj_c = sum(r['proj_c'] for r in rows_agg)
    tot_proj_p = sum(r['proj_p'] for r in rows_agg)
    tot_emp_c  = sum(r['emp_c']  for r in rows_agg)
    tot_emp_p  = sum(r['emp_p']  for r in rows_agg)
    tot_dom_c  = sum(r['dom_c']  for r in rows_agg)
    tot_dom_p  = sum(r['dom_p']  for r in rows_agg)
    tot_for_c  = sum(r['for_c']  for r in rows_agg)
    tot_for_p  = sum(r['for_p']  for r in rows_agg)
    tot_tot_c  = sum(r['tot_c']  for r in rows_agg)
    tot_tot_p  = sum(r['tot_p']  for r in rows_agg)
    tot_mts_c  = sum(r['mts_c']  for r in rows_agg)
    tot_sal5l  = sum(r['sal5l']  for r in rows_agg)
    tot_sal5f  = sum(r['sal5f']  for r in rows_agg)
    tot_va_c   = (sum(r['va_c'] * r['proj_c'] for r in rows_agg) / tot_proj_c) if tot_proj_c else 0.0
    tot_cipe_c = sd(tot_tot_c, tot_emp_c)

    story.append(stat_line(
        f"NIA Sectors: Electrical & Electronic  |  Pharmaceutical  |  Aerospace  |  Chemical (excl. Pharma Sub-Sector)  |  "
        f"Total NIA Projects {year}: {fn(tot_proj_c)}  |  Investment: {fmt_rm(tot_tot_c)}  |  "
        f"Employment: {fn(tot_emp_c)}  |  YoY Projects: {yoy_str(tot_proj_c, tot_proj_p)}"
    ))
    story.append(Spacer(1, 0.25*cm))

    # ── 8A: Projects & Employment ────────────────────────────────────────────
    story.append(TocEntry(1, '8A  Projects & Employment'))
    story.append(stat_line(f"8A   Projects & Employment  —  Year-on-Year Comparison"))
    story.append(Spacer(1, 0.1*cm))

    hdr_a = ['NIA Sector',
             f'No. of Projects\n{year}', f'No. of Projects\n{year-1}', 'YoY Change\n(n  &  %)',
             f'Total Employment\n{year}', f'Total Employment\n{year-1}', 'YoY Change\n(n  &  %)']
    rows_a = [hdr_a]
    for r in rows_agg:
        rows_a.append([
            r['label'],
            fn(r['proj_c']), fn(r['proj_p']), _yoy_n(r['proj_c'], r['proj_p']),
            fn(r['emp_c']),  fn(r['emp_p']),  _yoy_n(r['emp_c'],  r['emp_p']),
        ])
    rows_a.append([
        'TOTAL (NIA)',
        fn(tot_proj_c), fn(tot_proj_p), _yoy_n(tot_proj_c, tot_proj_p),
        fn(tot_emp_c),  fn(tot_emp_p),  _yoy_n(tot_emp_c,  tot_emp_p),
    ])
    cw_a = _cw(4.5, 2.2, 2.2, 2.8, 2.5, 2.5, 2.8)
    story.append(dtable(rows_a, cw_a))
    story.append(Spacer(1, 0.35*cm))

    # ── 8B: Investment ───────────────────────────────────────────────────────
    story.append(TocEntry(1, '8B  Investment'))
    story.append(stat_line(f"8B   Investment (RM bil)  —  Year-on-Year Comparison"))
    story.append(Spacer(1, 0.1*cm))

    hdr_b = ['NIA Sector',
             f'Domestic Inv.\n{year} (RM bil)', f'Domestic Inv.\n{year-1} (RM bil)', 'YoY Dom.\n(bil  &  %)',
             f'Foreign Inv.\n{year} (RM bil)',   f'Foreign Inv.\n{year-1} (RM bil)',  'YoY For.\n(bil  &  %)',
             f'Total Inv.\n{year} (RM bil)',      f'Total Inv.\n{year-1} (RM bil)',    'YoY Total\n(bil  &  %)']
    rows_b = [hdr_b]
    for r in rows_agg:
        rows_b.append([
            r['label'],
            fb(r['dom_c']), fb(r['dom_p']), _yoy_b(r['dom_c'], r['dom_p']),
            fb(r['for_c']), fb(r['for_p']), _yoy_b(r['for_c'], r['for_p']),
            fb(r['tot_c']), fb(r['tot_p']), _yoy_b(r['tot_c'], r['tot_p']),
        ])
    rows_b.append([
        'TOTAL (NIA)',
        fb(tot_dom_c), fb(tot_dom_p), _yoy_b(tot_dom_c, tot_dom_p),
        fb(tot_for_c), fb(tot_for_p), _yoy_b(tot_for_c, tot_for_p),
        fb(tot_tot_c), fb(tot_tot_p), _yoy_b(tot_tot_c, tot_tot_p),
    ])
    cw_b = _cw(4.0, 1.8, 1.8, 2.5, 1.8, 1.8, 2.5, 1.8, 1.8, 2.5)
    story.append(dtable(rows_b, cw_b))

    # ── 8C: Additional Metrics (no YoY) ─────────────────────────────────────
    story.append(PageBreak())
    story.append(TocEntry(1, '8C  Value Added, MTS, CIPE & Salary >RM5,000'))
    story.append(sec_bar(f'8.  NIA — ADDITIONAL METRICS  |  {pl}  {year}'))
    story.append(Spacer(1, 0.15*cm))
    story.append(stat_line(
        f"8C   Additional Metrics — Avg Value Added, MTS Workers, CIPE, Salary >RM5,000 (Local & Foreign)  |  No YoY comparison"
    ))
    story.append(Spacer(1, 0.15*cm))

    hdr_c = ['NIA Sector',
             'Avg Value\nAdded (%)',
             'MTS Workers\n(Total)', 'MTS\nRatio (%)',
             'CIPE\n(RM/Worker)',
             'Salary >RM5K\n(Local)', 'Salary >RM5K\n(Foreign)']
    rows_c = [hdr_c]
    cipe_ora = []
    for i, r in enumerate(rows_agg):
        rows_c.append([
            r['label'],
            fp(r['va_c']),
            fn(r['mts_c']), fp(sd(r['mts_c'], r['emp_c']) * 100),
            fmt_rm(r['cipe_c']),
            fn(r['sal5l']), fn(r['sal5f']),
        ])
        cipe_ora.append((i + 1, 4))
    rows_c.append([
        'TOTAL (NIA)',
        fp(tot_va_c),
        fn(tot_mts_c), fp(sd(tot_mts_c, tot_emp_c) * 100),
        fmt_rm(tot_cipe_c),
        fn(tot_sal5l), fn(tot_sal5f),
    ])
    cipe_ora.append((len(rows_agg) + 1, 4))
    cw_c = _cw(5.0, 2.5, 2.5, 2.5, 3.5, 3.0, 3.0)
    story.append(dtable(rows_c, cw_c, cipe_ora))


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  MIDA Manufacturing Investment Report Generator")
    print("=" * 60)

    # Find Excel file
    xlsx_files = [f for f in os.listdir('.') if f.endswith('.xlsx')]
    if not xlsx_files:
        print("\nNo .xlsx file found in current folder.")
        path = input("Enter full path to Excel file: ").strip().strip('"')
    elif len(xlsx_files) == 1:
        path = xlsx_files[0]
        print(f"\nUsing: {path}")
    else:
        print("\nMultiple Excel files found:")
        for i, f in enumerate(xlsx_files, 1):
            print(f"  {i}. {f}")
        choice = input("Select file number: ").strip()
        path = xlsx_files[int(choice)-1]

    if not os.path.exists(path):
        print(f"File not found: {path}"); return

    # Load data
    print("\nLoading data...")
    df = load_excel(path)
    mfg = df[df[CSEC]=='Manufacturing']
    avail_years = sorted(mfg['_y'].dropna().unique().astype(int), reverse=True)
    print(f"  Manufacturing projects found: {len(mfg):,}")
    print(f"  Available years: {', '.join(map(str, avail_years))}")

    # Year
    print(f"\nSelect year (default: {avail_years[0]}):")
    yr_in = input("  Year: ").strip()
    year  = int(yr_in) if yr_in else avail_years[0]
    if year not in avail_years:
        print(f"  No data for {year}. Available: {avail_years}"); return

    # Period
    print("\nSelect period:")
    for k, (lbl, _) in PERIODS.items():
        print(f"  {k}. {lbl}")
    per_in = input("  Choice (default: 4): ").strip() or '4'
    if per_in not in PERIODS:
        print("Invalid choice."); return
    pl, months = PERIODS[per_in]

    # Filter and check
    cur, prev = filt(df, year, months)
    print(f"\n  {year} ({pl}): {len(cur):,} projects")
    print(f"  {year-1} ({pl}): {len(prev):,} projects")

    # Output path
    ts   = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    name = f"MIDA_Manufacturing_{year}_{pl.split()[0]}_{ts}.pdf"
    out  = os.path.join(os.path.dirname(os.path.abspath(path)), name)

    # Generate
    print(f"\nGenerating PDF...")
    story = []
    doc = SimpleDocTemplate(out, pagesize=landscape(A4),
                            leftMargin=MAR, rightMargin=MAR,
                            topMargin=1.2*cm, bottomMargin=1.8*cm,
                            title=f'MIDA Manufacturing {year}', author='MIDA')

    prev_pl, prev_qoq = filt_qoq(df, year, months)
    sec_cover(story, year, pl)
    sec_toc(story, year, pl)
    print("  [1] YoY Summary...")
    sec_yoy(story, cur, prev, year, pl)
    print("  [1B] QoQ Summary...")
    sec_qoq(story, cur, prev_qoq, year, pl, prev_pl)
    print("  [2] Sector Overview...")
    sec_overview(story, cur, prev, year, pl)
    print("  [2E] CIPE by Sector...")
    sec_cipe(story, cur, year, pl)
    print("  [3] Employment by Category...")
    sec_emp_category(story, cur, prev, year, pl)
    print("  [3A] MTS Breakdown...")
    sec_mts(story, cur, prev, year, pl)
    print("  [3B-3C] MTS Local & Foreign...")
    sec_mts_local_foreign(story, cur, prev, year, pl)
    print("  [3D] Salary Breakdown...")
    sec_salary(story, cur, prev, year, pl)
    print("  [3E-3F] Salary Local & Foreign...")
    sec_salary_local_foreign(story, cur, prev, year, pl)
    print("  [4A] Export Analysis...")
    sec_export(story, cur, prev, year, pl)
    print("  [4B] Raw Materials...")
    sec_rawmat(story, cur, prev, year, pl)
    print("  [4C] Industry 4.0...")
    sec_i40(story, cur, prev, year, pl)
    print("  [4D] Indicators...")
    sec_indicators(story, cur, prev, year, pl)
    print("  [4E] Green Investment...")
    sec_green(story, cur, prev, year, pl)
    print("  [5A] State...")
    sec_state(story, cur, prev, year, pl)
    print("  [5B] LDS State...")
    sec_lds_state(story, cur, prev, year, pl)
    print("  [5C] Top State Breakdown...")
    sec_state_top3(story, cur, prev, year, pl)
    print("  [6] Country...")
    sec_country(story, cur, prev, year, pl)
    print("  [7] Top 10 Projects...")
    sec_top5(story, cur, year, pl)
    print("  [8] National Investment Aspirations (NIA)...")
    sec_nia(story, cur, prev, year, pl)

    footer = footer_fn(year, pl)
    doc.multiBuild(story, onFirstPage=footer, onLaterPages=footer)

    print(f"\nDone! PDF saved:")
    print(f"  {out}")

    ans = input("\nOpen PDF now? (y/n, default y): ").strip().lower()
    if ans != 'n':
        os.startfile(out)


if __name__ == '__main__':
    import traceback
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled.")
    except Exception:
        traceback.print_exc()
    input("\nPress Enter to close...")
