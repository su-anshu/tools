import streamlit as st
import os
import requests
import pandas as pd
from io import StringIO
from datetime import datetime
import logging
from app.utils.ui_components import (
    tailwind_card, tailwind_section_header, tailwind_status_badge,
    tailwind_input_group, tailwind_divider, tailwind_info_text,
    tailwind_success_message, tailwind_error_message, tailwind_warning_message
)

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

# Feature flag: Set to True to enable admin controls in frontend
SHOW_ADMIN_CONTROLS = False  # Hidden for now, will be added in future

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
    """Enhanced sidebar with Google Sheets integration and Tailwind CSS styling"""
    # Prevent duplicate rendering by checking if sidebar controls section already exists
    # Use a unique session state key to track if we've rendered the admin section
    SIDEBAR_RENDERED_KEY = 'sidebar_admin_section_rendered'
    
    # Check if we've already rendered in this script run
    if SIDEBAR_RENDERED_KEY in st.session_state and st.session_state[SIDEBAR_RENDERED_KEY]:
        # Return cached values to prevent duplicate rendering
        admin_logged_in = st.session_state.get('admin_authenticated', False)
        return admin_logged_in, MASTER_FILE, BARCODE_PDF_PATH, MANUAL_PLAN_FILE
    
    # Mark as rendered for this script run
    st.session_state[SIDEBAR_RENDERED_KEY] = True
    
    # Initialize session state for admin authentication
    if 'admin_authenticated' not in st.session_state:
        st.session_state.admin_authenticated = False
    
    # Configuration Header with Tailwind (only show if admin controls enabled)
    if SHOW_ADMIN_CONTROLS:
        st.sidebar.markdown(
            tailwind_section_header("⚙️ Configuration", size="text-xl"),
            unsafe_allow_html=True
        )
        st.sidebar.markdown(tailwind_divider(), unsafe_allow_html=True)
    
    # Admin Authentication Section with Tailwind (hidden if SHOW_ADMIN_CONTROLS is False)
    if SHOW_ADMIN_CONTROLS and not st.session_state.admin_authenticated:
        auth_card_content = '''
        <div class="space-y-3">
            <div class="flex items-center mb-3">
                <span class="text-2xl mr-2">🔐</span>
                <span class="text-sm font-medium text-gray-700">Admin Access Required</span>
            </div>
        </div>
        '''
        st.sidebar.markdown(
            tailwind_card(auth_card_content, padding="p-4", margin="mb-4"),
            unsafe_allow_html=True
        )
        
        password = st.sidebar.text_input(
            "Admin Password", 
            type="password", 
            help="Enter admin password to configure data sources",
            key="admin_password_input"
        )
        
        if password == ADMIN_PASSWORD:
            st.sidebar.markdown(
                tailwind_success_message("Admin logged in successfully"),
                unsafe_allow_html=True
            )
            st.session_state.admin_authenticated = True
            st.rerun()
        else:
            if password:
                st.sidebar.markdown(
                    tailwind_warning_message("Incorrect password"),
                    unsafe_allow_html=True
                )
            st.sidebar.markdown(
                tailwind_info_text("Only admin can configure data sources.", color="text-gray-500"),
                unsafe_allow_html=True
            )
    
    admin_logged_in = st.session_state.admin_authenticated if SHOW_ADMIN_CONTROLS else False
    
    # Show logout button if authenticated and admin controls enabled
    if SHOW_ADMIN_CONTROLS and admin_logged_in:
        if st.sidebar.button("🚪 Logout", key="admin_logout_button", use_container_width=True):
            st.session_state.admin_authenticated = False
            st.rerun()

    # Admin configuration sections (only show if admin controls enabled and logged in)
    if SHOW_ADMIN_CONTROLS and admin_logged_in:
        st.sidebar.markdown(tailwind_divider(), unsafe_allow_html=True)
        
        # Google Sheets Configuration Section with Tailwind
        st.sidebar.markdown(
            tailwind_section_header("📊 Google Sheets Configuration"),
            unsafe_allow_html=True
        )
        
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
        
        # Master Sheet URL input in Tailwind card
        sheets_card_content = '''
        <div class="space-y-4">
            <div>
                <label class="block text-sm font-medium text-gray-700 mb-2">Master Sheet CSV URL</label>
            </div>
        </div>
        '''
        st.sidebar.markdown(
            tailwind_card(sheets_card_content, padding="p-4", margin="mb-4"),
            unsafe_allow_html=True
        )
        
        master_sheet_url = st.sidebar.text_input(
            "Master Sheet CSV URL",
            value=current_master_url,
            help="CSV export URL from Google Sheets",
            key="master_sheet_url_input",
            label_visibility="collapsed"
        )
        
        if st.sidebar.button("📥 Test & Save Master Sheet", key="test_save_master_button", use_container_width=True):
            with st.sidebar.spinner("Testing connection..."):
                df, error = load_from_google_sheet(master_sheet_url)
                if error:
                    st.sidebar.markdown(
                        tailwind_error_message(f"Error: {error}"),
                        unsafe_allow_html=True
                    )
                else:
                    # Save URL to config file
                    with open(master_url_file, "w") as f:
                        f.write(master_sheet_url)
                    # Update meta file
                    with open(META_FILE, "w") as meta:
                        meta.write(f"Google_Sheets_Master|{datetime.now().isoformat()}")
                    st.sidebar.markdown(
                        tailwind_success_message(f"Connected! Found {len(df)} rows"),
                        unsafe_allow_html=True
                    )
        
        # Manual Packing Plan Sheet URL
        manual_url_file = os.path.join(DATA_DIR, "manual_sheet_url.txt")
        manual_card_content = '''
        <div class="space-y-4">
            <div>
                <label class="block text-sm font-medium text-gray-700 mb-2">Manual Plan Sheet CSV URL (Optional)</label>
            </div>
        </div>
        '''
        st.sidebar.markdown(
            tailwind_card(manual_card_content, padding="p-4", margin="mb-4"),
            unsafe_allow_html=True
        )
        
        manual_sheet_url = st.sidebar.text_input(
            "Manual Plan Sheet CSV URL (Optional)",
            placeholder="https://docs.google.com/.../export?format=csv&gid=0",
            help="Leave empty to use file uploads for manual plans",
            key="manual_sheet_url_input",
            label_visibility="collapsed"
        )
        
        if manual_sheet_url and st.sidebar.button("📥 Test & Save Manual Plan", key="test_save_manual_button", use_container_width=True):
            with st.sidebar.spinner("Testing connection..."):
                df, error = load_from_google_sheet(manual_sheet_url)
                if error:
                    st.sidebar.markdown(
                        tailwind_error_message(f"Error: {error}"),
                        unsafe_allow_html=True
                    )
                else:
                    with open(manual_url_file, "w") as f:
                        f.write(manual_sheet_url)
                    st.sidebar.markdown(
                        tailwind_success_message(f"Connected! Found {len(df)} rows"),
                        unsafe_allow_html=True
                    )

        st.sidebar.markdown(tailwind_divider(), unsafe_allow_html=True)
        
        # Status Section with Tailwind
        st.sidebar.markdown(
            tailwind_section_header("Status", size="text-lg"),
            unsafe_allow_html=True
        )
        
        # Status card
        status_content = ""
        if os.path.exists(master_url_file):
            try:
                with open(master_url_file, 'r') as f:
                    url = f.read().strip()
                df, error = load_from_google_sheet(url)
                if error:
                    status_content = tailwind_status_badge("⚠️ Connection issue", "warning")
                else:
                    status_content = tailwind_status_badge(f"✓ {len(df)} products", "success")
            except Exception:
                status_content = tailwind_status_badge("⚠️ Connection issue", "warning")
        else:
            status_content = tailwind_info_text("Using default URL", color="text-gray-500")
        
        st.sidebar.markdown(
            tailwind_card(f'<div class="flex items-center justify-center py-2">{status_content}</div>', 
                         padding="p-3", margin="mb-4"),
            unsafe_allow_html=True
        )

        # Quick refresh button
        if st.sidebar.button("🔄 Refresh Data", use_container_width=True, key="refresh_data_button"):
            st.cache_data.clear()
            st.rerun()

        # Backup file uploads section (collapsible) with Tailwind
        with st.sidebar.expander("📁 Backup File Uploads", expanded=False):
            st.markdown(
                tailwind_info_text("Use these if Google Sheets is unavailable", color="text-gray-600"),
                unsafe_allow_html=True
            )
            
            # Master Excel Upload (backup)
            upload_section = '''
            <div class="mb-4">
                <div class="flex items-center mb-2">
                    <span class="text-lg mr-2">📊</span>
                    <span class="text-sm font-medium text-gray-700">Backup Master Excel</span>
                </div>
            </div>
            '''
            st.markdown(upload_section, unsafe_allow_html=True)
            excel_file = st.file_uploader("Upload temp_master.xlsx", type=["xlsx"], key="sidebar_master_upload", label_visibility="collapsed")
            if excel_file:
                is_valid, message = validate_file_upload(excel_file, "xlsx")
                if is_valid:
                    try:
                        with open(MASTER_FILE, "wb") as f:
                            f.write(excel_file.read())
                        with open(META_FILE, "w") as meta:
                            meta.write(f"{excel_file.name}|{datetime.now().isoformat()}")
                        st.markdown(
                            tailwind_success_message("Backup Excel uploaded!"),
                            unsafe_allow_html=True
                        )
                        logger.info(f"Backup master Excel uploaded: {excel_file.name}")
                    except Exception as e:
                        st.markdown(
                            tailwind_error_message(f"Failed to save file: {str(e)}"),
                            unsafe_allow_html=True
                        )
                        logger.error(f"Error saving backup master Excel: {str(e)}")
                else:
                    st.markdown(
                        tailwind_error_message(message),
                        unsafe_allow_html=True
                    )

            # Barcode Upload
            barcode_section = '''
            <div class="mb-4 mt-4">
                <div class="flex items-center mb-2">
                    <span class="text-lg mr-2">📤</span>
                    <span class="text-sm font-medium text-gray-700">Barcode PDF</span>
                </div>
            </div>
            '''
            st.markdown(barcode_section, unsafe_allow_html=True)
            barcode_file = st.file_uploader("Upload master_fnsku.pdf", type=["pdf"], key="sidebar_barcode_upload", label_visibility="collapsed")
            if barcode_file:
                is_valid, message = validate_file_upload(barcode_file, "pdf")
                if is_valid:
                    try:
                        with open(BARCODE_PDF_PATH, "wb") as f:
                            f.write(barcode_file.read())
                        st.markdown(
                            tailwind_success_message("Barcode PDF uploaded"),
                            unsafe_allow_html=True
                        )
                        logger.info(f"Barcode PDF uploaded: {barcode_file.name}")
                    except Exception as e:
                        st.markdown(
                            tailwind_error_message(f"Failed to save barcode: {str(e)}"),
                            unsafe_allow_html=True
                        )
                        logger.error(f"Error saving barcode PDF: {str(e)}")
                else:
                    st.markdown(
                        tailwind_error_message(message),
                        unsafe_allow_html=True
                    )

            # Manual Packing Plan Upload (backup)
            manual_section = '''
            <div class="mb-4 mt-4">
                <div class="flex items-center mb-2">
                    <span class="text-lg mr-2">📝</span>
                    <span class="text-sm font-medium text-gray-700">Backup Manual Packing Plan</span>
                </div>
            </div>
            '''
            st.markdown(manual_section, unsafe_allow_html=True)
            manual_file = st.file_uploader("Upload latest_packing_plan.xlsx", type=["xlsx"], key="sidebar_manual_upload", label_visibility="collapsed")
            if manual_file:
                is_valid, message = validate_file_upload(manual_file, "xlsx")
                if is_valid:
                    try:
                        with open(MANUAL_PLAN_FILE, "wb") as f:
                            f.write(manual_file.read())
                        st.markdown(
                            tailwind_success_message("Backup manual plan uploaded"),
                            unsafe_allow_html=True
                        )
                        logger.info(f"Backup manual packing plan uploaded: {manual_file.name}")
                    except Exception as e:
                        st.markdown(
                            tailwind_error_message(f"Failed to save manual plan: {str(e)}"),
                            unsafe_allow_html=True
                        )
                        logger.error(f"Error saving manual packing plan: {str(e)}")
                else:
                    st.markdown(
                        tailwind_error_message(message),
                        unsafe_allow_html=True
                    )

        # Display current file info with Tailwind
        file_info_items = []
        
        if os.path.exists(META_FILE):
            try:
                meta_content = open(META_FILE).read().strip()
                if "|" in meta_content:
                    name, ts = meta_content.split("|", 1)
                    formatted_ts = pd.to_datetime(ts).strftime('%d %b %Y %I:%M %p')
                    if name == "Google_Sheets_Master":
                        file_info_items.append(f'<div class="flex items-center text-xs text-gray-600 py-1"><span class="mr-2">📊</span><span>Google Sheets: {formatted_ts}</span></div>')
                    else:
                        file_info_items.append(f'<div class="flex items-center text-xs text-gray-600 py-1"><span class="mr-2">🗂</span><span>{name}: {formatted_ts}</span></div>')
                else:
                    file_info_items.append('<div class="flex items-center text-xs text-gray-600 py-1"><span class="mr-2">🗂</span><span>Data source available</span></div>')
            except Exception as e:
                file_info_items.append('<div class="flex items-center text-xs text-gray-600 py-1"><span class="mr-2">🗂</span><span>Data source available</span></div>')
                logger.warning(f"Error reading meta file: {str(e)}")

        # Display other file timestamps
        if os.path.exists(BARCODE_PDF_PATH):
            try:
                ts = datetime.fromtimestamp(os.path.getmtime(BARCODE_PDF_PATH)).strftime('%d %b %Y %I:%M %p')
                file_info_items.append(f'<div class="flex items-center text-xs text-gray-600 py-1"><span class="mr-2">📦</span><span>Barcode: {ts}</span></div>')
            except Exception as e:
                file_info_items.append('<div class="flex items-center text-xs text-gray-600 py-1"><span class="mr-2">📦</span><span>Barcode file available</span></div>')
                logger.warning(f"Error reading barcode file timestamp: {str(e)}")

        if os.path.exists(MANUAL_PLAN_FILE):
            try:
                ts = datetime.fromtimestamp(os.path.getmtime(MANUAL_PLAN_FILE)).strftime('%d %b %Y %I:%M %p')
                file_info_items.append(f'<div class="flex items-center text-xs text-gray-600 py-1"><span class="mr-2">📒</span><span>Manual plan: {ts}</span></div>')
            except Exception as e:
                file_info_items.append('<div class="flex items-center text-xs text-gray-600 py-1"><span class="mr-2">📒</span><span>Manual plan file available</span></div>')
                logger.warning(f"Error reading manual plan file timestamp: {str(e)}")
        
        if file_info_items:
            file_info_content = '<div class="space-y-1">' + ''.join(file_info_items) + '</div>'
            st.sidebar.markdown(
                tailwind_card(file_info_content, padding="p-3", margin="mb-4", shadow="shadow-sm"),
                unsafe_allow_html=True
            )

    # Reset flag at end of function to allow re-rendering on next script run
    SIDEBAR_RENDERED_KEY = 'sidebar_admin_section_rendered'
    st.session_state[SIDEBAR_RENDERED_KEY] = False
    
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
                # Use columns to display messages in one line
                col1, col2 = st.columns([1, 1])
                with col1:
                    st.info("📊 Loading latest data from Google Sheets...")
                df, error = load_from_google_sheet(sheet_url)
                
                if df is not None:
                    with col2:
                        st.success(f"✅ Loaded {len(df)} products from Google Sheets")
                    return df
                else:
                    with col2:
                        st.warning(f"⚠️ Google Sheets error: {error}. Trying backup...")
                    
        except Exception as e:
            col1, col2 = st.columns([1, 1])
            with col1:
                st.info("📊 Loading latest data from Google Sheets...")
            with col2:
                st.warning(f"⚠️ Could not load from Google Sheets: {str(e)}. Trying backup...")
    
    # Try default Google Sheet URL
    if not os.path.exists(master_url_file):
        try:
            # Use columns to display messages in one line
            col1, col2 = st.columns([1, 1])
            with col1:
                st.info("📊 Loading data from default Google Sheets...")
            df, error = load_from_google_sheet(DEFAULT_MASTER_SHEET_URL)
            
            if df is not None:
                with col2:
                    st.success(f"✅ Loaded {len(df)} products from Google Sheets")
                # Save the working URL
                with open(master_url_file, "w") as f:
                    f.write(DEFAULT_MASTER_SHEET_URL)
                return df
            else:
                with col2:
                    st.warning(f"⚠️ Default Google Sheets error: {error}. Trying local backup...")
        except Exception as e:
            col1, col2 = st.columns([1, 1])
            with col1:
                st.info("📊 Loading data from default Google Sheets...")
            with col2:
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
