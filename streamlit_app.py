#!/usr/bin/env python3
"""
Streamlit App Entry Point for Mithila Tools Dashboard

This is the main entry point for deployment platforms like Streamlit Cloud.
"""

import streamlit as st
import logging
import sys
import os

# Setup paths
project_root = os.path.dirname(os.path.abspath(__file__))
app_dir = os.path.join(project_root, 'app')

# Add paths to sys.path
if project_root not in sys.path:
    sys.path.insert(0, project_root)
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)

# Change working directory to project root
os.chdir(project_root)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize default data files if missing (for deployment)
try:
    from app.default_data import ensure_data_files
    ensure_data_files()
except Exception as e:
    logger.warning(f"Could not initialize default data files: {e}")

# Configure Streamlit page
st.set_page_config(page_title="📦 Mithila Tools Dashboard", layout="wide")

# Inject custom CSS for smooth animations
try:
    from app.utils.ui_components import inject_custom_css
    inject_custom_css()
except Exception as e:
    logger.warning(f"Could not load custom CSS: {e}")

# Main dashboard
st.sidebar.title("🧰 Mithila Dashboard")

# Initialize session state for collapsible menu
if 'amazon_easy_ship_expanded' not in st.session_state:
    st.session_state.amazon_easy_ship_expanded = True  # Start expanded
if 'flipkart_expanded' not in st.session_state:
    st.session_state.flipkart_expanded = True  # Start expanded
if 'selected_tool' not in st.session_state:
    st.session_state.selected_tool = "Amazon Easy Ship > Amazon Packing Plan"

# Sidebar Navigation
# Note: app/main.py sidebar is disabled, so no duplicates will occur
# Amazon Easy Ship parent button with chevron
chevron_icon = "▼" if st.session_state.amazon_easy_ship_expanded else "▶"
is_amazon_selected = st.session_state.selected_tool.startswith("Amazon Easy Ship")
parent_button_type = "primary" if is_amazon_selected else "secondary"

# Parent button
if st.sidebar.button(f"📦 Amazon Easy Ship {chevron_icon}", use_container_width=True, type=parent_button_type, key="amazon_easy_ship_parent"):
    st.session_state.amazon_easy_ship_expanded = not st.session_state.amazon_easy_ship_expanded
    st.rerun()

# Sub-items (conditionally rendered - only when expanded)
if st.session_state.amazon_easy_ship_expanded:
    is_packing_selected = st.session_state.selected_tool == "Amazon Easy Ship > Amazon Packing Plan"
    is_report_selected = st.session_state.selected_tool == "Amazon Easy Ship > Easy Ship Report"
    
    if st.sidebar.button("  → Amazon Packing Plan", use_container_width=True, type="primary" if is_packing_selected else "secondary", key="amazon_packing_plan"):
        st.session_state.selected_tool = "Amazon Easy Ship > Amazon Packing Plan"
        st.rerun()
    
    if st.sidebar.button("  → Easy Ship Report", use_container_width=True, type="primary" if is_report_selected else "secondary", key="amazon_easy_ship_report"):
        st.session_state.selected_tool = "Amazon Easy Ship > Easy Ship Report"
        st.rerun()

# Flipkart group (after Amazon, before other tools)
flipkart_chevron = "▼" if st.session_state.flipkart_expanded else "▶"
is_flipkart_selected = st.session_state.selected_tool.startswith("🛒 Flipkart")
flipkart_button_type = "primary" if is_flipkart_selected else "secondary"

# Flipkart parent button
if st.sidebar.button(f"🛒 Flipkart {flipkart_chevron}", use_container_width=True, type=flipkart_button_type, key="flipkart_parent"):
    st.session_state.flipkart_expanded = not st.session_state.flipkart_expanded
    st.rerun()

# Flipkart sub-items (conditionally rendered - only when expanded)
if st.session_state.flipkart_expanded:
    is_flipkart_packing_selected = st.session_state.selected_tool == "🛒 Flipkart > Flipkart Packing Plan"
    is_flipkart_report_selected = st.session_state.selected_tool == "🛒 Flipkart > Report"
    
    if st.sidebar.button("  → Flipkart Packing Plan", use_container_width=True, type="primary" if is_flipkart_packing_selected else "secondary", key="flipkart_packing_plan"):
        st.session_state.selected_tool = "🛒 Flipkart > Flipkart Packing Plan"
        st.rerun()
    
    if st.sidebar.button("  → Report", use_container_width=True, type="primary" if is_flipkart_report_selected else "secondary", key="flipkart_report"):
        st.session_state.selected_tool = "🛒 Flipkart > Report"
        st.rerun()

# Other tools (Label Generator, Product Label Generator, Manual Plan)
is_label_selected = st.session_state.selected_tool == "Label Generator"
if st.sidebar.button("🏷️ Label Generator", use_container_width=True, type="primary" if is_label_selected else "secondary", key="label_generator"):
    st.session_state.selected_tool = "Label Generator"
    st.rerun()

is_product_label_selected = st.session_state.selected_tool == "Product Label Generator"
if st.sidebar.button("📋 Product Label Generator", use_container_width=True, type="primary" if is_product_label_selected else "secondary", key="product_label_generator"):
    st.session_state.selected_tool = "Product Label Generator"
    st.rerun()

is_manual_selected = st.session_state.selected_tool == "Manual Plan"
if st.sidebar.button("🔖 Manual Plan", use_container_width=True, type="primary" if is_manual_selected else "secondary", key="manual_plan"):
    st.session_state.selected_tool = "Manual Plan"
    st.rerun()

is_packed_unit_selected = st.session_state.selected_tool == "Packed Unit Stock"
if st.sidebar.button("📊 Packed Unit Stock", use_container_width=True, type="primary" if is_packed_unit_selected else "secondary", key="packed_unit_stock"):
    st.session_state.selected_tool = "Packed Unit Stock"
    st.rerun()

# Get the selected tool for loading
tool = st.session_state.selected_tool

# Tool loading with error handling
try:
    # Handle nested tool paths (e.g., "Amazon Easy Ship > Packing Plan")
    actual_tool = tool
    if " > " in tool:
        actual_tool = tool.split(" > ")[-1]
    
    # Map tool names to functions
    # Check Flipkart Packing Plan FIRST (before generic Packing Plan check)
    if (actual_tool in ["Packing Plan", "Flipkart Packing Plan"] and ("Flipkart" in tool or "🛒" in tool)) or tool == "🛒 Flipkart Packing Plan" or tool == "🛒 Flipkart > Flipkart Packing Plan":
        try:
            from app.tools.flipkart_packing_plan import flipkart_packing_plan_tool
            flipkart_packing_plan_tool()
        except ImportError as e:
            st.error(f"❌ **Module Error**: Could not load Flipkart Packing Plan Generator")
            st.error(f"**Details**: {str(e)}")
            st.info("💡 **Solution**: Ensure all dependencies are installed: `pip install -r requirements.txt`")
            logger.error(f"Import error in flipkart_packing_plan_tool: {str(e)}")
        except Exception as e:
            st.error(f"❌ **Runtime Error**: Error running Flipkart Packing Plan Generator")
            st.error(f"**Details**: {str(e)}")
            st.info("💡 **Solution**: Check your data files and try refreshing the page")
            logger.error(f"Runtime error in flipkart_packing_plan_tool: {str(e)}")

    elif (actual_tool in ["Packing Plan", "Amazon Packing Plan"] and ("Amazon" in tool or "📦" in tool)) or tool == "Amazon Easy Ship > Amazon Packing Plan" or tool == "Amazon Easy Ship > Packing Plan":
        try:
            from app.tools.packing_plan import packing_plan_tool
            packing_plan_tool()
        except ImportError as e:
            st.error(f"❌ **Module Error**: Could not load Packing Plan Generator")
            st.error(f"**Details**: {str(e)}")
            st.info("💡 **Solution**: Ensure all dependencies are installed: `pip install -r requirements.txt`")
            logger.error(f"Import error in packing_plan_tool: {str(e)}")
        except Exception as e:
            st.error(f"❌ **Runtime Error**: Error running Packing Plan Generator")
            st.error(f"**Details**: {str(e)}")
            st.info("💡 **Solution**: Check your data files and try refreshing the page")
            logger.error(f"Runtime error in packing_plan_tool: {str(e)}")

    elif actual_tool == "Easy Ship Report" or tool == "Amazon Easy Ship > Easy Ship Report":
        try:
            from app.tools.easy_ship_report import easy_ship_report
            easy_ship_report()
        except ImportError as e:
            st.error(f"❌ **Module Error**: Could not load Easy Ship Report Generator")
            st.error(f"**Details**: {str(e)}")
            st.info("💡 **Solution**: Ensure all dependencies are installed: `pip install -r requirements.txt`")
            logger.error(f"Import error in easy_ship_report: {str(e)}")
        except Exception as e:
            st.error(f"❌ **Runtime Error**: Error running Easy Ship Report Generator")
            st.error(f"**Details**: {str(e)}")
            st.info("💡 **Solution**: Check your shipping data format and try again")
            logger.error(f"Runtime error in easy_ship_report: {str(e)}")

    elif tool == "Label Generator":
        try:
            from app.tools.label_generator import label_generator_tool
            label_generator_tool()
        except ImportError as e:
            st.error(f"❌ **Module Error**: Could not load Label Generator")
            st.error(f"**Details**: {str(e)}")
            st.info("💡 **Solution**: Ensure all dependencies are installed: `pip install -r requirements.txt`")
            logger.error(f"Import error in label_generator_tool: {str(e)}")
        except Exception as e:
            st.error(f"❌ **Runtime Error**: Error running Label Generator")
            st.error(f"**Details**: {str(e)}")
            st.info("💡 **Solution**: Check your data files and font directory")
            logger.error(f"Runtime error in label_generator_tool: {str(e)}")

    elif tool == "Manual Plan":
        try:
            from app.tools.manual_packing_plan import manual_packing_plan
            manual_packing_plan()
        except ImportError as e:
            st.error(f"❌ **Module Error**: Could not load Manual Packing Plan Generator")
            st.error(f"**Details**: {str(e)}")
            st.info("💡 **Solution**: Ensure all dependencies are installed: `pip install -r requirements.txt`")
            logger.error(f"Import error in manual_packing_plan: {str(e)}")
        except Exception as e:
            st.error(f"❌ **Runtime Error**: Error running Manual Packing Plan Generator")
            st.error(f"**Details**: {str(e)}")
            st.info("💡 **Solution**: Check your Excel file format and data directory permissions")
            logger.error(f"Runtime error in manual_packing_plan: {str(e)}")

    elif tool == "Product Label Generator":
        try:
            from app.tools.product_label_generator import product_label_generator_tool
            product_label_generator_tool()
        except ImportError as e:
            st.error(f"❌ **Module Error**: Could not load Product Label Generator")
            st.error(f"**Details**: {str(e)}")
            st.info("💡 **Solution**: Ensure all dependencies are installed: `pip install -r requirements.txt`")
            logger.error(f"Import error in product_label_generator_tool: {str(e)}")
        except Exception as e:
            st.error(f"❌ **Runtime Error**: Error running Product Label Generator")
            st.error(f"**Details**: {str(e)}")
            st.info("💡 **Solution**: Check your data files and try refreshing the page")
            logger.error(f"Runtime error in product_label_generator_tool: {str(e)}")

    elif actual_tool == "Report" and "Flipkart" in tool:
        try:
            from app.tools.flipkart_report import flipkart_report
            flipkart_report()
        except ImportError as e:
            st.error(f"❌ **Module Error**: Could not load Flipkart Report Generator")
            st.error(f"**Details**: {str(e)}")
            st.info("💡 **Solution**: Ensure all dependencies are installed: `pip install -r requirements.txt`")
            logger.error(f"Import error in flipkart_report: {str(e)}")
        except Exception as e:
            st.error(f"❌ **Runtime Error**: Error running Flipkart Report Generator")
            st.error(f"**Details**: {str(e)}")
            st.info("💡 **Solution**: Check your Excel file format and try again")
            logger.error(f"Runtime error in flipkart_report: {str(e)}")

    elif tool == "Packed Unit Stock":
        try:
            from app.tools.packed_unit_stock import packed_unit_stock
            packed_unit_stock()
        except ImportError as e:
            st.error(f"❌ **Module Error**: Could not load Packed Unit Stock Processor")
            st.error(f"**Details**: {str(e)}")
            st.info("💡 **Solution**: Ensure all dependencies are installed: `pip install -r requirements.txt`")
            logger.error(f"Import error in packed_unit_stock: {str(e)}")
        except Exception as e:
            st.error(f"❌ **Runtime Error**: Error running Packed Unit Stock Processor")
            st.error(f"**Details**: {str(e)}")
            st.info("💡 **Solution**: Check your Excel/CSV file format and try again")
            logger.error(f"Runtime error in packed_unit_stock: {str(e)}")

except Exception as e:
    st.error(f"Unexpected error in main application: {str(e)}")
    logger.error(f"Unexpected error in main_app: {str(e)}")
    st.info("Please refresh the page and try again. If the problem persists, check the logs.")
