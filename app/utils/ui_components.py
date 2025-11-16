"""
Reusable UI Components for Mithila Tools Dashboard
"""
import streamlit as st
from typing import Optional, Dict, Any

def inject_custom_css():
    """Inject custom CSS into Streamlit app"""
    import os
    
    # Get the project root directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(current_dir))
    
    css_paths = [
        os.path.join(project_root, "app", "assets", "custom.css"),
        os.path.join(current_dir, "..", "assets", "custom.css"),
        "app/assets/custom.css",
        os.path.join(os.getcwd(), "app", "assets", "custom.css"),
        "assets/custom.css"
    ]
    
    css_content = None
    loaded_path = None
    
    for path in css_paths:
        try:
            abs_path = os.path.abspath(path)
            if os.path.exists(abs_path):
                with open(abs_path, "r", encoding="utf-8") as f:
                    css_content = f.read()
                loaded_path = abs_path
                break
        except Exception as e:
            continue
    
    if css_content:
        # Inject CSS with high priority
        st.markdown(f"<style>{css_content}</style>", unsafe_allow_html=True)
    else:
        # Fallback with basic styling
        st.markdown("""
        <style>
        .main .block-container { 
            padding-top: 2rem; 
            padding-bottom: 2rem;
        }
        .stDownloadButton > button {
            background: linear-gradient(135deg, #4CAF50 0%, #66BB6A 100%);
            border: none;
            border-radius: 8px;
            padding: 0.75rem 1.5rem;
            color: white;
            font-weight: 600;
        }
        </style>
        """, unsafe_allow_html=True)

def status_badge(status: str, size: str = "normal") -> str:
    """
    Generate HTML for status badge
    
    Args:
        status: Status text
        size: "small", "normal", or "large"
    
    Returns:
        HTML string for badge
    """
    status_lower = status.lower()
    
    # Determine badge class based on status
    if "ready" in status_lower or "success" in status_lower or "✅" in status:
        badge_class = "status-ready"
        icon = "🟢"
    elif "warning" in status_lower or "missing" in status_lower or "⚠️" in status:
        badge_class = "status-warning"
        icon = "🟡"
    elif "error" in status_lower or "failed" in status_lower or "❌" in status:
        badge_class = "status-error"
        icon = "🔴"
    else:
        badge_class = "status-info"
        icon = "🔵"
    
    size_class = f"badge-{size}" if size != "normal" else ""
    
    return f'<span class="status-badge {badge_class} {size_class}">{icon} {status}</span>'

def metric_card(title: str, value: Any, icon: str = "📊", variant: str = "default", 
                delta: Optional[str] = None) -> str:
    """
    Generate HTML for minimal metric card - simple white card with border
    
    Args:
        title: Metric title
        value: Metric value
        icon: Optional icon emoji (not used in minimal version)
        variant: Not used in minimal version
        delta: Optional delta/change indicator
    
    Returns:
        HTML string for minimal metric card
    """
    delta_html = f'<p style="font-size: 0.7rem; color: #757575; margin-top: 0.25rem;">{delta}</p>' if delta else ""
    
    return f"""
    <div style="background: white;
                padding: 0.5rem;
                border: 1px solid #E0E0E0;
                border-radius: 4px;
                text-align: center;">
        <h3 style="margin: 0; font-size: 1.25rem; font-weight: 600; color: #212121;">{value}</h3>
        <p style="margin: 0.25rem 0 0 0; font-size: 0.75rem; color: #757575;">{title}</p>
        {delta_html}
    </div>
    """

def info_card(title: str, content: str, variant: str = "info") -> None:
    """
    Display styled info card
    
    Args:
        title: Card title
        content: Card content
        variant: "info", "success", "warning", "error"
    """
    # Define colors based on variant
    colors = {
        "info": {"bg": "rgba(100, 181, 246, 0.1)", "border": "#64B5F6"},
        "success": {"bg": "rgba(129, 199, 132, 0.1)", "border": "#81C784"},
        "warning": {"bg": "rgba(255, 183, 77, 0.1)", "border": "#FFB74D"},
        "error": {"bg": "rgba(229, 115, 115, 0.1)", "border": "#E57373"}
    }
    
    color = colors.get(variant, colors["info"])
    
    st.markdown(f"""
    <div style="background: {color['bg']};
                border-left: 4px solid {color['border']};
                padding: 1rem;
                border-radius: 8px;
                margin: 1rem 0;">
        <strong>{title}</strong><br>
        {content}
    </div>
    """, unsafe_allow_html=True)

def section_header(title: str, icon: str = "") -> None:
    """
    Display styled section header
    
    Args:
        title: Section title
        icon: Optional icon emoji
    """
    icon_html = f"{icon} " if icon else ""
    st.markdown(f"""
    <div class="section-header" style="border-left: 4px solid #4CAF50;
                                       padding-left: 1rem;
                                       margin: 2rem 0 1rem 0;
                                       font-weight: 600;
                                       color: #212121;">
        <h2 style="margin: 0; color: #212121; font-size: 1.75rem;">{icon_html}{title}</h2>
    </div>
    """, unsafe_allow_html=True)

def welcome_header(title: str, subtitle: str = "") -> None:
    """
    Display welcome header banner
    
    Args:
        title: Main title
        subtitle: Optional subtitle
    """
    subtitle_html = f'<p style="margin-top: 0.5rem; opacity: 0.95;">{subtitle}</p>' if subtitle else ""
    
    st.markdown(f"""
    <div class="welcome-header" style="background: linear-gradient(135deg, #4CAF50 0%, #66BB6A 100%);
                                       color: white;
                                       padding: 2rem;
                                       border-radius: 12px;
                                       margin-bottom: 2rem;
                                       box-shadow: 0 4px 12px rgba(0,0,0,0.15);">
        <h1 style="color: white; margin-bottom: 0.5rem; font-size: 2.5rem;">{title}</h1>
        {subtitle_html}
    </div>
    """, unsafe_allow_html=True)

def connection_badge(connected: bool, label: str, count: Optional[int] = None) -> str:
    """
    Generate connection status badge HTML
    
    Args:
        connected: Connection status
        label: Badge label
        count: Optional count to display
    
    Returns:
        HTML string for badge
    """
    status_class = "connected" if connected else "disconnected"
    icon = "🟢" if connected else "🟡"
    count_text = f" ({count})" if count is not None else ""
    
    return f"""
    <span class="connection-badge {status_class}">
        {icon} {label}{count_text}
    </span>
    """

def empty_state(icon: str, title: str, message: str) -> None:
    """
    Display empty state message
    
    Args:
        icon: Icon emoji
        title: Empty state title
        message: Empty state message
    """
    st.markdown(f"""
    <div class="empty-state">
        <div class="empty-state-icon">{icon}</div>
        <h3>{title}</h3>
        <p>{message}</p>
    </div>
    """, unsafe_allow_html=True)

def tool_card(icon: str, title: str, description: str, key: str, is_active: bool = False) -> bool:
    """
    Display tool selection card and return True if clicked - Simple version without description
    
    Args:
        icon: Icon emoji
        title: Tool title
        description: Tool description (not displayed, kept for compatibility)
        key: Unique key for button
        is_active: Whether this tool is currently active
    
    Returns:
        True if card/button was clicked
    """
    active_style = "border: 2px solid #4CAF50; background: rgba(76, 175, 80, 0.05);" if is_active else "border: 1px solid #E0E0E0;"
    
    st.markdown(f"""
    <div style="background: white;
                {active_style}
                border-radius: 8px;
                padding: 0.75rem;
                margin-bottom: 0.5rem;
                transition: all 0.3s ease;">
        <div style="display: flex; align-items: center; gap: 0.5rem;">
            <span style="font-size: 1.25rem;">{icon}</span>
            <span style="color: #212121; font-size: 0.9rem; font-weight: 500;">{title}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    clicked = st.button("Open", key=key, use_container_width=True, type="primary" if is_active else "secondary")
    return clicked

def section_divider() -> None:
    """Display minimal section divider"""
    st.markdown("---")

def custom_card(content: str) -> None:
    """
    Wrap content in custom card container
    
    Args:
        content: HTML content to wrap
    """
    st.markdown(f'<div class="custom-card">{content}</div>', unsafe_allow_html=True)

def amazon_easy_ship_dropdown(group_name: str, children: list, group_key: str) -> Optional[str]:
    """
    Render Amazon Easy Ship dropdown menu with Tailwind CSS styling
    
    Args:
        group_name: Name of the parent group (e.g., "Amazon Easy Ship")
        children: List of child tool names
        group_key: Unique key for the group
    
    Returns:
        Selected tool path (e.g., "Amazon Easy Ship > Packing Plan") or None
    """
    # Initialize expanded state
    expanded_key = f"{group_key}_expanded"
    if expanded_key not in st.session_state:
        st.session_state[expanded_key] = True  # Start expanded by default
    
    # Check if any child is currently selected
    current_tool = st.session_state.get('selected_tool', '')
    is_group_selected = any(f"{group_name} > {child}" == current_tool for child in children)
    
    # Auto-expand if a child is selected
    if is_group_selected and not st.session_state[expanded_key]:
        st.session_state[expanded_key] = True
    
    # Parent button - styled with Tailwind-inspired CSS
    chevron = "▼" if st.session_state[expanded_key] else "▶"
    parent_button_type = "primary" if is_group_selected else "secondary"
    
    # Parent toggle button - make it clearly visible
    parent_label = f"{group_name} {chevron}"
    
    if st.sidebar.button(parent_label, key=f"{group_key}_parent", use_container_width=True, type=parent_button_type):
        st.session_state[expanded_key] = not st.session_state[expanded_key]
        st.rerun()
    
    # Render submenu when expanded
    selected_child = None
    if st.session_state[expanded_key]:
        for child in children:
            child_path = f"{group_name} > {child}"
            is_child_active = current_tool == child_path
            
            # Style child button based on active state
            child_style = "primary" if is_child_active else "secondary"
            child_label = f"  → {child}"  # Indent with arrow for visibility
            
            if st.sidebar.button(child_label, key=f"{group_key}_{child}", use_container_width=True, type=child_style):
                selected_child = child_path
                st.session_state.selected_tool = child_path
                st.rerun()
    
    return selected_child

# ============================================================================
# Tailwind CSS Helper Functions for Sidebar
# ============================================================================

def tailwind_card(content: str, padding: str = "p-4", shadow: str = "shadow-sm", 
                  bg_color: str = "bg-white", border: str = "border border-gray-200", 
                  rounded: str = "rounded-lg", margin: str = "mb-4", 
                  hover: bool = True) -> str:
    """
    Generate Tailwind-styled card container
    
    Args:
        content: HTML content to wrap
        padding: Tailwind padding class (default: p-4)
        shadow: Tailwind shadow class (default: shadow-sm)
        bg_color: Tailwind background color class (default: bg-white)
        border: Tailwind border classes (default: border border-gray-200)
        rounded: Tailwind rounded class (default: rounded-lg)
        margin: Tailwind margin class (default: mb-4)
        hover: Add hover shadow effect (default: True)
    
    Returns:
        HTML string for Tailwind-styled card
    """
    hover_class = "hover:shadow-md transition-all duration-200 ease-in-out" if hover else ""
    return f'<div class="{bg_color} {border} {rounded} {padding} {shadow} {margin} {hover_class}">{content}</div>'

def tailwind_section_header(title: str, icon: str = "", size: str = "text-lg") -> str:
    """
    Generate Tailwind-styled section header
    
    Args:
        title: Section title
        icon: Optional icon emoji or HTML
        size: Tailwind text size class (default: text-lg)
    
    Returns:
        HTML string for section header
    """
    icon_html = f'<span class="mr-2">{icon}</span>' if icon else ""
    return f'''
    <div class="mb-4 mt-6">
        <h3 class="{size} font-semibold text-gray-900 flex items-center">
            {icon_html}{title}
        </h3>
    </div>
    '''

def tailwind_status_badge(text: str, status: str = "info", size: str = "text-xs") -> str:
    """
    Generate Tailwind-styled status badge
    
    Args:
        text: Badge text
        status: Status type - "success", "warning", "error", "info" (default: info)
        size: Tailwind text size class (default: text-xs)
    
    Returns:
        HTML string for status badge
    """
    status_colors = {
        "success": "bg-green-100 text-green-800 border-green-200",
        "warning": "bg-yellow-100 text-yellow-800 border-yellow-200",
        "error": "bg-red-100 text-red-800 border-red-200",
        "info": "bg-blue-100 text-blue-800 border-blue-200"
    }
    color_class = status_colors.get(status, status_colors["info"])
    return f'''
    <span class="inline-flex items-center px-2.5 py-0.5 rounded-full {size} font-medium border {color_class}">
        {text}
    </span>
    '''

def tailwind_input_group(label: str, input_html: str, help_text: str = "") -> str:
    """
    Generate Tailwind-styled input group with label
    
    Args:
        label: Input label
        input_html: HTML for the input field
        help_text: Optional help text
    
    Returns:
        HTML string for input group
    """
    help_html = f'<p class="mt-1 text-xs text-gray-500">{help_text}</p>' if help_text else ""
    return f'''
    <div class="mb-4">
        <label class="block text-sm font-medium text-gray-700 mb-2">{label}</label>
        {input_html}
        {help_html}
    </div>
    '''

def tailwind_divider() -> str:
    """Generate Tailwind-styled divider"""
    return '<div class="border-t border-gray-200 my-4"></div>'

def tailwind_info_text(text: str, icon: str = "", color: str = "text-gray-600") -> str:
    """
    Generate Tailwind-styled info text
    
    Args:
        text: Text content
        icon: Optional icon
        color: Tailwind text color class (default: text-gray-600)
    
    Returns:
        HTML string for info text
    """
    icon_html = f'<span class="mr-1">{icon}</span>' if icon else ""
    return f'<p class="text-sm {color} mt-2">{icon_html}{text}</p>'

def tailwind_success_message(text: str) -> str:
    """Generate Tailwind-styled success message"""
    return f'''
    <div class="bg-green-50 border border-green-200 rounded-lg p-3 mb-4">
        <p class="text-sm text-green-800 flex items-center">
            <span class="mr-2">✅</span>{text}
        </p>
    </div>
    '''

def tailwind_error_message(text: str) -> str:
    """Generate Tailwind-styled error message"""
    return f'''
    <div class="bg-red-50 border border-red-200 rounded-lg p-3 mb-4">
        <p class="text-sm text-red-800 flex items-center">
            <span class="mr-2">❌</span>{text}
        </p>
    </div>
    '''

def tailwind_warning_message(text: str) -> str:
    """Generate Tailwind-styled warning message"""
    return f'''
    <div class="bg-yellow-50 border border-yellow-200 rounded-lg p-3 mb-4">
        <p class="text-sm text-yellow-800 flex items-center">
            <span class="mr-2">⚠️</span>{text}
        </p>
    </div>
    '''

