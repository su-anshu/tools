import streamlit as st
import os
import requests
import pandas as pd
from io import StringIO
from datetime import datetime
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATA_DIR = "data"
try:
    os.makedirs(DATA_DIR, exist_ok=True)
    # Test write permissions
    test_file = os.path.join(DATA_DIR, ".test_write")
    with open(test_file, 'w') as f:
        f.write("test")
    os.remove(test_file)
except PermissionError:
    DATA_DIR = "."  # Fallback to current directory
    logger.warning("No write permission to data directory, using current directory")
except Exception as e:
    logger.error(f"Error setting up data directory: {e}")
    DATA_DIR = "."

BARCODE_PDF_PATH = os.path.join(DATA_DIR, "master_fnsku.pdf")
MASTER_FILE = os.path.join(DATA_DIR, "temp_master.xlsx")
MANUAL_PLAN_FILE = os.path.join(DATA_DIR, "latest_packing_plan.xlsx")
META_FILE = os.path.join(DATA_DIR, "master_meta.txt")
ADMIN_PASSWORD = "admin@2025#"

# Default Google Sheet URL (your master sheet)
DEFAULT_MASTER_SHEET_URL = "https://docs.google.com/spreadsheets/d/11dBw92P7Bg0oFyfqramGqdAlLTGhcb2ScjmR_1wtiTM/export?format=csv&gid=0"

def load_from_google_sheet(sheet_url):
    """Load data directly from Google Sheet"""
    try:
        logger.info(f"Loading data from Google Sheets: {sheet_url[:50]}...")
        response = requests.get(sheet_url, timeout=30)
        response.raise_for_status()
        
        # Convert to DataFrame
        csv_data = StringIO(response.text)
        df = pd.read_csv(csv_data)
        
        logger.info(f"Successfully loaded {len(df)} rows from Google Sheets")
        return df, None
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error loading Google Sheet: {str(e)}")
        return None, f"Network error: {str(e)}"
    except pd.errors.EmptyDataError:
        logger.error("Google Sheet is empty or invalid CSV format")
        return None, "Sheet is empty or invalid format"
    except Exception as e:
        logger.error(f"Error loading Google Sheet: {str(e)}")
        return None, str(e)

def validate_file_upload(uploaded_file, expected_type, max_size_mb=50):
    """Validate uploaded files"""
    if uploaded_file is None:
        return False, "No file provided"
    
    if uploaded_file.size > max_size_mb * 1024 * 1024:
        return False, f"File too large (max {max_size_mb}MB)"
    
    if expected_type == "xlsx" and not uploaded_file.name.endswith(('.xlsx', '.xls')):
        return False, "Invalid Excel file format"
    elif expected_type == "pdf" and not uploaded_file.name.endswith('.pdf'):
        return False, "Invalid PDF file format"
    
    return True, "Valid file"

def sidebar_controls():
    """Enhanced sidebar with Google Sheets integration"""
    st.sidebar.title("🧰 Sidebar Controls")
    admin_logged_in = False
    password = st.sidebar.text_input("Admin Password", type="password")
    
    if password == ADMIN_PASSWORD:
        st.sidebar.success("✅ Admin logged in")
        admin_logged_in = True
    else:
        st.sidebar.info("Only admin can configure data sources.")

    if admin_logged_in:
        # Google Sheets Configuration Section
        st.sidebar.markdown("### 📊 Google Sheets Configuration")
        
        # Check if default sheet URL is working
        master_url_file = os.path.join(DATA_DIR, "master_sheet_url.txt")
        current_master_url = DEFAULT_MASTER_SHEET_URL
        
        # Load saved URL if exists
        if os.path.exists(master_url_file):
            try:
                with open(master_url_file, 'r') as f:
                    saved_url = f.read().strip()
                    if saved_url:
                        current_master_url = saved_url
            except Exception:
                pass
        
        # Master Sheet URL input
        master_sheet_url = st.sidebar.text_input(
            "Master Sheet CSV URL",
            value=current_master_url,
            help="CSV export URL from Google Sheets"
        )
        
        if st.sidebar.button("📥 Test & Save Master Sheet"):
            with st.sidebar.spinner("Testing connection..."):
                df, error = load_from_google_sheet(master_sheet_url)
                if error:
                    st.sidebar.error(f"❌ Error: {error}")
                else:
                    # Save URL to config file
                    with open(master_url_file, "w") as f:
                        f.write(master_sheet_url)
                    # Update meta file
                    with open(META_FILE, "w") as meta:
                        meta.write(f"Google_Sheets_Master|{datetime.now().isoformat()}")
                    st.sidebar.success(f"✅ Connected! Found {len(df)} rows")
        
        # Manual Packing Plan Sheet URL  
        manual_url_file = os.path.join(DATA_DIR, "manual_sheet_url.txt")
        manual_sheet_url = st.sidebar.text_input(
            "Manual Plan Sheet CSV URL (Optional)",
            placeholder="https://docs.google.com/.../export?format=csv&gid=0",
            help="Leave empty to use file uploads for manual plans"
        )
        
        if manual_sheet_url and st.sidebar.button("📥 Test & Save Manual Plan"):
            with st.sidebar.spinner("Testing connection..."):
                df, error = load_from_google_sheet(manual_sheet_url)
                if error:
                    st.sidebar.error(f"❌ Error: {error}")
                else:
                    with open(manual_url_file, "w") as f:
                        f.write(manual_sheet_url)
                    st.sidebar.success(f"✅ Connected! Found {len(df)} rows")

        # Connection Status
        st.sidebar.markdown("### 📊 Connection Status")
        
        # Test master sheet connection
        if os.path.exists(master_url_file):
            try:
                with open(master_url_file, 'r') as f:
                    url = f.read().strip()
                df, error = load_from_google_sheet(url)
                if error:
                    st.sidebar.warning(f"⚠️ Master Sheet: Connection issue")
                else:
                    st.sidebar.success(f"🔗 Master Sheet: Connected ({len(df)} products)")
            except Exception:
                st.sidebar.warning("⚠️ Master Sheet: Connection issue")
        else:
            st.sidebar.warning("⚠️ Master Sheet: Using default URL")
            
        if os.path.exists(manual_url_file):
            st.sidebar.success("🔗 Manual Plan Sheet: Connected")
        else:
            st.sidebar.info("ℹ️ Manual Plan: Using file uploads")

        # Quick refresh button
        if st.sidebar.button("🔄 Refresh Data Now"):
            st.sidebar.info("✅ Data will refresh on next tool use")

        # Backup file uploads section (collapsible)
        with st.sidebar.expander("📁 Backup File Uploads", expanded=False):
            st.write("**Use these if Google Sheets is unavailable**")
            
            # Master Excel Upload (backup)
            st.markdown("**📊 Backup Master Excel**")
            excel_file = st.file_uploader("Upload temp_master.xlsx", type=["xlsx"], key="master_upload")
            if excel_file:
                is_valid, message = validate_file_upload(excel_file, "xlsx")
                if is_valid:
                    try:
                        with open(MASTER_FILE, "wb") as f:
                            f.write(excel_file.read())
                        with open(META_FILE, "w") as meta:
                            meta.write(f"{excel_file.name}|{datetime.now().isoformat()}")
                        st.success("✅ Backup Excel uploaded!")
                        logger.info(f"Backup master Excel uploaded: {excel_file.name}")
                    except Exception as e:
                        st.error(f"Failed to save file: {str(e)}")
                        logger.error(f"Error saving backup master Excel: {str(e)}")
                else:
                    st.error(f"❌ {message}")

            # Barcode Upload
            st.markdown("**📤 Barcode PDF**")
            barcode_file = st.file_uploader("Upload master_fnsku.pdf", type=["pdf"])
            if barcode_file:
                is_valid, message = validate_file_upload(barcode_file, "pdf")
                if is_valid:
                    try:
                        with open(BARCODE_PDF_PATH, "wb") as f:
                            f.write(barcode_file.read())
                        st.success("✅ Barcode PDF uploaded")
                        logger.info(f"Barcode PDF uploaded: {barcode_file.name}")
                    except Exception as e:
                        st.error(f"Failed to save barcode: {str(e)}")
                        logger.error(f"Error saving barcode PDF: {str(e)}")
                else:
                    st.error(f"❌ {message}")

            # Manual Packing Plan Upload (backup)
            st.markdown("**📝 Backup Manual Packing Plan**")
            manual_file = st.file_uploader("Upload latest_packing_plan.xlsx", type=["xlsx"], key="manual_upload")
            if manual_file:
                is_valid, message = validate_file_upload(manual_file, "xlsx")
                if is_valid:
                    try:
                        with open(MANUAL_PLAN_FILE, "wb") as f:
                            f.write(manual_file.read())
                        st.success("✅ Backup manual plan uploaded")
                        logger.info(f"Backup manual packing plan uploaded: {manual_file.name}")
                    except Exception as e:
                        st.error(f"Failed to save manual plan: {str(e)}")
                        logger.error(f"Error saving manual packing plan: {str(e)}")
                else:
                    st.error(f"❌ {message}")

        # Display current file info
        if os.path.exists(META_FILE):
            try:
                meta_content = open(META_FILE).read().strip()
                if "|" in meta_content:
                    name, ts = meta_content.split("|", 1)
                    if name == "Google_Sheets_Master":
                        formatted_ts = pd.to_datetime(ts).strftime('%d %b %Y %I:%M %p')
                        st.sidebar.caption(f"📊 Google Sheets connected: {formatted_ts}")
                    else:
                        formatted_ts = pd.to_datetime(ts).strftime('%d %b %Y %I:%M %p')
                        st.sidebar.caption(f"🗂 Local file: {name} — {formatted_ts}")
                else:
                    st.sidebar.caption("🗂 Data source available")
            except Exception as e:
                st.sidebar.caption("🗂 Data source available")
                logger.warning(f"Error reading meta file: {str(e)}")

        # Display other file timestamps
        if os.path.exists(BARCODE_PDF_PATH):
            try:
                ts = datetime.fromtimestamp(os.path.getmtime(BARCODE_PDF_PATH)).strftime('%d %b %Y %I:%M %p')
                st.sidebar.caption(f"📦 Barcode updated: {ts}")
            except Exception as e:
                st.sidebar.caption("📦 Barcode file available")
                logger.warning(f"Error reading barcode file timestamp: {str(e)}")

        if os.path.exists(MANUAL_PLAN_FILE):
            try:
                ts = datetime.fromtimestamp(os.path.getmtime(MANUAL_PLAN_FILE)).strftime('%d %b %Y %I:%M %p')
                st.sidebar.caption(f"📒 Manual plan file updated: {ts}")
            except Exception as e:
                st.sidebar.caption("📒 Manual plan file available")
                logger.warning(f"Error reading manual plan file timestamp: {str(e)}")

    return admin_logged_in, MASTER_FILE, BARCODE_PDF_PATH, MANUAL_PLAN_FILE

def load_master_data():
    """Load master data from Google Sheet or fallback to local file"""
    master_url_file = os.path.join(DATA_DIR, "master_sheet_url.txt")
    
    # Try Google Sheet first
    if os.path.exists(master_url_file):
        try:
            with open(master_url_file, 'r') as f:
                sheet_url = f.read().strip()
            
            if sheet_url:
                st.info("📊 Loading latest data from Google Sheets...")
                df, error = load_from_google_sheet(sheet_url)
                
                if df is not None:
                    st.success(f"✅ Loaded {len(df)} products from Google Sheets")
                    return df
                else:
                    st.warning(f"⚠️ Google Sheets error: {error}. Trying backup...")
                    
        except Exception as e:
            st.warning(f"⚠️ Could not load from Google Sheets: {str(e)}. Trying backup...")
    
    # Try default Google Sheet URL
    if not os.path.exists(master_url_file):
        try:
            st.info("📊 Loading data from default Google Sheets...")
            df, error = load_from_google_sheet(DEFAULT_MASTER_SHEET_URL)
            
            if df is not None:
                st.success(f"✅ Loaded {len(df)} products from Google Sheets")
                # Save the working URL
                with open(master_url_file, "w") as f:
                    f.write(DEFAULT_MASTER_SHEET_URL)
                return df
            else:
                st.warning(f"⚠️ Default Google Sheets error: {error}. Trying local backup...")
        except Exception as e:
            st.warning(f"⚠️ Could not load from default Google Sheets: {str(e)}. Trying local backup...")
    
    # Fallback to local Excel file
    if os.path.exists(MASTER_FILE):
        st.info("📁 Using local Excel file as backup...")
        try:
            df = pd.read_excel(MASTER_FILE)
            st.success(f"✅ Loaded {len(df)} products from local backup file")
            return df
        except Exception as e:
            st.error(f"❌ Error loading local Excel file: {str(e)}")
    
    # No data source available
    st.error("❌ No data source available. Please configure Google Sheets or upload Excel file.")
    return None
