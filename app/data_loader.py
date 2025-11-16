import streamlit as st
import pandas as pd
import os
import requests
from io import StringIO
import logging

logger = logging.getLogger(__name__)

DATA_DIR = "data"
MASTER_FILE = os.path.join(DATA_DIR, "temp_master.xlsx")

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

@st.cache_data(ttl=300)
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

@st.cache_data(ttl=300)  # Cache for 5 minutes
def load_nutrition_data():
    """Load nutrition data from Google Sheets - nutritional sheet"""
    SPREADSHEET_ID = "11dBw92P7Bg0oFyfqramGqdAlLTGhcb2ScjmR_1wtiTM"
    NUTRITIONAL_SHEET_GID = "1800176856"  # Exact GID for nutritional sheet
    GOOGLE_SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv&gid={NUTRITIONAL_SHEET_GID}"
    try:
        st.info(f"📊 Loading from nutritional sheet (GID: {NUTRITIONAL_SHEET_GID})...")
        
        df = pd.read_csv(GOOGLE_SHEET_URL)
        
        # Debug: Show what columns we found
        st.info(f"🔍 Found columns: {list(df.columns)}")
        
        # More flexible product column detection
        product_column = None
        for col in df.columns:
            if 'product' in col.lower() or 'name' in col.lower() or 'item' in col.lower():
                product_column = col
                break
        
        if product_column is None:
            st.error("❌ No Product/Name column found in the nutritional sheet")
            st.info("📋 Available columns: " + ", ".join(df.columns))
            return None
        
        # Clean up the data using the found product column
        df = df.dropna(subset=[product_column])
        
        # Rename the product column to 'Product' for consistency
        if product_column != 'Product':
            df = df.rename(columns={product_column: 'Product'})
        
        st.success(f"✅ Loaded {len(df)} products from nutritional sheet")
        
        return df
        
    except Exception as e:
        st.error(f"❌ Error loading nutritional data: {str(e)}")
        st.info("💡 Possible issues:")
        st.info(f"• Check if the nutritional sheet (GID: {NUTRITIONAL_SHEET_GID}) is accessible")
        st.info("• Verify the sheet has a 'Product' or 'Name' column")
        st.info("• Make sure the sheet is shared publicly or with the right permissions")
        
        return None

@st.cache_data(ttl=300)
def load_nutrition_data_silent():
    """Load nutrition data silently without UI messages"""
    try:
        # Same Google Sheets URL from app_nutrtional_label.py
        SPREADSHEET_ID = "11dBw92P7Bg0oFyfqramGqdAlLTGhcb2ScjmR_1wtiTM"
        NUTRITIONAL_SHEET_GID = "1800176856"
        GOOGLE_SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv&gid={NUTRITIONAL_SHEET_GID}"
        
        import requests
        df = pd.read_csv(GOOGLE_SHEET_URL)
        
        # Find product column
        product_column = None
        for col in df.columns:
            if 'product' in col.lower() or 'name' in col.lower() or 'item' in col.lower():
                product_column = col
                break
        
        if product_column is None:
            return None
        
        # Clean up the data
        df = df.dropna(subset=[product_column])
        
        # Rename the product column to 'Product' for consistency
        if product_column != 'Product':
            df = df.rename(columns={product_column: 'Product'})
        
        return df
        
    except Exception as e:
        logger.error(f"Error loading nutrition data silently: {str(e)}")
        return None