"""
Utility functions for Mithila Tools Dashboard
"""
import pandas as pd
import hashlib
import re
import logging
import streamlit as st
from io import BytesIO
from datetime import datetime

def is_empty_value(value):
    """Standardized check for empty/invalid values"""
    if pd.isna(value):
        return True
    if value is None:
        return True
    str_value = str(value).strip().lower()
    return str_value in ["", "nan", "none", "null", "n/a"]

def get_unique_key_suffix(data):
    """Generate unique key suffix from data hash to prevent duplicate widget keys"""
    try:
        if isinstance(data, pd.DataFrame):
            hash_data = pd.util.hash_pandas_object(data).values
            return hashlib.md5(hash_data.tobytes()).hexdigest()[:8]
        elif isinstance(data, BytesIO):
            # For BytesIO, hash the content
            pos = data.tell()
            data.seek(0)
            content = data.read()
            data.seek(pos)
            return hashlib.md5(content).hexdigest()[:8]
        elif isinstance(data, bytes):
            return hashlib.md5(data).hexdigest()[:8]
        else:
            # Fallback: use string representation
            return hashlib.md5(str(data).encode()).hexdigest()[:8]
    except Exception as e:
        # Fallback to timestamp if hashing fails
        return datetime.now().strftime("%H%M%S")

def detect_multi_item_orders(df, product_id_column='asin'):
    """
    Detect orders with multiple different products
    
    Args:
        df: DataFrame with order data
        product_id_column: Column name for product identifier ('asin' for Amazon, 'sku' for Flipkart)
    
    Returns:
        tuple: (multi_item_order_ids, order_analysis_df)
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Group by tracking-id and count unique products
        order_analysis = df.groupby('tracking-id').agg({
            'product-name': 'nunique',  # Count unique products per order
            product_id_column: 'nunique',  # Count unique product IDs per order
            'qty': 'sum'                # Total items in order
        }).reset_index()
        
        # Multi-item = more than 1 unique product per order
        multi_item_orders = order_analysis[
            order_analysis['product-name'] > 1
        ]['tracking-id'].tolist()
        
        logger.info(f"Detected {len(multi_item_orders)} multi-item orders out of {len(order_analysis)} total orders")
        return multi_item_orders, order_analysis
    except Exception as e:
        logger.error(f"Error detecting multi-item orders: {str(e)}")
        return [], pd.DataFrame()

def truncate_product_name(text):
    """Truncate messy product names to clean format"""
    try:
        if is_empty_value(text):
            return "Unknown Product"
        words = str(text).split()
        return ' '.join(words[:10])[:70]
    except Exception:
        return "Unknown Product"

def extract_month_day(slot):
    """Extract month and day from pickup slot string"""
    import re
    try:
        if is_empty_value(slot):
            return "No Date"
        # Look for patterns like "January 15", "Feb 3", "Nov 15, 2025", etc.
        match = re.search(r'[A-Za-z]{3,9}\s+\d{1,2}', str(slot))
        return match.group(0) if match else str(slot)[:20]
    except Exception:
        return "Invalid Date"

def safe_int_conversion(value):
    """Safely convert value to integer with fallback"""
    try:
        return int(float(value)) if pd.notna(value) else 1
    except (ValueError, TypeError):
        return 1

def sanitize_filename(name):
    """Sanitize filename for safe file operations"""
    return re.sub(r'[^\w\-_\.]', '_', str(name))

def setup_tool_ui(title, load_ui_components=False):
    """
    Setup tool UI with CSS injection and optional UI components
    
    Args:
        title: Tool title to display
        load_ui_components: Whether to load UI components (for packing plan tools)
    
    Returns:
        tuple: (css_loaded, ui_enabled) - Status flags
    """
    css_loaded = False
    ui_enabled = False
    
    # Inject custom CSS
    try:
        from app.utils.ui_components import inject_custom_css
        inject_custom_css()
        css_loaded = True
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.warning(f"Could not inject CSS: {e}")
    
    # Inject UI components if requested
    if load_ui_components:
        try:
            from app.utils.ui_components import (
                welcome_header, section_header, metric_card, info_card,
                status_badge, section_divider, custom_card, connection_badge
            )
            ui_enabled = True
        except ImportError as e:
            logger = logging.getLogger(__name__)
            logger.warning(f"UI components not available: {e}, using default styling")
    
    # Display title
    st.markdown(f"### {title}")
    
    return css_loaded, ui_enabled

def load_and_validate_master_data(require_columns=None, return_barcode_path=False, show_error=True):
    """
    Load and validate master data from Google Sheets or Excel backup
    
    Args:
        require_columns: List of required column names (optional)
        return_barcode_path: Whether to return BARCODE_PDF_PATH from sidebar
        show_error: Whether to show error messages to user
    
    Returns:
        tuple: (master_df, admin_logged_in, barcode_path) or master_df if return_barcode_path=False
    """
    from app.sidebar import sidebar_controls, load_master_data
    
    admin_logged_in, _, barcode_path, _ = sidebar_controls()
    master_df = load_master_data()
    
    if master_df is None:
        if show_error:
            st.error("❌ Master data not available. Please configure data source in sidebar.")
            st.stop()
        return None if not return_barcode_path else (None, admin_logged_in, barcode_path)
    
    # Clean column names
    master_df.columns = master_df.columns.str.strip()
    
    # Validate required columns
    if require_columns:
        missing_columns = [col for col in require_columns if col not in master_df.columns]
        if missing_columns:
            if show_error:
                st.error(f"Missing required columns: {missing_columns}")
                st.stop()
            return None if not return_barcode_path else (None, admin_logged_in, barcode_path)
    
    logger = logging.getLogger(__name__)
    logger.info(f"Loaded master data with {len(master_df)} products")
    
    if return_barcode_path:
        return master_df, admin_logged_in, barcode_path
    return master_df

def create_product_name_mapping(master_df, id_column='ASIN', fallback_id_column=None):
    """
    Create product name mapping from master data (Name + Net Weight)
    
    Args:
        master_df: Master data DataFrame
        id_column: Primary ID column ('ASIN' for Amazon, 'SKU' or 'SKU_ID' for Flipkart)
        fallback_id_column: Fallback ID column if primary not found (e.g., 'ASIN' for Flipkart)
    
    Returns:
        pd.DataFrame: Mapping DataFrame with id_column and 'clean_product_name'
    """
    if master_df is None or master_df.empty:
        return pd.DataFrame()
    
    mapping_df = pd.DataFrame()
    
    # Try primary ID column first
    if id_column in master_df.columns or (id_column == 'SKU' and 'SKU_ID' in master_df.columns):
        actual_id_col = id_column if id_column in master_df.columns else 'SKU_ID'
        
        if 'Name' in master_df.columns and 'Net Weight' in master_df.columns:
            master_df['clean_product_name'] = (
                master_df['Name'].fillna('Unknown') + " " + 
                master_df['Net Weight'].fillna('N/A').astype(str) + "kg"
            )
            mapping_df = master_df[[actual_id_col, 'clean_product_name']].dropna()
            mapping_df = mapping_df.rename(columns={actual_id_col: id_column})
            logger = logging.getLogger(__name__)
            logger.info(f"Loaded {len(mapping_df)} {id_column} mappings from master data")
    
    # Fallback to secondary ID column if primary failed
    if mapping_df.empty and fallback_id_column and fallback_id_column in master_df.columns:
        if 'Name' in master_df.columns and 'Net Weight' in master_df.columns:
            master_df['clean_product_name'] = (
                master_df['Name'].fillna('Unknown') + " " + 
                master_df['Net Weight'].fillna('N/A').astype(str) + "kg"
            )
            mapping_df = master_df[[fallback_id_column, 'clean_product_name']].dropna()
            mapping_df = mapping_df.rename(columns={fallback_id_column: id_column})
            logger = logging.getLogger(__name__)
            logger.info(f"Loaded {len(mapping_df)} {id_column} mappings from master data (fallback)")
    
    return mapping_df

def should_include_product_label(product_name, master_df, row=None, id_column='ASIN', find_column_func=None):
    """
    Check if a product should be included in product labels based on "Product Label" column
    
    Args:
        product_name: Product name from df_physical
        master_df: Master data DataFrame
        row: Optional row from df_physical (for ASIN/SKU matching)
        id_column: ID column name ('ASIN' for Amazon, 'SKU ID' or 'SKU_ID' for Flipkart)
        find_column_func: Optional function to find columns flexibly (for Flipkart)
    
    Returns:
        bool: True if product should be included (Product Label = "Yes" or column doesn't exist), False otherwise
    """
    if master_df is None or master_df.empty:
        return True  # Backward compatibility: include all if no master data
    
    # Find "Product Label" column using flexible matching
    product_label_col = None
    for col in master_df.columns:
        col_lower = col.lower().strip()
        if 'product' in col_lower and 'label' in col_lower:
            product_label_col = col
            break
    
    # If column doesn't exist, include all products (backward compatibility)
    if product_label_col is None:
        return True
    
    # Try to match product in master data
    match = None
    
    # Strategy 1: Match by ID column if available
    if row is not None:
        if id_column == 'ASIN':
            product_id = row.get("ASIN", "")
            if product_id and "ASIN" in master_df.columns:
                id_match = master_df[master_df["ASIN"] == product_id]
                if not id_match.empty:
                    match = id_match.iloc[0]
        else:  # Flipkart - use SKU ID
            sku_id = row.get("SKU ID", row.get("SKU_ID", ""))
            if sku_id:
                # Try to find SKU column in master data
                sku_col = None
                for col in master_df.columns:
                    col_lower = col.lower().strip()
                    if 'sku' in col_lower and ('id' in col_lower or col_lower == 'sku'):
                        sku_col = col
                        break
                
                if sku_col:
                    # Match by SKU ID
                    sku_match = master_df[master_df[sku_col].astype(str).str.strip() == str(sku_id).strip()]
                    if not sku_match.empty:
                        match = sku_match.iloc[0]
    
    # Strategy 2: Match by Name if ID match failed
    if match is None and product_name:
        name_col = None
        if find_column_func:
            name_col = find_column_func(master_df, ['Name'])
        else:
            for col in master_df.columns:
                if col.lower().strip() in ['name', 'product name', 'product', 'item name', 'item']:
                    name_col = col
                    break
        
        if name_col:
            name_match = master_df[
                master_df[name_col].astype(str).str.strip().str.lower() == product_name.strip().lower()
            ]
            if not name_match.empty:
                match = name_match.iloc[0]
    
    # If no match found, don't include (product not in master data)
    if match is None:
        logger = logging.getLogger(__name__)
        logger.debug(f"Product '{product_name}' not found in master data for Product Label check")
        return False
    
    # Check Product Label value
    product_label_value = str(match.get(product_label_col, "")).strip()
    # Case-insensitive check for "Yes"
    return product_label_value.lower() in ["yes", "y"]

def initialize_packing_plan_variables():
    """
    Initialize common variables for packing plan tools
    
    Returns:
        dict: Dictionary with initialized variables
    """
    return {
        'df_orders': pd.DataFrame(),
        'df_physical': pd.DataFrame(),
        'missing_products': [],
        'total_orders': 0,
        'total_physical_items': 0,
        'total_qty_ordered': 0,
        'total_qty_physical': 0,
        'sorted_highlighted_pdf': None
    }

def create_packing_plan_tabs():
    """Create standard tabs for packing plan tools"""
    return st.tabs(["📤 Upload", "📊 Results", "📥 Downloads", "🏷️ Labels"])

def create_download_buttons(pdf_data, excel_dataframes, pdf_filename, excel_filename, key_suffix, 
                            pdf_label="Packing Plan PDF", excel_label="Excel Workbook",
                            missing_products_df=None):
    """
    Create download buttons for PDF and Excel files
    
    Args:
        pdf_data: PDF bytes or None
        excel_dataframes: Dict with sheet_name: DataFrame pairs, or list of (sheet_name, df) tuples
        pdf_filename: PDF filename
        excel_filename: Excel filename
        key_suffix: Unique key suffix for Streamlit widgets
        pdf_label: Label for PDF download button
        excel_label: Label for Excel download button
        missing_products_df: Optional DataFrame for missing products sheet
    
    Returns:
        None (renders buttons directly)
    """
    col1, col2 = st.columns(2)
    
    with col1:
        if pdf_data:
            try:
                st.download_button(
                    pdf_label,
                    data=pdf_data,
                    file_name=pdf_filename,
                    mime="application/pdf",
                    key=f"download_pdf_{key_suffix}",
                    use_container_width=True
                )
            except Exception as e:
                st.error(f"Error: {str(e)}")
    
    with col2:
        if excel_dataframes:
            try:
                excel_buffer = BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                    # Handle dict or list of tuples
                    if isinstance(excel_dataframes, dict):
                        for sheet_name, df in excel_dataframes.items():
                            df.to_excel(writer, index=False, sheet_name=sheet_name)
                    else:
                        for sheet_name, df in excel_dataframes:
                            df.to_excel(writer, index=False, sheet_name=sheet_name)
                    
                    # Add missing products sheet if provided
                    if missing_products_df is not None and not missing_products_df.empty:
                        missing_products_df.to_excel(writer, index=False, sheet_name="Missing Products")
                
                excel_buffer.seek(0)
                st.download_button(
                    excel_label,
                    data=excel_buffer,
                    file_name=excel_filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"download_excel_{key_suffix}",
                    use_container_width=True
                )
            except Exception as e:
                st.error(f"Error: {str(e)}")
