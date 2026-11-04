import streamlit as st


def apply_styles() -> None:
    st.markdown("""
    <style>
      .block-container {max-width: 1440px; padding-top: 1.6rem; padding-bottom: 3rem;}
      [data-testid="stMetric"] {background: var(--secondary-background-color); padding: 16px; border-radius: 14px;}
      .small-muted {color: var(--text-color); opacity: .72; font-size: .88rem;}
      .source-card {border: 1px solid rgba(128,128,128,.25); border-radius: 12px; padding: 14px; margin: 8px 0;}
      div[data-testid="stExpander"] {border-radius: 12px;}
    </style>
    """, unsafe_allow_html=True)
