import streamlit as st
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure Streamlit page
st.set_page_config(page_title="📦 Mithila Tools Dashboard", layout="wide")

# Main dashboard
st.sidebar.title("🧰 Mithila Dashboard")
tool = st.sidebar.selectbox("Choose a tool", [
    "📦 Packing Plan Generator",
    "🔖 Manual Packing Plan Generator", 
    "🔖 Label Generator",
    "📥 Easy Ship Report Generator"
])

# Tool loading with error handling
try:
    if tool == "📦 Packing Plan Generator":
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

    elif tool == "🔖 Label Generator":
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

    elif tool == "🔖 Manual Packing Plan Generator":
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

    elif tool == "📥 Easy Ship Report Generator":
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

    

    
    
   

except Exception as e:
    st.error(f"Unexpected error in main application: {str(e)}")
    logger.error(f"Unexpected error in main_app: {str(e)}")
    st.info("Please refresh the page and try again. If the problem persists, check the logs.")


