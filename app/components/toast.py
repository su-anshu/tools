"""
Toast Notification System
"""
import streamlit as st
from typing import Optional
import time

def show_toast(
    message: str,
    toast_type: str = "success",
    duration: int = 5000,
    icon: Optional[str] = None
):
    """
    Display toast notification
    
    Args:
        message: Toast message
        toast_type: "success", "error", "warning", "info"
        duration: Auto-dismiss duration in milliseconds
        icon: Optional icon emoji
    """
    # Define toast styles
    styles = {
        "success": {
            "bg": "rgba(129, 199, 132, 0.95)",
            "border": "#81C784",
            "icon": "✅",
            "text_color": "white"
        },
        "error": {
            "bg": "rgba(229, 115, 115, 0.95)",
            "border": "#E57373",
            "icon": "❌",
            "text_color": "white"
        },
        "warning": {
            "bg": "rgba(255, 183, 77, 0.95)",
            "border": "#FFB74D",
            "icon": "⚠️",
            "text_color": "white"
        },
        "info": {
            "bg": "rgba(100, 181, 246, 0.95)",
            "border": "#64B5F6",
            "icon": "ℹ️",
            "text_color": "white"
        }
    }
    
    style = styles.get(toast_type, styles["info"])
    display_icon = icon if icon else style["icon"]
    
    # Generate unique key for this toast
    toast_id = f"toast_{int(time.time() * 1000)}"
    
    st.markdown(f"""
    <div id="{toast_id}" style="position: fixed;
                                top: 20px;
                                right: 20px;
                                background: {style['bg']};
                                border-left: 4px solid {style['border']};
                                color: {style['text_color']};
                                padding: 1rem 1.5rem;
                                border-radius: 8px;
                                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                                z-index: 9999;
                                min-width: 300px;
                                max-width: 500px;
                                animation: slideIn 0.3s ease-out;
                                display: flex;
                                align-items: center;
                                gap: 0.75rem;">
        <span style="font-size: 1.5rem;">{display_icon}</span>
        <div style="flex: 1;">
            <strong>{message}</strong>
        </div>
        <button onclick="document.getElementById('{toast_id}').style.display='none'" 
                style="background: transparent;
                       border: none;
                       color: {style['text_color']};
                       font-size: 1.25rem;
                       cursor: pointer;
                       padding: 0;
                       margin-left: 0.5rem;">×</button>
    </div>
    <style>
        @keyframes slideIn {{
            from {{
                transform: translateX(100%);
                opacity: 0;
            }}
            to {{
                transform: translateX(0);
                opacity: 1;
            }}
        }}
    </style>
    <script>
        setTimeout(function() {{
            var toast = document.getElementById('{toast_id}');
            if (toast) {{
                toast.style.animation = 'slideOut 0.3s ease-out';
                setTimeout(function() {{ toast.style.display = 'none'; }}, 300);
            }}
        }}, {duration});
        @keyframes slideOut {{
            from {{
                transform: translateX(0);
                opacity: 1;
            }}
            to {{
                transform: translateX(100%);
                opacity: 0;
            }}
        }}
    </script>
    """, unsafe_allow_html=True)

