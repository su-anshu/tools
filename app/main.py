import streamlit as st
import logging
import os

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Tailwind CSS
try:
    import st_tailwind as st_tw
    st_tw.initialize_tailwind()
    TAILWIND_AVAILABLE = True
except ImportError:
    TAILWIND_AVAILABLE = False
    logger.warning("st_tailwind not available, using fallback styling")

# Configure Streamlit page
st.set_page_config(
    page_title="📦 Mithila Tools Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items=None
)

# Inject custom CSS
try:
    from app.utils.ui_components import inject_custom_css
    inject_custom_css()
except Exception as e:
    logger.warning(f"Could not load custom CSS: {e}")

# Minimal Dashboard Header
try:
    from app.components.dashboard_header import dashboard_header
    from app.data_loader import load_master_data
    
    # Get connection status
    try:
        master_df = load_master_data()
        connection_status = {
            "connected": master_df is not None and not master_df.empty,
            "product_count": len(master_df) if master_df is not None else 0,
            "last_sync": None
        }
    except:
        connection_status = {"connected": False, "product_count": 0}
    
    dashboard_header(
        title="Mithila Tools Dashboard",
        subtitle="",
        connection_status=connection_status
    )
except Exception as e:
    logger.warning(f"Could not load dashboard header: {e}")
    st.markdown("### Mithila Tools Dashboard")

# Sidebar Navigation - DISABLED to prevent duplicates
# Sidebar navigation is rendered in streamlit_app.py (main entry point)
# This prevents duplicate buttons when both files are active
# To re-enable, uncomment the code below and ensure streamlit_app.py sidebar is disabled

# SIDEBAR_NAVIGATION_ENABLED = False  # Set to True to enable sidebar navigation here
SIDEBAR_NAVIGATION_ENABLED = False

if SIDEBAR_NAVIGATION_ENABLED:
    # Sidebar Navigation - Simple
    st.sidebar.markdown("### 🛠️ Tools")

    # Restructured tools dictionary with support for groups
    # Order: Amazon, Flipkart, Label Generator, Product Label Generator, Manual Plan
    tools = {
        "Amazon Easy Ship": {
            "type": "group",
            "key": "group_amazon_easy_ship",
            "icon": "📦",
            "children": ["Amazon Packing Plan", "Easy Ship Report"]
        },
        "🛒 Flipkart": {
            "type": "group",
            "key": "group_flipkart",
            "icon": "🛒",
            "children": ["Flipkart Packing Plan", "Report"]
        },
        "🏷️ Label Generator": {
            "type": "tool",
            "description": "",
            "key": "tool_label_generator",
            "icon": "🏷️"
        },
        "📋 Product Label Generator": {
            "type": "tool",
            "description": "",
            "key": "tool_product_label_generator",
            "icon": "📋"
        },
        "🔖 Manual Plan": {
            "type": "tool",
            "description": "",
            "key": "tool_manual_packing",
            "icon": "🔖"
        }
    }

    # Initialize session state for selected tool
    if 'selected_tool' not in st.session_state:
        st.session_state.selected_tool = "Amazon Easy Ship > Amazon Packing Plan"

    # Display tool cards and groups
    try:
        from app.utils.ui_components import tool_card, amazon_easy_ship_dropdown
        
        # Render each tool/group
        for item_name, item_info in tools.items():
            try:
                if item_info.get("type") == "group":
                    # Render dropdown for group
                    selected = amazon_easy_ship_dropdown(
                        group_name=item_name,
                        children=item_info["children"],
                        group_key=item_info["key"]
                    )
                    if selected:
                        st.session_state.selected_tool = selected
                        st.rerun()
                else:
                    # Render regular tool card
                    is_active = st.session_state.selected_tool == item_name
                    if tool_card(
                        icon=item_info["icon"],
                        title=item_name,
                        description=item_info.get("description", ""),
                        key=item_info["key"],
                        is_active=is_active
                    ):
                        st.session_state.selected_tool = item_name
                        st.rerun()
            except Exception as item_error:
                logger.error(f"Error rendering {item_name}: {item_error}", exc_info=True)
                st.sidebar.error(f"Error with {item_name}: {str(item_error)}")
                continue
        
        tool = st.session_state.selected_tool
    except Exception as e:
        logger.error(f"Error loading tool cards: {e}", exc_info=True)
        st.sidebar.error(f"Sidebar error: {str(e)}")
        # Fallback to selectbox
        tool = st.sidebar.selectbox(
            "Choose a tool",
            ["Amazon Easy Ship > Amazon Packing Plan", "Amazon Easy Ship > Easy Ship Report", "🛒 Flipkart > Flipkart Packing Plan", "🛒 Flipkart > Report", "🔖 Manual Plan", "🏷️ Label Generator"],
            label_visibility="visible"
        )
else:
    # Use selected_tool from session state (set by streamlit_app.py)
    if 'selected_tool' not in st.session_state:
        st.session_state.selected_tool = "Amazon Easy Ship > Amazon Packing Plan"
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

    elif actual_tool == "Easy Ship Report" or tool == "📥 Easy Ship":
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

    elif tool == "🏷️ Label Generator":
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

    elif tool == "📋 Product Label Generator":
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

    elif actual_tool == "Report" and ("Flipkart" in tool or "🛒" in tool):
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

    elif tool == "🔖 Manual Plan":
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

    elif tool == "Packed Unit Stock" or tool == "📊 Packed Unit Stock":
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


