"""
Dashboard Header Component
"""
import streamlit as st
from datetime import datetime
from typing import Optional

def dashboard_header(
    title: str = "Mithila Tools Dashboard",
    subtitle: str = "Warehouse Management & Label Generation",
    connection_status: Optional[dict] = None
):
    """
    Display minimal dashboard header - simple and clean
    
    Args:
        title: Main dashboard title
        subtitle: Subtitle text (optional, shown small)
        connection_status: Optional dict with 'connected', 'product_count', 'last_sync'
    """
    # Minimal header - white background, simple border
    status_text = ""
    if connection_status:
        connected = connection_status.get('connected', False)
        product_count = connection_status.get('product_count', 0)
        if product_count:
            status_text = f'<span style="font-size: 0.75rem; color: #757575; margin-left: 0.5rem;">({product_count} products)</span>'
    
    st.markdown(f"""
    <div style="background: white;
                border-bottom: 2px solid #4CAF50;
                padding: 0.5rem 1rem;
                margin: -1rem -1rem 0.75rem -1rem;">
        <div style="display: flex; align-items: baseline; gap: 0.5rem;">
            <h1 style="color: #212121; margin: 0; font-size: 1.25rem; font-weight: 600;">
                {title}
            </h1>
            {status_text}
        </div>
        {f'<p style="color: #757575; margin: 0.25rem 0 0 0; font-size: 0.75rem;">{subtitle}</p>' if subtitle else ''}
    </div>
    """, unsafe_allow_html=True)

# Status badge removed - status shown inline in header

