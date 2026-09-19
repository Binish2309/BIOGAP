"""
src/visualization/theme.py

Shared visual identity applied by every page. Goals, in priority order:
  1. Don't look like a default Streamlit app (hide Streamlit's own chrome,
     restyle its native widgets to match our palette instead of fighting
     them with overrides everywhere).
  2. One consistent, deliberate visual language -- palette, type pairing,
     spacing, and a real logo mark -- shared with charts.py and maps.py.
  3. A small set of reusable components (hero, pill, metric card, detail
     disclosure) so every page composes the same way instead of each page
     hand-rolling its own HTML.
"""

from __future__ import annotations

import streamlit as st

PALETTE = {
    "forest": "#2E5339",
    "forest_dark": "#1F3D2B",
    "sage": "#74A57F",
    "slate": "#3E5C76",
    "sand": "#F2E9DC",
    "sand_deep": "#E5DFD3",
    "clay": "#B0813E",
    "rust": "#B0413E",
    "ink": "#232323",
    "ink_soft": "#5B5B5B",
    "paper": "#FBF9F5",
}

LOGO_SVG = """
<svg width="30" height="30" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
  <circle cx="20" cy="20" r="19" stroke="#F2E9DC" stroke-width="1.4" opacity="0.55"/>
  <path d="M20 6 C11 12, 9 20, 20 34 C31 20, 29 12, 20 6 Z" fill="#74A57F" opacity="0.9"/>
  <path d="M20 10 L20 30 M20 16 L14 12 M20 20 L27 15 M20 25 L14 22" stroke="#1F3D2B" stroke-width="1.1" stroke-linecap="round"/>
</svg>
"""

CUSTOM_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700&family=Inter:wght@400;500;600;700&display=swap');

/* ---------- Hide Streamlit's own chrome (but keep sidebar toggle!) ---------- */
#MainMenu {{ visibility: hidden; }}
footer {{ visibility: hidden; }}
.stDeployButton {{ display: none !important; }}
a[href*="streamlit.io"] {{ display: none !important; }}

/* The sidebar expand/collapse arrow lives in the same header region as the
   elements above -- force it to stay visible regardless, since on mobile
   the sidebar starts collapsed and this arrow is the ONLY way to open it
   and reach any page other than the landing page. */
[data-testid="collapsedControl"] {{
    visibility: visible !important;
    display: flex !important;
}}
[data-testid="stSidebarCollapseButton"] {{
    visibility: visible !important;
    display: flex !important;
}}

/* ---------- Base type & surface ---------- */
html, body, [class*="css"] {{
    font-family: 'Inter', -apple-system, sans-serif;
    color: {PALETTE['ink']};
}}
.stApp {{
    background-color: {PALETTE['paper']};
    background-image: radial-gradient(circle at 1px 1px, {PALETTE['sand_deep']} 1px, transparent 0);
    background-size: 28px 28px;
}}
.block-container {{
    padding-top: 1.6rem;
    max-width: 1100px;
}}

h1, h2, h3 {{
    font-family: 'Fraunces', Georgia, serif !important;
    font-weight: 600 !important;
    color: {PALETTE['forest']} !important;
    letter-spacing: -0.01em;
}}
h2 {{ font-size: 1.4rem !important; margin-top: 0.4rem !important; }}
h3 {{ font-size: 1.1rem !important; }}
p, li, .stMarkdown {{ color: {PALETTE['ink']}; line-height: 1.55; }}

/* ---------- Sidebar ---------- */
[data-testid="stSidebar"] {{
    background-color: {PALETTE['forest']};
    background-image: linear-gradient(180deg, {PALETTE['forest']} 0%, {PALETTE['forest_dark']} 100%);
}}
[data-testid="stSidebar"] * {{ color: {PALETTE['sand']} !important; }}
[data-testid="stSidebar"] hr {{ border-color: rgba(242,233,220,0.2); }}
[data-testid="stSidebarNav"] a {{
    border-radius: 8px;
    transition: background-color 0.15s ease;
}}
[data-testid="stSidebarNav"] a:hover {{ background-color: rgba(242,233,220,0.12); }}
[data-testid="stSidebarNav"] a[aria-current="page"] {{
    background-color: rgba(242,233,220,0.18);
    font-weight: 600;
}}

/* ---------- Buttons ---------- */
.stButton > button {{
    border-radius: 8px;
    border: 1px solid {PALETTE['forest']};
    font-weight: 500;
    transition: transform 0.08s ease, box-shadow 0.15s ease;
}}
.stButton > button[kind="primary"] {{
    background-color: {PALETTE['forest']};
    border-color: {PALETTE['forest']};
}}
.stButton > button[kind="primary"]:hover {{
    background-color: {PALETTE['forest_dark']};
    box-shadow: 0 3px 10px rgba(46,83,57,0.25);
    transform: translateY(-1px);
}}
.stButton > button:not([kind="primary"]):hover {{
    border-color: {PALETTE['sage']};
    color: {PALETTE['forest']};
    transform: translateY(-1px);
}}

/* ---------- Tabs ---------- */
.stTabs [data-baseweb="tab-list"] {{ gap: 4px; }}
.stTabs [data-baseweb="tab"] {{
    border-radius: 8px 8px 0 0;
    font-weight: 500;
    color: {PALETTE['ink_soft']};
}}
.stTabs [aria-selected="true"] {{ color: {PALETTE['forest']} !important; }}

/* ---------- Metrics ---------- */
[data-testid="stMetric"] {{
    background: white;
    border: 1px solid {PALETTE['sand_deep']};
    border-radius: 12px;
    padding: 0.8rem 1rem;
}}
[data-testid="stMetricLabel"] {{ color: {PALETTE['ink_soft']} !important; }}
[data-testid="stMetricValue"] {{ color: {PALETTE['forest']} !important; font-family: 'Fraunces', serif; }}

/* ---------- Custom components ---------- */
.biogap-topbar {{
    display: flex; align-items: center; gap: 10px;
    margin-bottom: 0.6rem;
}}
.biogap-topbar span {{
    font-family: 'Fraunces', serif; font-weight: 600; font-size: 1.05rem;
    color: {PALETTE['forest']}; letter-spacing: 0.01em;
}}

.biogap-hero {{
    padding: 2.2rem 2rem;
    border-radius: 16px;
    background: linear-gradient(140deg, {PALETTE['forest']} 0%, {PALETTE['forest_dark']} 55%, {PALETTE['slate']} 100%);
    color: {PALETTE['sand']} !important;
    margin-bottom: 1.4rem;
    box-shadow: 0 8px 24px rgba(31,61,43,0.18);
}}
.biogap-hero h1 {{
    color: {PALETTE['sand']} !important;
    font-size: 1.9rem !important;
    margin: 0 0 0.4rem 0 !important;
    line-height: 1.25;
}}
.biogap-hero p {{
    color: {PALETTE['sand']} !important;
    font-size: 1rem;
    opacity: 0.9;
    margin: 0;
}}

.biogap-status-pill {{
    display: inline-flex; align-items: center; gap: 6px;
    padding: 0.3rem 0.9rem;
    border-radius: 999px;
    font-size: 0.82rem;
    font-weight: 600;
    margin-bottom: 0.6rem;
}}
.biogap-status-ok {{ background-color: {PALETTE['sage']}; color: #103018; }}
.biogap-status-pending {{ background-color: {PALETTE['clay']}; color: #2B1D08; }}
.biogap-status-failed {{ background-color: {PALETTE['rust']}; color: #FBF9F5; }}

.biogap-card {{
    background-color: white;
    border: 1px solid {PALETTE['sand_deep']};
    border-radius: 12px;
    padding: 1.1rem 1.3rem;
    margin-bottom: 0.9rem;
    transition: box-shadow 0.15s ease;
}}
.biogap-card:hover {{ box-shadow: 0 4px 16px rgba(46,83,57,0.08); }}

.biogap-note {{
    border-left: 3px solid {PALETTE['clay']};
    background: #FBF3E6;
    border-radius: 0 8px 8px 0;
    padding: 0.55rem 0.85rem;
    font-size: 0.86rem;
    color: #5A4A2E;
    margin: 0.5rem 0;
}}

.biogap-label-implemented {{ color: {PALETTE['forest']}; font-weight: 600; }}
.biogap-label-proposed {{ color: {PALETTE['clay']}; font-weight: 600; }}
.biogap-label-notvalidated {{ color: {PALETTE['rust']}; font-weight: 600; }}

code, .stCode, [data-testid="stCaptionContainer"] code {{
    background: {PALETTE['sand']} !important;
    color: {PALETTE['forest_dark']} !important;
    border-radius: 4px;
}}
</style>
"""


def inject_theme() -> None:
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def topbar(page_label: str) -> None:
    """Small persistent brand mark at the top of every page (not just the
    hero on Overview), so the app reads as one product while navigating."""
    st.markdown(
        f'<div class="biogap-topbar">{LOGO_SVG}<span>BIOGAP</span></div>',
        unsafe_allow_html=True,
    )


def hero(title: str, subtitle: str) -> None:
    st.markdown(
        f"""<div class="biogap-hero">{LOGO_SVG}<h1 style="margin-top:0.6rem;">{title}</h1><p>{subtitle}</p></div>""",
        unsafe_allow_html=True,
    )


def status_pill(text: str, kind: str = "pending") -> None:
    css_class = {"ok": "biogap-status-ok", "pending": "biogap-status-pending",
                 "failed": "biogap-status-failed"}.get(kind, "biogap-status-pending")
    st.markdown(f'<span class="biogap-status-pill {css_class}">{text}</span>', unsafe_allow_html=True)


def note(text: str) -> None:
    """A short, quiet inline caveat -- for the ONE sentence that matters on
    a page, not a paragraph. Use `detail()` for anything longer."""
    st.markdown(f'<div class="biogap-note">{text}</div>', unsafe_allow_html=True)


def detail(label_text: str, body_markdown: str) -> None:
    """Collapsed-by-default disclosure for methodology caveats and other
    detail that shouldn't clutter the main page but must stay one tap away.
    Use instead of always-visible paragraphs of caveat text."""
    with st.expander(label_text, expanded=False):
        st.markdown(body_markdown)


def label(text: str, kind: str) -> str:
    """Inline HTML span for IMPLEMENTED / PROPOSED / NOT_YET_VALIDATED labels
    used throughout the Methodology page."""
    css_class = {
        "IMPLEMENTED": "biogap-label-implemented",
        "IMPLEMENTED_DESCRIPTIVE": "biogap-label-implemented",
        "PROPOSED": "biogap-label-proposed",
        "NOT_YET_VALIDATED": "biogap-label-notvalidated",
        "NOT_IMPLEMENTED": "biogap-label-notvalidated",
    }.get(kind, "biogap-label-proposed")
    return f'<span class="{css_class}">[{kind}]</span> {text}'
