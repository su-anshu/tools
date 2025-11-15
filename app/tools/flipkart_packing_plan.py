import streamlit as st
import pandas as pd
import fitz
import re
from fpdf import FPDF
from io import BytesIO
from collections import defaultdict
from datetime import datetime
import contextlib
import logging
import hashlib
from app.sidebar import sidebar_controls, load_master_data, MASTER_FILE, BARCODE_PDF_PATH
from app.tools.label_generator import generate_combined_label_pdf_direct, generate_pdf, generate_triple_label_combined
from app.tools.product_label_generator import create_label_pdf
from app.data_loader import load_nutrition_data_silent

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Utility functions
def is_empty_value(value):
    """Standardized check for empty/invalid values"""
    if pd.isna(value):
        return True
    if value is None:
        return True
    str_value = str(value).strip().lower()
    return str_value in ["", "nan", "none", "null", "n/a"]

def find_column_flexible(df, column_names):
    """
    Find column in DataFrame with flexible matching (handles spaces, case, punctuation)
    
    Args:
        df: DataFrame to search
        column_names: List of possible column names or single string
    
    Returns:
        str: First matching column name or None if not found
    """
    if df is None or df.empty:
        return None
    
    if isinstance(column_names, str):
        column_names = [column_names]
    
    # Normalize column names: remove spaces, dots, convert to lowercase
    def normalize_name(name):
        return re.sub(r'[\s\.]+', '', str(name).lower())
    
    for col in df.columns:
        col_normalized = normalize_name(col)
        for target_name in column_names:
            target_normalized = normalize_name(target_name)
            # Try exact match first
            if col_normalized == target_normalized:
                return col
            # Try contains match
            if target_normalized in col_normalized or col_normalized in target_normalized:
                return col
            # Try case-insensitive match with original
            if str(col).strip().lower() == str(target_name).strip().lower():
                return col
    
    return None

@contextlib.contextmanager
def safe_pdf_context(pdf_bytes):
    """Context manager for safe PDF handling"""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        yield doc
    finally:
        doc.close()

def normalize_weight(weight_str):
    """
    Normalize weight strings to standard format for comparison
    
    Examples:
        "1kg" -> "1kg"
        "1 kg" -> "1kg"
        "1000g" -> "1kg"
        "350g" -> "350g"
        "0.35kg" -> "350g"
    
    Returns:
        Normalized weight string (e.g., "1kg", "350g")
    """
    if not weight_str or pd.isna(weight_str):
        return None
    
    weight_str = str(weight_str).strip().lower().replace(" ", "")
    
    # Handle grams
    if weight_str.endswith("g") and not weight_str.endswith("kg"):
        try:
            grams = float(weight_str[:-1])
            # Convert to kg if >= 1000g
            if grams >= 1000:
                kg = grams / 1000
                # Remove trailing zeros
                if kg == int(kg):
                    return f"{int(kg)}kg"
                else:
                    return f"{kg}kg"
            else:
                # Keep as grams, remove trailing zeros
                if grams == int(grams):
                    return f"{int(grams)}g"
                else:
                    return f"{grams}g"
        except ValueError:
            return weight_str
    
    # Handle kilograms
    if weight_str.endswith("kg"):
        try:
            kg = float(weight_str[:-2])
            # Remove trailing zeros
            if kg == int(kg):
                return f"{int(kg)}kg"
            else:
                return f"{kg}kg"
        except ValueError:
            return weight_str
    
    return weight_str

def weight_to_grams(weight_str):
    """
    Convert weight string to grams (float)
    
    Examples:
        "0.35" -> 350 (assume kg if < 1)
        "0.35kg" -> 350
        "350g" -> 350
        "700g" -> 700
        "0.7kg" -> 700
        "1kg" -> 1000
        "1" -> 1000 (assume kg if >= 1 and round number)
    
    Args:
        weight_str: Weight string with or without unit
    
    Returns:
        int: Weight in grams, or None if invalid
    """
    if not weight_str or pd.isna(weight_str):
        return None
    
    try:
        weight_str = str(weight_str).strip().lower().replace(" ", "")
        
        # Remove units and get numeric value
        if weight_str.endswith("kg"):
            kg = float(weight_str[:-2])
            return int(kg * 1000)
        elif weight_str.endswith("g"):
            return int(float(weight_str[:-1]))
        else:
            # No unit - assume kg if < 1, grams if >= 1
            value = float(weight_str)
            if value < 1:
                return int(value * 1000)  # Assume kg
            else:
                # For values >= 1, check if it's more likely kg or grams
                # If it's a round number like 1, 2, 5, assume kg
                # If it's like 350, 700, assume grams
                if value == int(value) and value <= 10:
                    return int(value * 1000)  # Assume kg (1, 2, 5 kg)
                else:
                    return int(value)  # Assume grams (350, 700, etc.)
    except (ValueError, AttributeError):
        return None

def weights_match(weight1, weight2):
    """
    Check if two weight strings represent the same weight
    Handles conversions: 0.35kg = 350g, 0.7kg = 700g, etc.
    
    Args:
        weight1: First weight string (e.g., "0.35", "0.35kg", "350g")
        weight2: Second weight string (e.g., "350g", "0.35kg")
    
    Returns:
        bool: True if weights match (within 0.01g tolerance)
    """
    # Convert both to grams and compare
    grams1 = weight_to_grams(weight1)
    grams2 = weight_to_grams(weight2)
    
    if grams1 is None or grams2 is None:
        return False
    
    # Use small tolerance for floating point comparison
    return abs(grams1 - grams2) < 0.01

def parse_sku_id(sku_id):
    """
    Parse SKU ID like "1 Sattu 1kg" into product name and weight
    
    SKU ID Format: number + product name + weight
    Examples:
        "1 Sattu 1kg" → ("Sattu", "1kg")
        "1 Bihari Coconut Thekua 350g" → ("Bihari Coconut Thekua", "350g")
        "1 ragi atta 1kg" → ("ragi atta", "1kg")
        "1 makai atta 1kg" → ("makai atta", "1kg")
        "1 Moori 250g" → ("Moori", "250g")
        "1 Bihari Thekua 350g" → ("Bihari Thekua", "350g")
    
    Args:
        sku_id: SKU ID string from Flipkart invoice (may include description after pipe)
    
    Returns:
        tuple: (product_name, weight) or (None, None) if parsing fails
    """
    if not sku_id or pd.isna(sku_id):
        return None, None
    
    sku_id = str(sku_id).strip()
    
    # Remove description part if pipe separator exists (SKU ID is before the pipe)
    if "|" in sku_id:
        sku_id = sku_id.split("|")[0].strip()
    
    # Pattern 1: Extract weight first (more reliable)
    # Look for weight pattern at the end: "Product Name 350g" or "Product Name 1kg"
    weight_pattern = re.compile(r'(\d+(?:\.\d+)?(?:kg|g))', re.IGNORECASE)
    weight_matches = list(weight_pattern.finditer(sku_id))
    
    if weight_matches:
        # Use the last weight match (most likely to be the actual weight)
        last_weight_match = weight_matches[-1]
        weight = last_weight_match.group(1)
        weight_normalized = normalize_weight(weight)
        
        # Extract product name by removing weight and leading number
        weight_start = last_weight_match.start()
        product_name = sku_id[:weight_start].strip()
        # Remove leading number if present
        product_name = re.sub(r'^\d+\s+', '', product_name).strip()
        
        if product_name:
            return product_name, weight_normalized
    
    # Pattern 2: "1 Product Name Weight" with space before weight (most common)
    pattern2 = re.compile(r'^\d+\s+(.+?)\s+(\d+(?:\.\d+)?(?:kg|g))$', re.IGNORECASE)
    match = pattern2.match(sku_id)
    if match:
        product_name = match.group(1).strip()
        weight = match.group(2).strip()
        weight_normalized = normalize_weight(weight)
        return product_name, weight_normalized
    
    # Pattern 3: "1 Product Name" (no weight in SKU, may have trailing number like "1 Bihari Coconut Thekua 3")
    # First, try to extract product name by removing leading number and trailing standalone number
    pattern3 = re.compile(r'^\d+\s+(.+)$')
    match = pattern3.match(sku_id)
    if match:
        product_name = match.group(1).strip()
        # Check if product name ends with a standalone number (not weight unit)
        # Remove trailing number if it's not part of a weight pattern
        trailing_num_match = re.search(r'\s+(\d+)$', product_name)
        if trailing_num_match:
            # Check if this number is likely a quantity or variant, not weight
            # If the number is small (1-10) and there's no weight unit before it, it's likely not weight
            trailing_num = trailing_num_match.group(1)
            if int(trailing_num) <= 10:
                # Remove the trailing number
                product_name = product_name[:trailing_num_match.start()].strip()
        return product_name, None
    
    # Fallback: return as-is without weight
    product_name = re.sub(r'^\d+\s+', '', sku_id).strip()
    # Remove trailing standalone numbers (likely quantities, not weights)
    trailing_num_match = re.search(r'\s+(\d+)$', product_name)
    if trailing_num_match and int(trailing_num_match.group(1)) <= 10:
        product_name = product_name[:trailing_num_match.start()].strip()
    
    if product_name:
        return product_name, None
    
    return None, None

def extract_sku_from_page(page_text):
    """
    Extract SKU IDs from Flipkart invoice page text
    
    Looks for table format: "SKU ID | Description | QTY"
    SKU ID format: "1 Product Name Weight"
    
    Args:
        page_text: Full text content of the PDF page
    
    Returns:
        list: List of tuples (sku_id, description, quantity) or empty list
    """
    if not page_text:
        return []
    
    products = []
    lines = page_text.split("\n")
    
    # Find table header
    table_start_idx = None
    for i, line in enumerate(lines):
        if "SKU ID" in line and ("Description" in line or "QTY" in line):
            table_start_idx = i
            break
    
    if table_start_idx is None:
        # Try alternative: look for product descriptions directly
        # Pattern: "1 Product Name Weight | Description | QTY"
        for i, line in enumerate(lines):
            # Look for lines starting with number followed by product name
            sku_match = re.match(r'^(\d+\s+[A-Za-z].*?)\s*\|\s*(.*?)\s*\|\s*(\d+)', line)
            if sku_match:
                sku_id = sku_match.group(1).strip()
                description = sku_match.group(2).strip()
                qty = int(sku_match.group(3))
                products.append((sku_id, description, qty))
        return products
    
    # Parse table rows after header
    for i in range(table_start_idx + 1, len(lines)):
        line = lines[i].strip()
        if not line:
            continue
        
        # Stop if we hit a section that's not part of the table
        if any(stop_word in line.upper() for stop_word in ["SOLD BY", "SHIPPING", "AWB", "ORDERED", "HBD", "CPD"]):
            break
        
        # Pattern: "1 Product Name Weight | Description | QTY"
        # Try full table row pattern first
        table_row_match = re.match(r'^(\d+\s+[A-Za-z].*?)\s*\|\s*(.*?)\s*\|\s*(\d+)', line)
        if table_row_match:
            sku_id = table_row_match.group(1).strip()
            description = table_row_match.group(2).strip()
            qty = int(table_row_match.group(3))
            products.append((sku_id, description, qty))
            continue
        
        # Pattern: "1 Product Name Weight" (SKU ID only, quantity might be on next line)
        sku_only_match = re.match(r'^(\d+\s+[A-Za-z].*?)$', line)
        if sku_only_match:
            sku_id = sku_only_match.group(1).strip()
            # Look ahead for quantity
            qty = 1
            for j in range(i + 1, min(i + 3, len(lines))):
                qty_match = re.search(r'\bQTY\s*:?\s*(\d+)\b', lines[j], re.IGNORECASE)
                if qty_match:
                    qty = int(qty_match.group(1))
                    break
                # Also check for standalone number
                num_match = re.match(r'^\s*(\d+)\s*$', lines[j])
                if num_match:
                    qty = int(num_match.group(1))
                    break
            
            # Try to extract description from same line or next line
            description = ""
            if "|" in line:
                parts = line.split("|")
                if len(parts) > 1:
                    description = parts[1].strip()
            else:
                # Check next line for description
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if "MITHILA" in next_line.upper() or "FOODS" in next_line.upper():
                        description = next_line
            
            products.append((sku_id, description, qty))
    
    return products

def get_product_from_fk_sku(sku_id, master_df):
    """
    Match products in master data by FK SKU column (direct SKU matching)
    
    Also checks "M" column if FK SKU match fails
    
    Args:
        sku_id: Full SKU ID from Flipkart invoice (e.g., "1 Sattu 1kg")
        master_df: Master data DataFrame with FK SKU and M columns
    
    Returns:
        pandas.DataFrame: Matching rows from master_df, or empty DataFrame if no match
    """
    if master_df is None or master_df.empty:
        return pd.DataFrame()
    
    # Check for FK SKU column (case-insensitive)
    fk_sku_column = None
    m_column = None
    for col in master_df.columns:
        col_lower = col.lower().strip()
        if 'fk' in col_lower and 'sku' in col_lower:
            fk_sku_column = col
        elif col_lower == 'm' or col_lower.startswith('m '):
            m_column = col
    
    if fk_sku_column is None:
        logger.warning("Master data missing 'FK SKU' column")
        return pd.DataFrame()
    
    if not sku_id:
        return pd.DataFrame()
    
    # Clean SKU ID - remove leading number and normalize
    sku_clean = str(sku_id).strip()
    # Remove leading number if present
    sku_clean = re.sub(r'^\d+\s+', '', sku_clean).strip()
    
    # Try exact match first on FK SKU
    exact_match = master_df[
        master_df[fk_sku_column].astype(str).str.strip().str.lower() == sku_clean.lower()
    ]
    if not exact_match.empty:
        logger.info(f"Found FK SKU exact match for '{sku_id}'")
        return exact_match
    
    # Try partial match (contains) on FK SKU
    partial_match = master_df[
        master_df[fk_sku_column].astype(str).str.contains(sku_clean, case=False, na=False)
    ]
    if not partial_match.empty:
        logger.info(f"Found FK SKU partial match for '{sku_id}'")
        return partial_match
    
    # Try reverse - check if master FK SKU is contained in invoice SKU
    reverse_match = master_df[
        master_df[fk_sku_column].astype(str).apply(
            lambda x: str(x).strip().lower() in sku_clean.lower() if pd.notna(x) else False
        )
    ]
    if not reverse_match.empty:
        logger.info(f"Found FK SKU reverse match for '{sku_id}'")
        return reverse_match
    
    # If M column exists, try matching with it
    if m_column:
        m_exact_match = master_df[
            master_df[m_column].astype(str).str.strip().str.lower() == sku_clean.lower()
        ]
        if not m_exact_match.empty:
            logger.info(f"Found M column exact match for '{sku_id}'")
            return m_exact_match
        
        m_partial_match = master_df[
            master_df[m_column].astype(str).str.contains(sku_clean, case=False, na=False)
        ]
        if not m_partial_match.empty:
            logger.info(f"Found M column partial match for '{sku_id}'")
            return m_partial_match
    
    logger.warning(f"No FK SKU match found for '{sku_id}'")
    return pd.DataFrame()

def get_product_from_name_weight(product_name, weight, master_df):
    """
    Match products in master data by product name and weight
    
    Uses fuzzy matching to handle variations in product names.
    Matches by:
    1. Exact name + weight match
    2. Normalized weight match + name contains
    3. Normalized weight match + partial name match
    
    Args:
        product_name: Product name from SKU ID (e.g., "Sattu", "Bihari Coconut Thekua")
        weight: Weight from SKU ID (e.g., "1kg", "350g")
        master_df: Master data DataFrame with Name and Net Weight columns
    
    Returns:
        pandas.DataFrame: Matching rows from master_df, or empty DataFrame if no match
    """
    if master_df is None or master_df.empty:
        return pd.DataFrame()
    
    # Use flexible column matching for Name and Net Weight
    name_col = find_column_flexible(master_df, ['Name'])
    net_weight_col = find_column_flexible(master_df, ['Net Weight', 'NetWeight'])
    
    if not name_col or not net_weight_col:
        logger.warning(f"Master data missing 'Name' or 'Net Weight' columns. Found: {list(master_df.columns)}")
        return pd.DataFrame()
    
    if not product_name:
        return pd.DataFrame()
    
    # Normalize weight for comparison
    weight_normalized = normalize_weight(weight) if weight else None
    
    # Normalize master data weights
    master_df = master_df.copy()
    master_df["Net Weight Normalized"] = master_df[net_weight_col].apply(normalize_weight)
    
    # Strategy 1: Exact name match + weight match
    if weight_normalized:
        exact_name_match = master_df[
            (master_df[name_col].str.strip().str.lower() == product_name.strip().lower()) &
            (master_df["Net Weight Normalized"] == weight_normalized)
        ]
        if not exact_name_match.empty:
            logger.info(f"Found exact match for '{product_name}' {weight}")
            return exact_name_match
    
    # Strategy 2: Name contains + weight match
    if weight_normalized:
        name_contains_match = master_df[
            (master_df[name_col].str.contains(product_name, case=False, na=False)) &
            (master_df["Net Weight Normalized"] == weight_normalized)
        ]
        if not name_contains_match.empty:
            logger.info(f"Found name contains match for '{product_name}' {weight}")
            return name_contains_match
    
    # Strategy 3: Partial name match (split product name into words)
    if weight_normalized:
        product_words = [w.strip() for w in product_name.split() if len(w.strip()) > 2]
        for word in product_words:
            partial_match = master_df[
                (master_df[name_col].str.contains(word, case=False, na=False)) &
                (master_df["Net Weight Normalized"] == weight_normalized)
            ]
            if not partial_match.empty:
                logger.info(f"Found partial match for '{product_name}' {weight} using word '{word}'")
                return partial_match
    
    # Strategy 4: Name match only (if weight not provided)
    if not weight_normalized:
        name_only_match = master_df[
            master_df[name_col].str.contains(product_name, case=False, na=False)
        ]
        if not name_only_match.empty:
            logger.info(f"Found name-only match for '{product_name}' (no weight)")
            return name_only_match
    
    # Strategy 5: Try matching common product name variations
    # Handle cases like "Sattu" vs "Bihari Chana Sattu"
    if weight_normalized:
        # Extract key product words (remove common descriptors)
        key_words = []
        for word in product_name.split():
            word_lower = word.lower()
            # Skip common descriptors
            if word_lower not in ["bihari", "mithila", "foods", "desi", "plain", "high", "protein"]:
                if len(word) > 2:
                    key_words.append(word)
        
        if key_words:
            # Try matching with key words
            for key_word in key_words:
                key_match = master_df[
                    (master_df[name_col].str.contains(key_word, case=False, na=False)) &
                    (master_df["Net Weight Normalized"] == weight_normalized)
                ]
                if not key_match.empty:
                    logger.info(f"Found key word match for '{product_name}' {weight} using '{key_word}'")
                    return key_match
    
    logger.warning(f"No match found for product '{product_name}' with weight '{weight}'")
    return pd.DataFrame()

def extract_product_info_flipkart(pdf_bytes):
    """
    Main extraction function for Flipkart invoices
    
    Extracts all product information from Flipkart PDF invoices:
    - SKU IDs
    - Product names and weights (parsed from SKU)
    - Quantities
    - Descriptions
    
    Args:
        pdf_bytes: PDF file bytes
    
    Returns:
        dict: {
            'products': list of dicts with keys: sku_id, product_name, weight, description, qty,
            'order_id': Order ID if found,
            'awb_number': AWB number if found
        }
    """
    result = {
        'products': [],
        'order_id': None,
        'awb_number': None
    }
    
    try:
        with safe_pdf_context(pdf_bytes) as doc:
            full_text = ""
            for page in doc:
                full_text += page.get_text() + "\n"
            
            # Extract order ID
            order_id_match = re.search(r'OD\d+', full_text)
            if order_id_match:
                result['order_id'] = order_id_match.group(0)
            
            # Extract AWB number
            awb_match = re.search(r'AWB\s+No\.\s*(FMP[CP]\d+)', full_text, re.IGNORECASE)
            if awb_match:
                result['awb_number'] = awb_match.group(1)
            
            # Extract products from each page
            for page_num, page in enumerate(doc):
                page_text = page.get_text()
                sku_products = extract_sku_from_page(page_text)
                
                for sku_id, description, qty in sku_products:
                    # Clean SKU ID - remove description part if pipe exists
                    clean_sku_id = sku_id
                    if "|" in clean_sku_id:
                        clean_sku_id = clean_sku_id.split("|")[0].strip()
                    
                    product_name, weight = parse_sku_id(clean_sku_id)
                    
                    # Convert None to empty string immediately for consistent handling
                    if product_name is None:
                        product_name = ''
                    if weight is None:
                        weight = ''
                    
                    product_info = {
                        'sku_id': clean_sku_id,  # Store cleaned SKU without description
                        'product_name': product_name,
                        'weight': weight,
                        'description': description,
                        'qty': qty,
                        'page': page_num + 1
                    }
                    result['products'].append(product_info)
                    
                    logger.info(f"Extracted: SKU={clean_sku_id}, Product={product_name}, Weight={weight}, Qty={qty}")
    
    except Exception as e:
        logger.error(f"Error extracting product info from Flipkart PDF: {str(e)}")
        raise
    
    return result

# Test function (for development)
def test_extraction(pdf_bytes):
    """
    Test function to verify extraction works correctly
    """
    result = extract_product_info_flipkart(pdf_bytes)
    
    print(f"Order ID: {result['order_id']}")
    print(f"AWB Number: {result['awb_number']}")
    print(f"Products found: {len(result['products'])}")
    
    for product in result['products']:
        print(f"  - SKU: {product['sku_id']}")
        print(f"    Product: {product['product_name']}")
        print(f"    Weight: {product['weight']}")
        print(f"    Qty: {product['qty']}")
        print(f"    Description: {product['description']}")
    
    return result

def detect_shipping_label_boundary(page):
    """
    Detect the Y-coordinate where shipping label section ends (above horizontal line)
    
    Uses multiple methods:
    1. Text-based: Look for "Tax Invoice" header
    2. Line detection: Find horizontal lines/strokes
    3. Fallback: Use ~60% of page height
    
    Args:
        page: PyMuPDF page object
    
    Returns:
        float: Y-coordinate where shipping label ends (crop boundary), validated to be reasonable
    """
    try:
        page_rect = page.rect
        page_height = page_rect.height
        
        if page_height <= 0:
            logger.warning(f"Invalid page height: {page_height}, using default")
            return page_height * 0.6 if page_height > 0 else 400  # Fallback to 400 if height is 0
        
        # Method 1: Text-based detection - look for "Tax Invoice" header
        try:
            text_dict = page.get_text("dict")
            for block in text_dict.get("blocks", []):
                if "lines" in block:
                    for line in block["lines"]:
                        for span in line.get("spans", []):
                            text = span.get("text", "").strip()
                            if "Tax Invoice" in text or "TAX INVOICE" in text.upper():
                                # Get Y coordinate of this text
                                bbox = span.get("bbox", [])
                                if len(bbox) >= 4:
                                    y_coord = bbox[1]  # Top Y coordinate
                                    # Validate y_coord is reasonable
                                    if 50 < y_coord < page_height * 0.9:
                                        logger.info(f"Found 'Tax Invoice' at Y={y_coord}")
                                        return y_coord
        except Exception as e:
            logger.debug(f"Text-based detection failed: {e}")
        
        # Method 2: Look for horizontal lines using drawing detection
        try:
            drawings = page.get_drawings()
            horizontal_lines = []
            for drawing in drawings:
                if "items" in drawing:
                    for item in drawing["items"]:
                        if item[0] == "l":  # Line item
                            x0, y0, x1, y1 = item[1]
                            # Check if line is mostly horizontal (small Y difference)
                            if abs(y1 - y0) < 5 and abs(x1 - x0) > page_rect.width * 0.3:
                                # Horizontal line found
                                avg_y = (y0 + y1) / 2
                                horizontal_lines.append(avg_y)
            
            if horizontal_lines:
                # Use the first significant horizontal line (likely the separator)
                horizontal_lines.sort()
                # Filter lines that are in the middle portion of page (likely separator)
                for line_y in horizontal_lines:
                    if page_height * 0.3 < line_y < page_height * 0.8:
                        logger.info(f"Found horizontal line separator at Y={line_y}")
                        return line_y
        except Exception as e:
            logger.debug(f"Line detection failed: {e}")
        
        # Method 3: Fallback - use ~60% of page height
        default_y = page_height * 0.6
        # Validate default_y is reasonable
        if default_y < 50:
            default_y = 400  # Minimum reasonable height
        elif default_y > page_height * 0.95:
            default_y = page_height * 0.6  # Ensure it's not too close to page height
        
        logger.info(f"Using default crop boundary at Y={default_y} (60% of page height)")
        return default_y
        
    except Exception as e:
        logger.error(f"Error detecting shipping label boundary: {e}", exc_info=True)
        # Fallback to 60% of page height, with validation
        try:
            fallback = page.rect.height * 0.6
            return max(400, min(fallback, page.rect.height * 0.9))  # Clamp between 400 and 90% of height
        except:
            return 400  # Absolute fallback

def crop_shipping_label(page):
    """
    Crop page to extract only the shipping label section using fixed margins.
    
    Uses vector-based method (show_pdf_page) as primary to maintain quality,
    with 300 DPI pixmap as fallback for high-quality output.
    
    Fixed margins (from user's PDF viewer):
    - Top: 0.76 cm
    - Left: 6.49 cm
    - Right: 6.49 cm
    - Bottom: 16.14 cm
    
    Args:
        page: PyMuPDF page object
    
    Returns:
        PyMuPDF page object: New page with cropped content (shipping label only), or None if error
    """
    try:
        page_rect = page.rect
        page_width = page_rect.width
        page_height = page_rect.height
        
        # Validate page dimensions
        if page_width <= 0 or page_height <= 0:
            logger.error(f"Invalid page dimensions: {page_width}x{page_height}")
            return None
        
        # Fixed crop margins in centimeters (from user's PDF viewer)
        TOP_MARGIN_CM = 0.76
        LEFT_MARGIN_CM = 6.49
        RIGHT_MARGIN_CM = 6.49
        BOTTOM_MARGIN_CM = 16.14
        
        # Convert cm to points (1 cm = 28.35 points in PDF)
        CM_TO_POINTS = 28.35
        
        top_margin_pt = TOP_MARGIN_CM * CM_TO_POINTS
        left_margin_pt = LEFT_MARGIN_CM * CM_TO_POINTS
        right_margin_pt = RIGHT_MARGIN_CM * CM_TO_POINTS
        bottom_margin_pt = BOTTOM_MARGIN_CM * CM_TO_POINTS
        
        # Calculate crop rectangle based on margins
        # Crop from (left_margin, top_margin) to (width - right_margin, height - bottom_margin)
        crop_x0 = left_margin_pt
        crop_y0 = top_margin_pt
        crop_x1 = page_width - right_margin_pt
        crop_y1 = page_height - bottom_margin_pt
        
        # Validate crop rectangle
        if crop_x1 <= crop_x0 or crop_y1 <= crop_y0:
            logger.error(f"Invalid crop rectangle: ({crop_x0}, {crop_y0}) to ({crop_x1}, {crop_y1})")
            return None
        
        crop_width = crop_x1 - crop_x0
        crop_height = crop_y1 - crop_y0
        
        logger.debug(f"Cropping page: {page_width}x{page_height} to {crop_width}x{crop_height}")
        logger.debug(f"Margins: Top={TOP_MARGIN_CM}cm, Left={LEFT_MARGIN_CM}cm, Right={RIGHT_MARGIN_CM}cm, Bottom={BOTTOM_MARGIN_CM}cm")
        
        # Create crop rectangle
        crop_rect = fitz.Rect(crop_x0, crop_y0, crop_x1, crop_y1)
        
        # Create new temporary document with one page
        # Use exact dimensions to match crop rectangle
        temp_doc = fitz.open()
        new_page = temp_doc.new_page(width=crop_width, height=crop_height)
        
        # PRIMARY METHOD: Use show_pdf_page (vector-based, maintains quality)
        # This preserves vector graphics, text, and barcodes without quality loss
        try:
            # Identity matrix for 1:1 scaling (no distortion)
            mat = fitz.Matrix(1, 0, 0, 1, 0, 0)
            
            # Use show_pdf_page with clip to copy only the cropped region
            # This maintains vector quality - no rasterization
            new_page.show_pdf_page(
                fitz.Rect(0, 0, crop_width, crop_height),  # Destination rectangle (exact match)
                page.parent,  # Source document
                page.number,  # Source page number
                clip=crop_rect,  # Clip to crop rectangle
                matrix=mat  # Identity matrix (1:1 scaling)
            )
            
            logger.info(f"✅ Using vector method (show_pdf_page) - maintains quality with small file size")
            logger.debug(f"Successfully cropped page using vector method (show_pdf_page)")
            
        except Exception as vector_error:
            logger.warning(f"Vector method (show_pdf_page) failed: {vector_error}, trying 300 DPI pixmap fallback")
            
            # FALLBACK METHOD: Use 300 DPI pixmap for high quality
            # Only used if vector method fails
            try:
                # Calculate matrix for 300 DPI (high quality)
                # Default is 72 DPI, so 300/72 = 4.167 scaling factor
                dpi_scale = 300.0 / 72.0
                high_dpi_matrix = fitz.Matrix(dpi_scale, 0, 0, dpi_scale, 0, 0)
                
                # Get pixmap of the cropped region at 300 DPI
                pix = page.get_pixmap(matrix=high_dpi_matrix, clip=crop_rect)
                
                # Insert the high-resolution pixmap as an image into the new page
                # Scale back down to original size for display
                new_page.insert_image(
                    fitz.Rect(0, 0, crop_width, crop_height),
                    pixmap=pix
                )
                
                pix = None  # Free memory
                
                logger.warning(f"⚠️ Using 300 DPI pixmap fallback - file size will be larger than vector method")
                logger.debug(f"Successfully cropped page using 300 DPI pixmap fallback")
                
            except Exception as pixmap_error:
                logger.error(f"Both cropping methods failed: vector={vector_error}, pixmap={pixmap_error}")
                temp_doc.close()
                return None
        
        # Return the page (temp_doc will be kept open until sorted_pdf is created)
        logger.debug(f"Successfully cropped page to {crop_width}x{crop_height}")
        return new_page
        
    except Exception as e:
        logger.error(f"Error cropping shipping label: {e}", exc_info=True)
        return None

def extract_product_from_shipping_label(page_text):
    """
    Extract product info from shipping label section only (before "Tax Invoice")
    
    Args:
        page_text: Full text content of the PDF page
    
    Returns:
        list: List of product info dicts with keys: sku_id, product_name, weight, qty
    """
    if not page_text:
        return []
    
    # Split text at "Tax Invoice" to get only shipping label section
    if "Tax Invoice" in page_text or "TAX INVOICE" in page_text.upper():
        # Find where "Tax Invoice" starts
        lines = page_text.split("\n")
        shipping_label_text = ""
        for i, line in enumerate(lines):
            if "Tax Invoice" in line or "TAX INVOICE" in line.upper():
                # Take everything before this line
                shipping_label_text = "\n".join(lines[:i])
                break
        if not shipping_label_text:
            shipping_label_text = page_text
    else:
        shipping_label_text = page_text
    
    # Use existing extraction function but on shipping label text only
    sku_products = extract_sku_from_page(shipping_label_text)
    
    products = []
    for sku_id, description, qty in sku_products:
        # Clean SKU ID - remove description part if pipe exists
        clean_sku_id = sku_id
        if "|" in clean_sku_id:
            clean_sku_id = clean_sku_id.split("|")[0].strip()
        
        product_name, weight = parse_sku_id(clean_sku_id)
        
        # Convert None to empty string
        if product_name is None:
            product_name = ''
        if weight is None:
            weight = ''
        
        products.append({
            'sku_id': clean_sku_id,
            'product_name': product_name,
            'weight': weight,
            'qty': qty
        })
    
    return products

def highlight_large_qty_flipkart(page, products=None, total_qty=None):
    """
    Highlight quantities > 1 in shipping label section
    
    Also highlights when same product appears multiple times (even if each shows QTY 1)
    
    Args:
        page: PyMuPDF page object (should be cropped to shipping label)
        products: Optional list of product dicts to help detect duplicates
        total_qty: Optional total quantity (sum of all products)
    
    Returns:
        int: Number of blocks highlighted
    """
    try:
        logger.info("🎨 HIGHLIGHTING START: highlight_large_qty_flipkart() called")
        logger.info(f"   Page info: width={page.rect.width:.1f}, height={page.rect.height:.1f}, page_num={page.number}")
        logger.info(f"   Parameters: total_qty={total_qty}, products_count={len(products) if products else 0}")
        
        highlighted_count = 0
        page_text = page.get_text()
        logger.debug(f"   Page text length: {len(page_text)} characters")
        
        # Detect if same product appears multiple times (for logging/info purposes)
        has_duplicate_products = False
        if products and len(products) > 1:
            # Simple check: if we have multiple products, check if any have same name+weight
            product_identifiers = {}
            for p in products:
                p_name = p.get('product_name', '').strip().lower()
                p_weight = p.get('weight', '').strip().lower()
                if p_name and p_weight:
                    identifier = (p_name, p_weight)
                    if identifier in product_identifiers:
                        has_duplicate_products = True
                        logger.info(f"   🔍 Duplicate product detected: {p_name} ({p_weight})")
                        break
                    product_identifiers[identifier] = True
            
            # Log if multiple products (same or different)
            if not has_duplicate_products:
                logger.info(f"   🔍 Multiple different products detected: {len(products)} products")
        
        # If total_qty > 1 or multiple products detected (same or different), highlight all product rows
        should_highlight_all = (total_qty and total_qty > 1) or (products and len(products) > 1)
        
        logger.info(f"   Decision: should_highlight={should_highlight_all}, total_qty={total_qty}, duplicates={has_duplicate_products}, products={len(products) if products else 0}")
        
        if not should_highlight_all:
            logger.info("   ⏭️  No highlighting needed - total_qty <= 1 and only 1 product")
            return 0
        
        # Get text blocks for precise highlighting
        text_blocks = page.get_text("blocks")
        logger.info(f"   📄 Processing {len(text_blocks)} text blocks for highlighting")
        
        # Collect all blocks that contain product information
        blocks_to_highlight = []
        in_table = False
        page_width = page.rect.width
        logger.debug(f"   Page width: {page_width:.1f} points")
        
        for block_idx, block in enumerate(text_blocks):
            if len(block) < 5:
                continue
            x0, y0, x1, y1, text = block[:5]
            
            # Detect table start
            if "SKU ID" in text or ("Description" in text and "QTY" in text):
                in_table = True
                logger.debug(f"Table detected at block {block_idx}: {text[:50]}")
                continue
            
            # If we're in the product table area
            if in_table:
                # Stop if we hit end of table
                if any(stop_word in text.upper() for stop_word in ["SOLD BY", "SHIPPING", "AWB", "ORDERED", "HBD", "CPD", "TAX INVOICE"]):
                    in_table = False
                    logger.debug(f"Table ended at block {block_idx}")
                    continue
                
                # Skip header blocks
                if any(header in text for header in ["SKU ID", "Description", "QTY"]):
                    continue
                
                # Check if this looks like a product row
                is_product_row = False
                
                # Method 1: Check for product row pattern with pipe separator
                if "|" in text:
                    # Pattern: "1 Product | Description | QTY"
                    row_match = re.search(r'(\d+)\s+[A-Za-z].*?\|', text)
                    if row_match:
                        is_product_row = True
                        logger.debug(f"Found product row (pipe pattern): {text[:60]}...")
                
                # Method 2: Check for product row starting with number + letter
                if not is_product_row:
                    # Pattern: "1 Product Name Weight"
                    row_match = re.search(r'^\s*(\d+)\s+[A-Za-z]', text.strip())
                    if row_match:
                        is_product_row = True
                        logger.debug(f"Found product row (number+letter pattern): {text[:60]}...")
                
                # Method 3: Check if text contains any product name from products list
                if not is_product_row and products:
                    for p in products:
                        p_name = p.get('product_name', '').strip()
                        p_sku = p.get('sku_id', '').strip()
                        if p_name and p_name.lower() in text.lower():
                            is_product_row = True
                            logger.debug(f"Found product row (name match): {p_name}")
                            break
                        if p_sku and p_sku in text:
                            is_product_row = True
                            logger.debug(f"Found product row (SKU match): {p_sku}")
                            break
                
                if is_product_row:
                    # Store block info for highlighting (mark as table row)
                    blocks_to_highlight.append({
                        'block_idx': block_idx,
                        'x0': x0,
                        'y0': y0,
                        'x1': x1,
                        'y1': y1,
                        'text': text,
                        'is_table_row': True
                    })
            
            # Also check blocks outside table for quantities > 1
            if not in_table:
                # Skip blocks without digits
                if not any(char.isdigit() for char in text):
                    continue
                
                # Skip obvious header blocks
                if any(header in text for header in ["SKU ID", "Description", "QTY", "AWB", "Order ID"]):
                    continue
                
                # Look for quantities > 1
                should_highlight = False
                found_qty = None
                
                # Look for QTY patterns first (most reliable)
                qty_patterns = re.findall(r'QTY\s*:?\s*(\d+)', text, re.IGNORECASE)
                for qty_str in qty_patterns:
                    qty_val = int(qty_str)
                    if qty_val > 1:
                        should_highlight = True
                        found_qty = qty_val
                        break
                
                # Look for table row patterns: "1 Product Name | Description | QTY"
                if not should_highlight:
                    table_row_match = re.search(r'\|\s*(\d+)\s*$', text.strip())
                    if table_row_match:
                        qty_val = int(table_row_match.group(1))
                        if qty_val > 1:
                            should_highlight = True
                            found_qty = qty_val
                
                # Look for standalone numbers > 1 (last resort)
                if not should_highlight:
                    values = text.split()
                    for val in values:
                        if val.isdigit():
                            qty_val = int(val)
                            if qty_val > 1 and qty_val <= 100:
                                should_highlight = True
                                found_qty = qty_val
                                break
                
                if should_highlight:
                    blocks_to_highlight.append({
                        'block_idx': block_idx,
                        'x0': x0,
                        'y0': y0,
                        'x1': x1,
                        'y1': y1,
                        'text': text,
                        'qty': found_qty,
                        'is_table_row': False
                    })
        
        # Now highlight all collected blocks
        logger.info(f"   🎯 Found {len(blocks_to_highlight)} blocks to highlight")
        
        if len(blocks_to_highlight) == 0:
            logger.warning("   ⚠️  No blocks found to highlight - this may indicate a problem with block detection")
        
        for block_idx, block_info in enumerate(blocks_to_highlight):
            logger.debug(f"   Highlighting block {block_idx + 1}/{len(blocks_to_highlight)}: {block_info.get('text', '')[:60]}...")
            x0 = block_info['x0']
            y0 = block_info['y0']
            x1 = block_info['x1']
            y1 = block_info['y1']
            text = block_info['text']
            
            # Create highlight rectangle - use full width for product rows
            is_table_row = block_info.get('is_table_row', False)
            if is_table_row or "|" in text:
                # Product row - highlight full width
                highlight_box = fitz.Rect(0, y0 - 1, page_width, y1 + 1)
            else:
                # Other blocks - use block dimensions
                highlight_box = fitz.Rect(x0, y0, x1, y1)
            
            # PRIMARY METHOD: Use highlight annotations (more reliably preserved during PDF operations)
            # This is especially important when pages are inserted into other documents
            try:
                annot = page.add_highlight_annot(highlight_box)
                # Set red color for highlight
                annot.set_colors(stroke=(1, 0, 0), fill=(1, 0, 0))
                annot.set_opacity(0.4)  # Semi-transparent red
                annot.update()
                highlighted_count += 1
                logger.debug(f"      ✅ Block {block_info['block_idx']} highlighted using annotation method (rect: {x0:.1f},{y0:.1f} to {x1:.1f},{y1:.1f})")
            except Exception as annot_error:
                logger.warning(f"      ⚠️  Annotation method failed for block {block_info['block_idx']}: {annot_error}, trying draw_rect fallback")
                # FALLBACK: Use draw_rect if annotations fail
                try:
                    page.draw_rect(highlight_box, color=(1, 0, 0), fill_opacity=0.4)
                    highlighted_count += 1
                    logger.debug(f"      ✅ Block {block_info['block_idx']} highlighted using draw_rect fallback method")
                except Exception as draw_error:
                    logger.error(f"      ❌ Both highlight methods failed for block {block_info['block_idx']}: annot={annot_error}, draw={draw_error}")
        
        logger.info(f"✅ HIGHLIGHTING COMPLETE: {highlighted_count} out of {len(blocks_to_highlight)} blocks successfully highlighted")
        if highlighted_count == 0 and len(blocks_to_highlight) > 0:
            logger.error(f"   ❌ WARNING: Found {len(blocks_to_highlight)} blocks but failed to highlight any of them!")
        return highlighted_count
    except Exception as e:
        logger.error(f"Error highlighting shipping label: {e}", exc_info=True)
        return 0

def sort_pdf_by_sku_flipkart(pdf_bytes, master_df=None):
    """
    Sort Flipkart invoice PDFs by product name/SKU and highlight quantities > 1
    
    Process:
    1. For each page: crop to shipping label section
    2. Extract product info from shipping label
    3. Sort pages by (product_name, weight, sku_id)
    4. Apply highlighting to pages with qty > 1
    5. Return sorted PDF with only shipping labels
    
    Args:
        pdf_bytes: PDF file bytes
        master_df: Master data DataFrame (optional, for product name lookup)
    
    Returns:
        BytesIO: Sorted PDF buffer with cropped shipping labels, or None if error
    """
    logger.info(f"=== sort_pdf_by_sku_flipkart() called with {len(pdf_bytes) if pdf_bytes else 0} bytes ===")
    try:
        with safe_pdf_context(pdf_bytes) as doc:
            total_pages = len(doc)
            logger.info(f"PDF opened successfully: {total_pages} pages")
            
            if total_pages == 0:
                logger.warning("❌ Empty PDF provided")
                return None
            
            # Process each page: crop and extract product info
            page_data = []
            for page_num, page in enumerate(doc):
                try:
                    logger.debug(f"Processing page {page_num + 1}/{total_pages}")
                    
                    # Try to crop to shipping label section
                    cropped_page = crop_shipping_label(page)
                    use_cropped = cropped_page is not None
                    
                    if not use_cropped:
                        logger.warning(f"⚠️ Could not crop page {page_num + 1}, using full page as fallback")
                        # Fallback: use original page
                        cropped_page = page
                    
                    # Extract product info from shipping label (or full page if crop failed)
                    try:
                        shipping_label_text = cropped_page.get_text()
                        logger.debug(f"Page {page_num + 1} text length: {len(shipping_label_text)} chars")
                    except Exception as text_error:
                        logger.error(f"Could not extract text from page {page_num + 1}: {text_error}")
                        # Try original page if cropped page fails
                        if use_cropped:
                            try:
                                shipping_label_text = page.get_text()
                                logger.debug(f"Using original page text as fallback")
                            except:
                                logger.error(f"Could not extract text from original page either")
                                continue
                        else:
                            continue
                    
                    products = extract_product_from_shipping_label(shipping_label_text)
                    logger.debug(f"Page {page_num + 1} extracted {len(products)} products")
                    
                    # Get primary product for sorting (use first product or aggregate)
                    if products:
                        # Use first product as primary (most invoices have single product)
                        primary_product = products[0]
                        product_name = primary_product.get('product_name', '')
                        weight = primary_product.get('weight', '')
                        sku_id = primary_product.get('sku_id', '')
                        
                        # Calculate max_qty (individual max) and total_qty (sum of all quantities)
                        max_qty = max(p.get('qty', 1) for p in products)
                        
                        # Calculate total_qty: sum of all quantities
                        # If same product appears multiple times, sum their quantities
                        total_qty = sum(p.get('qty', 1) for p in products)
                        
                        # Check if same product appears multiple times (even if each shows QTY 1)
                        # This is the key fix: detect duplicates by checking (product_name, weight) pairs
                        has_duplicates = False
                        if len(products) > 1:
                            # Create a set to track (product_name, weight) combinations we've seen
                            product_identifiers = set()
                            for p in products:
                                p_name = p.get('product_name', '').strip().lower()
                                p_weight = p.get('weight', '').strip().lower()
                                # Only check if both name and weight are present
                                if p_name and p_weight:
                                    identifier = (p_name, p_weight)
                                    if identifier in product_identifiers:
                                        # Found duplicate! Same product appears multiple times
                                        has_duplicates = True
                                        break
                                    product_identifiers.add(identifier)
                        
                        logger.info(f"Page {page_num + 1}: max_qty={max_qty}, total_qty={total_qty}, has_duplicates={has_duplicates}, products={len(products)}")
                    else:
                        # No products found, use defaults
                        product_name = ''
                        weight = ''
                        sku_id = ''
                        max_qty = 1
                        total_qty = 1
                        has_duplicates = False
                        logger.warning(f"⚠️ Page {page_num + 1}: No products extracted")
                    
                    # Create sort key
                    sort_key = (
                        product_name or "ZZZ_NO_NAME",  # Put unknown at end
                        weight or "ZZZ_NO_WEIGHT",
                        sku_id or "ZZZ_NO_SKU"
                    )
                    
                    page_data.append({
                        'page_num': page_num,
                        'cropped_page': cropped_page,
                        'original_page': page,  # Keep reference to original for fallback
                        'use_cropped': use_cropped,
                        'product_name': product_name,
                        'weight': weight,
                        'sku_id': sku_id,
                        'max_qty': max_qty,
                        'total_qty': total_qty,  # Total quantity (sum of all products)
                        'has_duplicates': has_duplicates,  # Whether same product appears multiple times
                        'sort_key': sort_key,
                        'products': products
                    })
                    
                    status = "cropped" if use_cropped else "full page (fallback)"
                    qty_info = f"Qty={max_qty}" if max_qty == total_qty else f"Qty={max_qty} (Total={total_qty})"
                    logger.info(f"✅ Page {page_num + 1} ({status}): Product={product_name}, Weight={weight}, {qty_info}")
                    
                except Exception as e:
                    logger.error(f"❌ Error processing page {page_num + 1}: {e}", exc_info=True)
                    continue
            
            logger.info(f"Processed {len(page_data)} pages out of {total_pages} total")
            
            if not page_data:
                logger.error("❌ No pages could be processed - returning None")
                return None
            
            # Sort pages by product name, weight, SKU
            logger.info(f"Sorting {len(page_data)} pages...")
            page_data.sort(key=lambda x: x['sort_key'])
            
            # Create new PDF with sorted cropped pages
            logger.info("Creating sorted PDF document...")
            sorted_pdf = fitz.open()
            temp_docs = []  # Keep track of temporary documents to close later
            highlighting_info = []  # Store info for pages that need highlighting: (sorted_pdf_page_index, products, total_qty)
            
            # FIRST PASS: Insert all pages into sorted_pdf (without highlighting)
            # This ensures highlights are drawn directly on final document pages, not temp documents
            for idx, page_info in enumerate(page_data):
                cropped_page = page_info['cropped_page']
                original_page = page_info.get('original_page')
                use_cropped = page_info.get('use_cropped', True)
                max_qty = page_info['max_qty']
                total_qty = page_info.get('total_qty', max_qty)  # Use total_qty if available, fallback to max_qty
                has_duplicates = page_info.get('has_duplicates', False)
                products = page_info.get('products', [])
                
                # Determine if this page needs highlighting
                # 1. Total quantity > 1 (sum of all quantities), OR
                # 2. Multiple products appear (same or different, even if each shows QTY 1)
                should_highlight = total_qty > 1 or len(products) > 1
                
                # Add page to sorted PDF (without highlighting first)
                try:
                    if use_cropped:
                        # Use cropped page from temp document
                        temp_doc = cropped_page.parent
                        # Only track unique documents
                        if temp_doc not in temp_docs:
                            temp_docs.append(temp_doc)
                        
                        sorted_pdf.insert_pdf(
                            temp_doc,  # Source document
                            from_page=cropped_page.number,
                            to_page=cropped_page.number
                        )
                    else:
                        # Use original page directly (fallback when cropping failed)
                        sorted_pdf.insert_pdf(
                            doc,  # Original document
                            from_page=original_page.number,
                            to_page=original_page.number
                        )
                    
                    # Store highlighting info for pages that need it
                    # sorted_pdf page index is len(sorted_pdf) - 1 (just inserted)
                    if should_highlight:
                        sorted_page_idx = len(sorted_pdf) - 1
                        highlighting_info.append({
                            'sorted_page_idx': sorted_page_idx,
                            'products': products,
                            'total_qty': total_qty,
                            'has_duplicates': has_duplicates
                        })
                        logger.debug(f"Page {idx + 1} (sorted_pdf index {sorted_page_idx}) marked for highlighting")
                    
                    logger.debug(f"Inserted page {idx + 1} into sorted PDF")
                except Exception as e:
                    logger.error(f"Error inserting page {idx + 1}: {e}", exc_info=True)
                    # Try fallback: use original page if cropped page fails
                    if use_cropped and original_page:
                        try:
                            logger.info(f"Trying original page as fallback for page {idx + 1}")
                            sorted_pdf.insert_pdf(
                                doc,
                                from_page=original_page.number,
                                to_page=original_page.number
                            )
                            # Store highlighting info if needed
                            if should_highlight:
                                sorted_page_idx = len(sorted_pdf) - 1
                                highlighting_info.append({
                                    'sorted_page_idx': sorted_page_idx,
                                    'products': products,
                                    'total_qty': total_qty,
                                    'has_duplicates': has_duplicates
                                })
                        except Exception as fallback_error:
                            logger.error(f"Fallback also failed for page {idx + 1}: {fallback_error}")
                            continue
                    else:
                        continue
            
            logger.info(f"Sorted PDF created with {len(sorted_pdf)} pages")
            
            # SECOND PASS: Apply highlighting to pages in sorted_pdf (like Amazon does)
            # This ensures highlights are drawn directly on final document pages and are preserved
            if highlighting_info:
                logger.info(f"🎨 SECOND PASS: Applying highlights to {len(highlighting_info)} pages in sorted PDF...")
                for idx, highlight_data in enumerate(highlighting_info):
                    sorted_page_idx = highlight_data['sorted_page_idx']
                    products = highlight_data['products']
                    total_qty = highlight_data['total_qty']
                    has_duplicates = highlight_data['has_duplicates']
                    
                    logger.info(f"   📄 Processing page {idx + 1}/{len(highlighting_info)}: sorted_pdf index {sorted_page_idx}")
                    logger.info(f"      Products: {len(products) if products else 0}, total_qty={total_qty}, has_duplicates={has_duplicates}")
                    
                    try:
                        if sorted_page_idx < len(sorted_pdf):
                            sorted_page = sorted_pdf[sorted_page_idx]
                            logger.info(f"      🎨 Calling highlight_large_qty_flipkart() for sorted_pdf page {sorted_page_idx + 1}...")
                            
                            highlight_count = highlight_large_qty_flipkart(
                                sorted_page, 
                                products=products, 
                                total_qty=total_qty
                            )
                            
                            # Determine reason for highlighting
                            if total_qty > 1:
                                qty_reason = f"total_qty={total_qty}"
                            elif has_duplicates:
                                qty_reason = "duplicate products"
                            elif len(products) > 1:
                                qty_reason = f"multiple products ({len(products)} products)"
                            else:
                                qty_reason = "unknown"
                            
                            if highlight_count > 0:
                                logger.info(f"      ✅ SUCCESS: Highlighted sorted_pdf page {sorted_page_idx + 1} with {qty_reason} ({highlight_count} blocks highlighted)")
                            else:
                                logger.warning(f"      ⚠️  WARNING: Highlight function returned 0 blocks for sorted_pdf page {sorted_page_idx + 1} (qty_reason: {qty_reason})")
                        else:
                            logger.error(f"      ❌ ERROR: Page index {sorted_page_idx} out of range for sorted_pdf (length: {len(sorted_pdf)})")
                    except Exception as e:
                        logger.error(f"      ❌ ERROR: Could not highlight sorted_pdf page {sorted_page_idx + 1}: {e}", exc_info=True)
                
                logger.info(f"🎨 SECOND PASS COMPLETE: Finished processing {len(highlighting_info)} pages")
            else:
                logger.info("⏭️  No pages require highlighting (all pages have qty <= 1 and only 1 product each)")
            
            # Save to buffer with optimization to reduce file size
            logger.info("Saving sorted PDF to buffer with optimization...")
            output_buffer = BytesIO()
            # Use deflate=True for compression and garbage=4 to remove unused objects
            sorted_pdf.save(output_buffer, deflate=True, garbage=4)
            output_buffer.seek(0)
            buffer_size = len(output_buffer.getvalue())
            sorted_pdf.close()
            logger.info(f"✅ Sorted PDF saved to buffer: {buffer_size} bytes ({buffer_size/1024/1024:.2f} MB)")
            
            # Close temporary documents
            logger.info(f"Closing {len(temp_docs)} temporary documents...")
            for temp_doc in temp_docs:
                try:
                    if temp_doc and not temp_doc.is_closed:
                        temp_doc.close()
                except Exception as e:
                    logger.debug(f"Error closing temp doc: {e}")
            
            logger.info(f"✅ Successfully sorted {len(page_data)} shipping labels by product")
            logger.info(f"✅ Returning BytesIO buffer with {buffer_size} bytes")
            return output_buffer
            
    except Exception as e:
        logger.error(f"❌ Error sorting PDF by SKU: {e}", exc_info=True)
        return None

def flipkart_packing_plan_tool():
    """
    Main UI function for Flipkart Packing Plan Generator
    Phase 2: Full workflow with packing plan generation
    """
    # Inject custom CSS
    try:
        from app.utils.ui_components import inject_custom_css
        inject_custom_css()
    except Exception:
        pass
    
    st.markdown("### Flipkart Packing Plan Generator")
    
    admin_logged_in, _, _, _ = sidebar_controls()
    
    # Load master data
    master_df = load_master_data()
    if master_df is None:
        st.error("❌ Master data not available. Please configure data source in sidebar.")
        st.stop()
        return
    
    # Clean column names
    master_df.columns = master_df.columns.str.strip()
    logger.info(f"Loaded master data with {len(master_df)} products")
    
    # Helper function to generate unique key suffix from data
    def get_unique_key_suffix(data):
        """Generate unique key suffix from data hash to prevent duplicate widget keys"""
        try:
            if isinstance(data, pd.DataFrame):
                hash_data = pd.util.hash_pandas_object(data).values
                return hashlib.md5(hash_data.tobytes()).hexdigest()[:8]
            elif isinstance(data, BytesIO):
                pos = data.tell()
                data.seek(0)
                content = data.read()
                data.seek(pos)
                return hashlib.md5(content).hexdigest()[:8]
            elif isinstance(data, bytes):
                return hashlib.md5(data).hexdigest()[:8]
            else:
                return hashlib.md5(str(data).encode()).hexdigest()[:8]
        except Exception as e:
            logger.warning(f"Error generating key suffix: {e}")
            return datetime.now().strftime("%H%M%S")
    
    # Organize content into tabs
    tab1, tab2, tab3, tab4 = st.tabs(["📤 Upload", "📊 Results", "📥 Downloads", "🏷️ Labels"])
    
    # Initialize variables
    df_orders = pd.DataFrame()
    df_physical = pd.DataFrame()
    missing_products = []
    total_orders = 0
    total_physical_items = 0
    total_qty_ordered = 0
    total_qty_physical = 0
    sorted_highlighted_pdf = None  # Initialize sorted PDF variable
    
    # Initialize session state for sorted PDF if not exists
    if 'flipkart_sorted_pdf' not in st.session_state:
        st.session_state.flipkart_sorted_pdf = None
    
    with tab1:
        # File Upload Section
        pdf_files = st.file_uploader(
            "Upload Flipkart Invoice PDFs",
            type=["pdf"],
            accept_multiple_files=True,
            help="Upload one or more Flipkart invoice PDF files"
        )
        
        # Master Data Preview
        with st.expander("📋 Master Data", expanded=False):
            st.dataframe(master_df.head(10), use_container_width=True)
            st.caption(f"Total: {len(master_df)} products")
    
    # File info
    if pdf_files:
        total_size = sum(f.size for f in pdf_files)
        total_size_mb = total_size / (1024 * 1024)
        file_count = len(pdf_files)
        st.caption(f"{file_count} files • {total_size_mb:.2f} MB total")
    
    if pdf_files:
        logger.info(f"Processing {len(pdf_files)} Flipkart PDF files")
        
        # Progress indicators
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # Collect all products from all PDFs
        all_products = []
        product_qty_data = defaultdict(int)
        all_pdf_bytes = []  # Store PDF bytes for sorting
        
        total_files = len(pdf_files)
        for file_idx, uploaded_file in enumerate(pdf_files):
            progress = (file_idx + 1) / total_files
            progress_bar.progress(progress)
            status_text.text(f"📄 Processing file {file_idx + 1}/{total_files}: {uploaded_file.name}")
            
            try:
                pdf_bytes = uploaded_file.read()
                all_pdf_bytes.append(pdf_bytes)  # Store for sorting
                result = extract_product_info_flipkart(pdf_bytes)
                
                # Aggregate products by product_name + weight (same as ASIN for Amazon)
                for product in result['products']:
                    product_name = product.get('product_name', '') or ''
                    weight = product.get('weight', '') or ''
                    qty = product.get('qty', 1)
                    sku_id = product.get('sku_id', '') or ''
                    
                    # Normalize: ensure empty strings, not None
                    if product_name is None:
                        product_name = ''
                    if weight is None:
                        weight = ''
                    if sku_id is None:
                        sku_id = ''
                    
                    # If product_name or weight is empty, use SKU ID as part of key to preserve connection
                    if not product_name or not weight:
                        # Use SKU ID as primary identifier when parsing failed
                        product_key = f"SKU:{sku_id}" if sku_id else f"{product_name}|{weight}"
                    else:
                        # Normal case: use product_name + weight
                        product_key = f"{product_name}|{weight}"
                    
                    product_qty_data[product_key] += qty
                    
                    # Store product info for orders dataframe
                    all_products.append({
                        'Product_Name': product_name,
                        'Weight': weight,
                        'SKU_ID': sku_id,
                        'Description': product.get('description', ''),
                        'Qty': qty,
                        'Product_Key': product_key  # Store the key for later matching
                    })
                    
                    logger.debug(f"Aggregated: Key={product_key}, SKU={sku_id}, Name={product_name}, Weight={weight}, Qty={qty}")
                
            except Exception as e:
                error_type = type(e).__name__
                logger.error(f"Error processing {uploaded_file.name}: {error_type} - {str(e)}")
                st.warning(f"⚠️ **File Processing Error**: Could not process '{uploaded_file.name}'. Error: {str(e)}")
        
        # Generate sorted PDF if we have PDF files
        sorted_highlighted_pdf = None
        if all_pdf_bytes:
            try:
                progress_bar.progress(0.9)
                status_text.text("🔄 Combining PDFs and generating sorted shipping labels...")
                logger.info(f"=== Starting sorted PDF generation for {len(all_pdf_bytes)} PDF files ===")
                
                # Combine all PDFs into one
                combined_pdf = fitz.open()
                for pdf_bytes in all_pdf_bytes:
                    with safe_pdf_context(pdf_bytes) as doc:
                        combined_pdf.insert_pdf(doc)
                
                logger.info(f"Combined {len(all_pdf_bytes)} PDFs into single document with {len(combined_pdf)} pages")
                
                # Convert combined PDF to bytes with optimization
                combined_buffer = BytesIO()
                combined_pdf.save(combined_buffer, deflate=True, garbage=4)
                combined_buffer.seek(0)
                combined_bytes = combined_buffer.read()
                combined_pdf.close()
                combined_buffer.close()
                
                logger.info(f"Combined PDF size: {len(combined_bytes)} bytes")
                
                # Generate sorted PDF
                progress_bar.progress(0.95)
                status_text.text("🎨 Sorting and highlighting shipping labels...")
                logger.info(f"Calling sort_pdf_by_sku_flipkart() with {len(combined_bytes)} bytes")
                sorted_pdf_buffer = sort_pdf_by_sku_flipkart(combined_bytes, master_df)
                
                if sorted_pdf_buffer:
                    logger.info(f"sort_pdf_by_sku_flipkart() returned BytesIO buffer: {type(sorted_pdf_buffer)}")
                    # Keep BytesIO buffer - match Amazon pattern exactly
                    sorted_pdf_buffer.seek(0)
                    sorted_highlighted_pdf = sorted_pdf_buffer
                    
                    # Also store as bytes in session state for persistence
                    sorted_pdf_buffer.seek(0)
                    sorted_pdf_bytes = sorted_pdf_buffer.read()
                    st.session_state.flipkart_sorted_pdf = sorted_pdf_bytes
                    sorted_pdf_buffer.seek(0)  # Reset for local use
                    
                    logger.info(f"✅ Successfully generated sorted PDF: {len(sorted_pdf_bytes)} bytes")
                    logger.info(f"✅ Stored in session state: {len(st.session_state.flipkart_sorted_pdf)} bytes")
                    logger.info(f"✅ Local variable sorted_highlighted_pdf set: {sorted_highlighted_pdf is not None}")
                else:
                    sorted_highlighted_pdf = None
                    if 'flipkart_sorted_pdf' in st.session_state:
                        del st.session_state.flipkart_sorted_pdf
                    logger.error("❌ Failed to generate sorted PDF - sort_pdf_by_sku_flipkart returned None")
                    st.warning("⚠️ **Warning**: Could not generate sorted shipping labels PDF. Other features will still work.")
                
            except (IOError, OSError, MemoryError) as e:
                error_type = type(e).__name__
                logger.error(f"❌ Error combining and sorting PDFs: {error_type} - {str(e)}", exc_info=True)
                sorted_highlighted_pdf = None
                if 'flipkart_sorted_pdf' in st.session_state:
                    del st.session_state.flipkart_sorted_pdf
                if isinstance(e, MemoryError):
                    st.error(f"❌ **Memory Error**: PDFs are too large to process together ({total_size_mb:.2f} MB). Try processing fewer files at once.")
                else:
                    st.error(f"❌ **PDF Processing Error** ({error_type}): {str(e)}. The sorted PDF will not be available, but other features will still work.")
            except Exception as e:
                logger.error(f"❌ Unexpected error combining and sorting PDFs: {str(e)}", exc_info=True)
                sorted_highlighted_pdf = None
                if 'flipkart_sorted_pdf' in st.session_state:
                    del st.session_state.flipkart_sorted_pdf
                st.error(f"❌ **Unexpected Error**: {str(e)}. The sorted PDF will not be available, but other features will still work.")
        
        progress_bar.progress(1.0)
        status_text.text("✅ PDF processing complete!")
        progress_bar.empty()
        status_text.empty()
        
        if not product_qty_data:
            st.error("❌ **No Products Found**: No products were extracted from the uploaded PDFs.")
            st.info("**Possible causes:**")
            st.write("• PDFs may not be Flipkart invoice PDFs")
            st.write("• PDFs may be corrupted or unreadable")
            st.write("• SKU ID format may not be recognized")
            return
        
        # Create orders dataframe
        orders_list = []
        for product_key, qty in product_qty_data.items():
            # Check if this is a SKU-based key (when parsing failed)
            if product_key.startswith('SKU:'):
                sku_id = product_key.replace('SKU:', '', 1)
                # Find product by SKU ID
                matching_product = next((p for p in all_products if p['SKU_ID'] == sku_id), None)
                if matching_product:
                    product_name = matching_product.get('Product_Name', '') or ''
                    weight = matching_product.get('Weight', '') or ''
                else:
                    # If not found, try to parse from SKU ID
                    product_name, weight = parse_sku_id(sku_id)
                    # Convert None to empty string
                    if product_name is None:
                        product_name = ''
                    if weight is None:
                        weight = ''
                
                logger.debug(f"SKU-based key: SKU={sku_id}, Parsed Name={product_name}, Weight={weight}")
            else:
                # Normal case: split product_name and weight
                parts = product_key.split('|', 1)
                product_name = parts[0] if len(parts) > 0 else ''
                weight = parts[1] if len(parts) > 1 else ''
                
                # Clean up "None" strings from split
                if product_name == 'None' or not product_name:
                    product_name = ''
                if weight == 'None' or not weight:
                    weight = ''
                
                # Find matching product info - try exact match first
                matching_product = next((p for p in all_products if p.get('Product_Key') == product_key), None)
                
                # If no match by key, try by product name and weight
                if not matching_product:
                    matching_product = next((p for p in all_products if p['Product_Name'] == product_name and p['Weight'] == weight), None)
                
                # If no exact match, try to find by product name only or weight only
                if not matching_product and product_name:
                    matching_product = next((p for p in all_products if p['Product_Name'] == product_name), None)
                if not matching_product and weight:
                    matching_product = next((p for p in all_products if p['Weight'] == weight), None)
            
            # Get SKU ID from matching product or use the one from key
            if matching_product:
                sku_id = matching_product.get('SKU_ID', '')
                # Update product_name and weight from matching product if they're empty
                if not product_name and matching_product.get('Product_Name'):
                    product_name = matching_product.get('Product_Name', '')
                if not weight and matching_product.get('Weight'):
                    weight = matching_product.get('Weight', '')
            elif product_key.startswith('SKU:'):
                sku_id = product_key.replace('SKU:', '', 1)
            else:
                sku_id = ''
            
            orders_list.append({
                'Product_Name': product_name,
                'Weight': weight,
                'SKU_ID': sku_id,
                'Qty': qty
            })
        
        df_orders = pd.DataFrame(orders_list)
        
        # Enrich df_orders with master data (Packet Size, etc.)
        # Match products with master_df to get additional information
        enriched_orders = []
        for _, row in df_orders.iterrows():
            product_name = row.get('Product_Name', '')
            weight = row.get('Weight', '')
            sku_id = row.get('SKU_ID', '')
            qty = row.get('Qty', 0)
            
            # Always try to extract from SKU ID if product_name or weight is missing
            # This ensures we get the data even if initial parsing failed
            if (not product_name or not weight) and sku_id:
                logger.debug(f"Re-parsing SKU ID: {sku_id}, Current Name={product_name}, Weight={weight}")
                
                # Re-parse SKU ID to get product name and weight
                parsed_name, parsed_weight = parse_sku_id(sku_id)
                
                # Convert None to empty string
                if parsed_name is None:
                    parsed_name = ''
                if parsed_weight is None:
                    parsed_weight = ''
                
                # Update if we got better values
                if parsed_name and not product_name:
                    product_name = parsed_name
                    logger.debug(f"Extracted product name from SKU: {product_name}")
                if parsed_weight and not weight:
                    weight = parsed_weight
                    logger.debug(f"Extracted weight from SKU: {weight}")
                
                # If still empty after re-parsing, extract basic info from SKU ID string directly
                if not product_name:
                    # Remove leading number and try to extract product name
                    sku_clean = re.sub(r'^\d+\s+', '', sku_id).strip()
                    # Remove weight pattern if present (kg or g)
                    sku_clean = re.sub(r'\s+\d+(?:\.\d+)?(?:kg|g)\s*$', '', sku_clean, flags=re.IGNORECASE).strip()
                    # Remove trailing standalone numbers (like "3" in "1 Bihari Coconut Thekua 3")
                    # Only remove if it's a small number (likely quantity, not weight)
                    trailing_num_match = re.search(r'\s+(\d+)$', sku_clean)
                    if trailing_num_match:
                        trailing_num = int(trailing_num_match.group(1))
                        if trailing_num <= 10:  # Likely a quantity, not weight
                            sku_clean = sku_clean[:trailing_num_match.start()].strip()
                    if sku_clean:
                        product_name = sku_clean
                        logger.debug(f"Extracted product name from SKU string: {product_name}")
                
                if not weight:
                    # Try to extract weight from SKU ID (look for kg or g patterns)
                    weight_match = re.search(r'(\d+(?:\.\d+)?(?:kg|g))', sku_id, re.IGNORECASE)
                    if weight_match:
                        weight = normalize_weight(weight_match.group(1))
                        logger.debug(f"Extracted weight from SKU string: {weight}")
            
            # Final cleanup: ensure no None values or 'None' strings
            if product_name is None or product_name == 'None' or (isinstance(product_name, float) and pd.isna(product_name)):
                product_name = ''
            if weight is None or weight == 'None' or (isinstance(weight, float) and pd.isna(weight)):
                weight = ''
            
            logger.debug(f"Final values before enrichment: Name={product_name}, Weight={weight}, SKU={sku_id}, Qty={qty}")
            
            # Try to find matching product in master data
            packet_size = 'N/A'
            
            # Strategy 1: Try FK SKU matching
            if sku_id:
                matches = get_product_from_fk_sku(sku_id, master_df)
                if not matches.empty:
                    # Use flexible column matching for Packet Size
                    packet_size_col = find_column_flexible(matches, ['Packet Size', 'PacketSize'])
                    if packet_size_col:
                        packet_size = str(matches.iloc[0].get(packet_size_col, 'N/A'))
                    else:
                        packet_size = 'N/A'
                    if pd.isna(packet_size) or packet_size == 'nan':
                        packet_size = 'N/A'
            
            # Strategy 2: Try name + weight matching if packet size not found
            if packet_size == 'N/A' and product_name and weight:
                matches = get_product_from_name_weight(product_name, weight, master_df)
                if not matches.empty:
                    # Use flexible column matching for Packet Size
                    packet_size_col = find_column_flexible(matches, ['Packet Size', 'PacketSize'])
                    if packet_size_col:
                        packet_size = str(matches.iloc[0].get(packet_size_col, 'N/A'))
                    else:
                        packet_size = 'N/A'
                    if pd.isna(packet_size) or packet_size == 'nan':
                        packet_size = 'N/A'
            
            # Ensure we have values to display - use extracted values or fallback
            display_item = product_name if product_name else 'N/A'
            display_weight = weight if weight else 'N/A'
            display_sku = sku_id if sku_id else 'N/A'
            
            # Final validation: if we still don't have item/weight but have SKU, try one more time
            if (display_item == 'N/A' or display_weight == 'N/A') and display_sku != 'N/A':
                logger.warning(f"Still missing data after enrichment: Item={display_item}, Weight={display_weight}, SKU={display_sku}")
            
            enriched_orders.append({
                'Item': display_item,
                'Weight': display_weight,
                'Qty': qty,
                'Packet Size': packet_size,
                'SKU ID': display_sku
            })
        
        # Create enriched DataFrame with correct column names and order
        df_orders = pd.DataFrame(enriched_orders)
        # Ensure correct column order: Item, Weight, Qty, Packet Size, SKU ID
        column_order = ['Item', 'Weight', 'Qty', 'Packet Size', 'SKU ID']
        df_orders = df_orders[[col for col in column_order if col in df_orders.columns]]
        
        # Log enrichment results for debugging
        logger.info(f"Enriched df_orders created with {len(df_orders)} rows")
        if not df_orders.empty:
            empty_items = df_orders[df_orders['Item'].isin(['', 'N/A', None])].shape[0]
            empty_weights = df_orders[df_orders['Weight'].isin(['', 'N/A', None])].shape[0]
            logger.info(f"Enrichment stats: {empty_items} empty Items, {empty_weights} empty Weights out of {len(df_orders)} total")
            # Log first few rows for debugging
            for idx, row in df_orders.head(3).iterrows():
                logger.info(f"Row {idx}: Item='{row.get('Item', '')}', Weight='{row.get('Weight', '')}', SKU='{row.get('SKU ID', '')}'")
        
        # Expand to physical plan
        df_physical, missing_products = expand_to_physical_flipkart(df_orders, master_df)
        
        # Summary statistics
        total_orders = len(df_orders)
        total_physical_items = len(df_physical) if not df_physical.empty else 0
        total_qty_ordered = df_orders['Qty'].sum() if 'Qty' in df_orders.columns else 0
        total_qty_physical = df_physical['Qty'].sum() if not df_physical.empty and 'Qty' in df_physical.columns else 0
        
        st.caption("✅ Packing plan generated")
        
        # Metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Orders", total_orders)
        with col2:
            st.metric("Items", total_physical_items)
        with col3:
            st.metric("Qty Ordered", int(total_qty_ordered))
        with col4:
            st.metric("Qty Physical", int(total_qty_physical))
        
        # Missing products warning
        if missing_products:
            st.warning(f"{len(missing_products)} product(s) have issues")
            with st.expander("View Missing Products", expanded=False):
                missing_df = pd.DataFrame(missing_products)
                st.dataframe(missing_df, use_container_width=True)
    
    with tab2:
        # Results & Preview Tab
        if pdf_files and not df_orders.empty:
            # Summary metrics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Orders", total_orders)
            with col2:
                st.metric("Items", total_physical_items)
            with col3:
                st.metric("Qty Ordered", int(total_qty_ordered))
            with col4:
                st.metric("Qty Physical", int(total_qty_physical))
            
            st.markdown("---")
            
            # Original Ordered Items
            st.markdown("**Ordered Items**")
            st.dataframe(df_orders, use_container_width=True, height=250)
            
            st.markdown("---")
            
            # Physical Packing Plan
            st.markdown("**Physical Packing Plan**")
            if not df_physical.empty:
                # Color code the dataframe based on status
                def highlight_status(row):
                    status = row.get('Status', '')
                    if 'MISSING FNSKU' in status:
                        return ['background-color: #ffcccc'] * len(row)
                    elif 'MISSING FROM MASTER' in status:
                        return ['background-color: #ff9999'] * len(row)
                    else:
                        return ['background-color: #ccffcc'] * len(row)
                
                try:
                    st.dataframe(df_physical.style.apply(highlight_status, axis=1), use_container_width=True, height=300)
                except:
                    st.dataframe(df_physical, use_container_width=True, height=300)
            else:
                if missing_products:
                    st.error("⚠️ **No physical packing plan generated!**")
                    st.info("**Possible causes:**")
                    st.write("• All products may be missing from the master file")
                    st.write("• Check the missing products listed above")
        else:
            st.info("Please upload Flipkart invoice PDFs to see results.")
    
    with tab3:
        # Downloads Tab
        if pdf_files and not df_physical.empty:
            pdf_key_suffix = get_unique_key_suffix(df_physical)
            
            col1, col2 = st.columns(2)
            
            with col1:
                try:
                    summary_pdf = generate_summary_pdf_flipkart(df_orders, df_physical, missing_products)
                    if summary_pdf:
                        st.download_button(
                            "Packing Plan PDF", 
                            data=summary_pdf, 
                            file_name="Flipkart_Packing_Plan.pdf", 
                            mime="application/pdf", 
                            key=f"download_packing_plan_pdf_{pdf_key_suffix}",
                            use_container_width=True
                        )
                except Exception as e:
                    st.error(f"Error: {str(e)}")
            
            with col2:
                try:
                    excel_buffer = BytesIO()
                    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                        df_physical.to_excel(writer, index=False, sheet_name="Physical Packing Plan")
                        df_orders.to_excel(writer, index=False, sheet_name="Original Orders")
                        if missing_products:
                            pd.DataFrame(missing_products).to_excel(writer, index=False, sheet_name="Missing Products")
                    excel_buffer.seek(0)
                    st.download_button(
                        "Excel Workbook", 
                        data=excel_buffer, 
                        file_name="Flipkart_Packing_Plan.xlsx", 
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
                        key=f"download_packing_plan_excel_{pdf_key_suffix}",
                        use_container_width=True
                    )
                except Exception as e:
                    st.error(f"Error: {str(e)}")
            
            st.markdown("---")
            
            # Sorted Shipping Labels PDF
            # Simplified check - match Amazon pattern exactly (like Amazon version)
            logger.info(f"=== Downloads tab: Checking for sorted PDF ===")
            logger.info(f"Local variable sorted_highlighted_pdf exists: {'sorted_highlighted_pdf' in locals()}")
            logger.info(f"Local variable sorted_highlighted_pdf value: {sorted_highlighted_pdf is not None if 'sorted_highlighted_pdf' in locals() else 'N/A'}")
            logger.info(f"Session state flipkart_sorted_pdf: {'flipkart_sorted_pdf' in st.session_state}")
            
            # Priority 1: Check local variable first (same-run access) - match Amazon pattern exactly
            # Note: sorted_highlighted_pdf is in function scope, so it's accessible here
            if sorted_highlighted_pdf:
                logger.info(f"✅ Using local sorted_highlighted_pdf: type={type(sorted_highlighted_pdf)}")
                try:
                    # Ensure BytesIO is at start
                    if isinstance(sorted_highlighted_pdf, BytesIO):
                        sorted_highlighted_pdf.seek(0)
                    
                    sorted_pdf_key_suffix = get_unique_key_suffix(sorted_highlighted_pdf)
                    st.download_button(
                        "Sorted Shipping Labels PDF", 
                        data=sorted_highlighted_pdf, 
                        file_name=f"Flipkart_Sorted_Shipping_Labels_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf", 
                        mime="application/pdf",
                        key=f"download_sorted_pdf_{sorted_pdf_key_suffix}",
                        use_container_width=True,
                        help="Download sorted shipping labels (cropped, sorted by product, with quantities > 1 highlighted)"
                    )
                    logger.info("✅ Sorted PDF download button displayed successfully")
                except Exception as e:
                    logger.error(f"❌ Error displaying sorted PDF download: {e}", exc_info=True)
                    st.error(f"Error with sorted PDF: {str(e)}")
            # Priority 2: Check session state (cross-run persistence)
            elif 'flipkart_sorted_pdf' in st.session_state and st.session_state.flipkart_sorted_pdf:
                session_data = st.session_state.flipkart_sorted_pdf
                logger.info(f"✅ Using session state sorted PDF: type={type(session_data)}, size={len(session_data) if isinstance(session_data, bytes) else 'N/A'}")
                try:
                    sorted_pdf_key_suffix = get_unique_key_suffix(session_data)
                    st.download_button(
                        "Sorted Shipping Labels PDF", 
                        data=session_data, 
                        file_name=f"Flipkart_Sorted_Shipping_Labels_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf", 
                        mime="application/pdf",
                        key=f"download_sorted_pdf_{sorted_pdf_key_suffix}",
                        use_container_width=True,
                        help="Download sorted shipping labels (cropped, sorted by product, with quantities > 1 highlighted)"
                    )
                    logger.info("✅ Sorted PDF download button displayed from session state")
                except Exception as e:
                    logger.error(f"❌ Error displaying sorted PDF from session state: {e}", exc_info=True)
                    st.error(f"Error with sorted PDF: {str(e)}")
            else:
                # Show helpful message
                if pdf_files:
                    st.info("🔄 Sorted shipping labels PDF is being generated. Please wait for processing to complete.")
                    logger.warning(f"⚠️ Sorted PDF not available - sorted_highlighted_pdf={'sorted_highlighted_pdf' in locals() and sorted_highlighted_pdf is not None}, session_state={'flipkart_sorted_pdf' in st.session_state}")
                else:
                    st.info("Please upload Flipkart invoice PDFs to generate sorted shipping labels.")
        else:
            st.info("Please upload Flipkart invoice PDFs to generate downloads.")
    
    with tab4:
        # Labels Tab
        if pdf_files and not df_physical.empty:
            if "Packet used" not in df_physical.columns:
                st.warning("'Packet used' column not found")
            else:
                # Load nutrition data for House labels
                try:
                    nutrition_df = load_nutrition_data_silent()
                except Exception as e:
                    logger.error(f"Error loading nutrition data: {str(e)}")
                    nutrition_df = None
                
                # Use session state caching to prevent regeneration
                try:
                    hash_data = pd.util.hash_pandas_object(df_physical[['ASIN', 'Qty', 'FNSKU', 'Packet used']] if all(col in df_physical.columns for col in ['ASIN', 'Qty', 'FNSKU', 'Packet used']) else df_physical).values
                    data_hash = hashlib.md5(hash_data.tobytes()).hexdigest()
                except Exception as e:
                    logger.warning(f"Could not create selective hash: {e}")
                    data_hash = hashlib.md5(pd.util.hash_pandas_object(df_physical).values.tobytes()).hexdigest()
                
                # Check if labels already generated
                if 'flipkart_label_cache_hash' not in st.session_state or st.session_state.flipkart_label_cache_hash != data_hash:
                    with st.spinner("🔄 Generating labels..."):
                        try:
                            sticker_buffer, house_buffer, sticker_count, house_count, skipped_products = generate_labels_by_packet_used_flipkart(
                                df_physical, master_df, nutrition_df
                            )
                            
                            # Store in session state
                            st.session_state.flipkart_label_cache_hash = data_hash
                            st.session_state.flipkart_sticker_buffer = sticker_buffer
                            st.session_state.flipkart_house_buffer = house_buffer
                            st.session_state.flipkart_sticker_count = sticker_count
                            st.session_state.flipkart_house_count = house_count
                            st.session_state.flipkart_skipped_products = skipped_products
                        except Exception as e:
                            logger.error(f"Error generating labels: {str(e)}")
                            st.error(f"❌ **Label Generation Error**: {str(e)}")
                            st.session_state.flipkart_label_cache_hash = data_hash
                            st.session_state.flipkart_sticker_buffer = BytesIO()
                            st.session_state.flipkart_house_buffer = BytesIO()
                            st.session_state.flipkart_sticker_count = 0
                            st.session_state.flipkart_house_count = 0
                            st.session_state.flipkart_skipped_products = []
                else:
                    sticker_buffer = st.session_state.flipkart_sticker_buffer
                    house_buffer = st.session_state.flipkart_house_buffer
                    sticker_count = st.session_state.flipkart_sticker_count
                    house_count = st.session_state.flipkart_house_count
                    skipped_products = st.session_state.flipkart_skipped_products
                
                # Display results and download buttons
                sticker_key_suffix = data_hash[:8]
                house_key_suffix = data_hash[:8]
                
                col1, col2 = st.columns(2)
                
                with col1:
                    if sticker_buffer and sticker_count > 0:
                        st.metric("Sticker Labels", sticker_count)
                        st.download_button(
                            f"Download ({sticker_count})",
                            data=sticker_buffer,
                            file_name=f"Flipkart_Sticker_Labels_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                            mime="application/pdf",
                            key=f"download_sticker_labels_{sticker_key_suffix}",
                            use_container_width=True
                        )
                    else:
                        st.caption("No Sticker labels")
                
                with col2:
                    if house_buffer and house_count > 0:
                        st.metric("House Labels", house_count)
                        st.download_button(
                            f"Download ({house_count})",
                            data=house_buffer,
                            file_name=f"Flipkart_House_Labels_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                            mime="application/pdf",
                            key=f"download_house_labels_{house_key_suffix}",
                            use_container_width=True
                        )
                    else:
                        st.caption("No House labels")
                
                # Show skipped products if any
                if skipped_products:
                    with st.expander("⚠️ Products Skipped from Label Generation", expanded=False):
                        skipped_df = pd.DataFrame(skipped_products)
                        st.dataframe(skipped_df, use_container_width=True)
        else:
            if pdf_files:
                st.info("ℹ️ No physical packing plan available for label generation.")
            else:
                st.info("Please upload Flipkart invoice PDFs to generate labels.")

def expand_to_physical_flipkart(df, master_df):
    """
    Convert ordered items to physical packing plan for Flipkart orders
    
    Matches products by FK SKU first, then falls back to name + weight
    
    Args:
        df: Orders DataFrame with columns: Item (or Product_Name), Weight, Qty, SKU ID (or SKU_ID)
        master_df: Master data DataFrame with FK SKU and M columns
    
    Returns:
        tuple: (df_physical, missing_products)
    """
    physical_rows = []
    missing_products = []
    
    for _, row in df.iterrows():
        try:
            # Support both old and new column names
            product_name = row.get("Item", row.get("Product_Name", ""))
            weight = row.get("Weight", "")
            qty = int(row.get("Qty", 1))
            sku_id = row.get("SKU ID", row.get("SKU_ID", ""))
            
            # Strategy 1: Try FK SKU matching first (most reliable)
            matches = get_product_from_fk_sku(sku_id, master_df)
            
            # Strategy 2: Fallback to name + weight matching if FK SKU fails
            if matches.empty and product_name and weight:
                matches = get_product_from_name_weight(product_name, weight, master_df)
            
            # Strategy 3: Try name-only matching if weight is missing
            if matches.empty and product_name and not weight:
                matches = get_product_from_name_weight(product_name, None, master_df)
            
            if matches.empty:
                logger.warning(f"Product not found in master file: {product_name} {weight}")
                missing_products.append({
                    "SKU_ID": sku_id,
                    "Product": product_name,
                    "Weight": weight,
                    "Issue": "Not found in master file",
                    "Qty": qty
                })
                physical_rows.append({
                    "item": f"UNKNOWN PRODUCT ({product_name} {weight})",
                    "weight": weight or "N/A",
                    "Qty": qty,
                    "Packet Size": "N/A",
                    "Packet used": "N/A",
                    "ASIN": "N/A",
                    "MRP": "N/A",
                    "FNSKU": "MISSING",
                    "FSSAI": "N/A",
                    "Packed Today": "",
                    "Available": "",
                    "Status": "⚠️ MISSING FROM MASTER"
                })
                continue
            
            # Use first match (best match from get_product_from_name_weight)
            base = matches.iloc[0]
            # Use flexible column matching
            split_into_col = find_column_flexible(matches, ['Split Into', 'SplitInto'])
            name_col = find_column_flexible(matches, ['Name'])
            fnsku_col = find_column_flexible(matches, ['FNSKU'])
            asin_col = find_column_flexible(matches, ['ASIN'])
            
            split = str(base.get(split_into_col, "")) if split_into_col else ""
            name = base.get(name_col, "Unknown Product") if name_col else "Unknown Product"
            fnsku = str(base.get(fnsku_col, "")) if fnsku_col else ""
            asin = str(base.get(asin_col, "")) if asin_col else ""
            
            # Check if FNSKU is missing
            if is_empty_value(fnsku):
                missing_products.append({
                    "SKU_ID": sku_id,
                    "Product": product_name,
                    "Weight": weight,
                    "Issue": "Missing FNSKU",
                    "Qty": qty
                })
            
            # Handle products with split information
            if split and not is_empty_value(split):
                sizes = [s.strip() for s in split.split(",")]
                split_found = False
                
                for size in sizes:
                    try:
                        # Use weight matching function that handles kg/g conversions
                        # Match by name and weight using flexible column matching
                        name_col_master = find_column_flexible(master_df, ['Name'])
                        net_weight_col_master = find_column_flexible(master_df, ['Net Weight', 'NetWeight'])
                        
                        if name_col_master and net_weight_col_master:
                            # Use weights_match for flexible weight comparison
                            # This handles: "0.35" matches "350g", "0.7" matches "700g", etc.
                            sub_matches = master_df[
                                (master_df[name_col_master].str.contains(name, case=False, na=False)) &
                                (master_df[net_weight_col_master].apply(lambda w: weights_match(w, size)))
                            ]
                            
                            if not sub_matches.empty:
                                sub = sub_matches.iloc[0]
                                # Use flexible column matching for all column accesses
                                sub_fnsku_col = find_column_flexible(sub_matches, ['FNSKU'])
                                packet_size_col = find_column_flexible(sub_matches, ['Packet Size', 'PacketSize'])
                                packet_used_col = find_column_flexible(sub_matches, ['Packet used', 'Packetused'])
                                asin_col_sub = find_column_flexible(sub_matches, ['ASIN'])
                                mrp_col = find_column_flexible(sub_matches, ['M.R.P', 'MRP', 'M.R.P.'])
                                fssai_col = find_column_flexible(sub_matches, ['FSSAI'])
                                
                                sub_fnsku = str(sub.get(sub_fnsku_col, "")) if sub_fnsku_col else ""
                                status = "✅ READY" if not is_empty_value(sub_fnsku) else "⚠️ MISSING FNSKU"
                                
                                physical_rows.append({
                                    "item": name,
                                    "weight": sub.get(net_weight_col_master, "N/A"),
                                    "Qty": qty,
                                    "Packet Size": sub.get(packet_size_col, "N/A") if packet_size_col else "N/A",
                                    "Packet used": sub.get(packet_used_col, "N/A") if packet_used_col else "N/A",
                                    "ASIN": sub.get(asin_col_sub, asin) if asin_col_sub else asin,
                                    "MRP": sub.get(mrp_col, "N/A") if mrp_col else "N/A",
                                    "FNSKU": sub_fnsku if not is_empty_value(sub_fnsku) else "MISSING",
                                    "FSSAI": sub.get(fssai_col, "N/A") if fssai_col else "N/A",
                                    "Packed Today": "",
                                    "Available": "",
                                    "Status": status
                                })
                                split_found = True
                                break  # Found the split variant, no need to continue
                    except (ValueError, KeyError, AttributeError) as e:
                        error_type = type(e).__name__
                        logger.error(f"Error processing split variant for {name}: {error_type} - {str(e)}")
                    except Exception as e:
                        logger.error(f"Unexpected error processing split variant for {name}: {str(e)}")
                
                if not split_found:
                    missing_products.append({
                        "SKU_ID": sku_id,
                        "Product": product_name,
                        "Weight": weight,
                        "Issue": "Split sizes not found in master file",
                        "Split Info": split,
                        "Qty": qty
                    })
            else:
                # No split information - use base product
                status = "✅ READY" if not is_empty_value(fnsku) else "⚠️ MISSING FNSKU"
                
                # Use flexible column matching for all column accesses
                net_weight_col_base = find_column_flexible(matches, ['Net Weight', 'NetWeight'])
                packet_size_col_base = find_column_flexible(matches, ['Packet Size', 'PacketSize'])
                packet_used_col_base = find_column_flexible(matches, ['Packet used', 'Packetused'])
                mrp_col_base = find_column_flexible(matches, ['M.R.P', 'MRP', 'M.R.P.'])
                fssai_col_base = find_column_flexible(matches, ['FSSAI'])
                
                physical_rows.append({
                    "item": name,
                    "weight": base.get(net_weight_col_base, weight or "N/A") if net_weight_col_base else (weight or "N/A"),
                    "Qty": qty,
                    "Packet Size": base.get(packet_size_col_base, "N/A") if packet_size_col_base else "N/A",
                    "Packet used": base.get(packet_used_col_base, "N/A") if packet_used_col_base else "N/A",
                    "ASIN": asin if not is_empty_value(asin) else "N/A",
                    "MRP": base.get(mrp_col_base, "N/A") if mrp_col_base else "N/A",
                    "FNSKU": fnsku if not is_empty_value(fnsku) else "MISSING",
                    "FSSAI": base.get(fssai_col_base, "N/A") if fssai_col_base else "N/A",
                    "Packed Today": "",
                    "Available": "",
                    "Status": status
                })
        except (ValueError, KeyError) as e:
            error_type = type(e).__name__
            logger.error(f"Error processing row {product_name}: {error_type} - {str(e)}")
            continue
        except Exception as e:
            logger.error(f"Unexpected error processing row {product_name}: {str(e)}")
            continue
    
    df_physical = pd.DataFrame(physical_rows)
    
    # Debug information
    logger.info(f"Generated {len(physical_rows)} physical rows")
    logger.info(f"Missing products: {len(missing_products)}")
    
    if not df_physical.empty:
        try:
            # Group by all columns except Qty to sum quantities for identical items
            df_physical = df_physical.groupby(
                ["item", "weight", "Packet Size", "Packet used", "ASIN", "MRP", "FNSKU", "FSSAI", "Packed Today", "Available", "Status"],
                as_index=False
            ).agg({"Qty": "sum"})
        except Exception as e:
            logger.error(f"Error grouping physical data: {str(e)}")
    else:
        logger.warning("No physical rows generated - this may indicate data processing issues")
    
    return df_physical, missing_products

def generate_summary_pdf_flipkart(original_df, physical_df, missing_products=None):
    """Generate PDF summary with proper encoding handling for Flipkart"""
    try:
        pdf = FPDF()
        timestamp = datetime.now().strftime("%d %b %Y, %I:%M %p")

        def clean_text(text):
            """Clean text for PDF generation"""
            if pd.isna(text):
                return ""
            text = str(text)
            replacements = {
                '✅': 'OK',
                '⚠️': 'WARNING',
                '📦': '',
                '🚨': 'ALERT',
                '•': '-'
            }
            for unicode_char, replacement in replacements.items():
                text = text.replace(unicode_char, replacement)
            # Remove any remaining non-ASCII characters
            text = text.encode('ascii', 'ignore').decode('ascii')
            return text

        def add_table(df, title, include_tracking=False, hide_sku=False):
            """Add table to PDF"""
            pdf.set_font("Arial", "B", 12)
            pdf.cell(0, 10, clean_text(title), 0, 1, "C")
            pdf.set_font("Arial", "", 10)
            pdf.cell(0, 8, f"Generated on: {timestamp}", 0, 1, "C")
            pdf.ln(2)

            headers = ["Item", "Weight", "Qty", "Packet Size"]
            col_widths = [50, 25, 20, 35]

            if not hide_sku:
                headers.append("SKU ID")
                col_widths.append(50)

            if include_tracking:
                headers += ["Packed Today", "Available"]
                col_widths += [30, 30]

            margin_x = (210 - sum(col_widths)) / 2
            pdf.set_x(margin_x)
            pdf.set_font("Arial", "B", 10)
            for header, width in zip(headers, col_widths):
                pdf.cell(width, 10, clean_text(header), 1, 0, "C")
            pdf.ln()

            pdf.set_font("Arial", "", 10)
            for _, row in df.iterrows():
                pdf.set_x(margin_x)
                # Support both "Item" (original) and "item" (physical) column names
                item_value = row.get("Item", row.get("item", ""))
                weight_value = row.get("Weight", row.get("weight", ""))
                values = [
                    clean_text(str(item_value))[:20],
                    clean_text(str(weight_value)),
                    str(row.get("Qty", 0)),
                    clean_text(str(row.get("Packet Size", "")))[:15]
                ]
                if not hide_sku:
                    # Support both "SKU ID" and "SKU_ID" column names
                    sku_value = row.get("SKU ID", row.get("SKU_ID", row.get("ASIN", "")))
                    values.append(clean_text(str(sku_value)))
                if include_tracking:
                    values += [
                        clean_text(str(row.get("Packed Today", ""))),
                        clean_text(str(row.get("Available", "")))
                    ]
                    
                for val, width in zip(values, col_widths):
                    pdf.cell(width, 10, str(val)[:width//2], 1)  # Truncate to fit
                pdf.ln()

        pdf.add_page()
        add_table(original_df, "Original Ordered Items (from Flipkart Invoice)", hide_sku=False)
        pdf.ln(5)
        add_table(physical_df, "Actual Physical Packing Plan", include_tracking=True, hide_sku=True)
        
        # Fixed PDF output handling
        output_buffer = BytesIO()
        try:
            pdf_output = pdf.output(dest="S")
            # Handle both string and bytes output
            if isinstance(pdf_output, str):
                output_buffer.write(pdf_output.encode("latin1"))
            else:
                output_buffer.write(pdf_output)
        except Exception as e:
            logger.error(f"PDF encoding error: {str(e)}")
            # Fallback
            pdf_string = pdf.output(dest="S")
            output_buffer.write(pdf_string.encode("latin1", errors="ignore"))
        
        output_buffer.seek(0)
        return output_buffer
    except Exception as e:
        logger.error(f"Error generating PDF: {str(e)}")
        return None

def generate_labels_by_packet_used_flipkart(df_physical, master_df, nutrition_df, progress_callback=None):
    """
    Automatically generate labels based on 'Packet used' column for Flipkart products
    
    Args:
        df_physical: Physical packing plan DataFrame
        master_df: Master data DataFrame
        nutrition_df: Nutrition data DataFrame (for triple labels)
        progress_callback: Optional callback function(progress, status) for progress updates
    
    Returns:
        tuple: (sticker_pdf_buffer, house_pdf_buffer, sticker_count, house_count, skipped_products)
    """
    sticker_pdf = fitz.open()
    house_pdf = fitz.open()
    sticker_count = 0
    house_count = 0
    skipped_products = []
    
    if df_physical.empty:
        return BytesIO(), BytesIO(), 0, 0, []
    
    # Check if "Packet used" column exists
    if "Packet used" not in df_physical.columns:
        logger.warning("'Packet used' column not found in physical packing plan")
        return BytesIO(), BytesIO(), 0, 0, []
    
    # Separate products by "Packet used" value
    df_physical["Packet used"] = df_physical["Packet used"].astype(str).str.strip()
    sticker_products = df_physical[df_physical["Packet used"].str.lower() == "sticker"]
    house_products = df_physical[df_physical["Packet used"].str.lower() == "house"]
    
    # Track products with empty/invalid "Packet used" values
    other_products = df_physical[
        (~df_physical["Packet used"].str.lower().isin(["sticker", "house"])) &
        (df_physical["Packet used"] != "N/A") &
        (df_physical["Packet used"] != "nan")
    ]
    
    for _, row in other_products.iterrows():
        skipped_products.append({
            "Product": row.get("item", "Unknown"),
            "ASIN": row.get("ASIN", "Unknown"),
            "Packet used": row.get("Packet used", "N/A"),
            "Reason": "Invalid or empty 'Packet used' value"
        })
    
    # Generate Sticker labels (96mm × 25mm)
    for _, row in sticker_products.iterrows():
        fnsku = str(row.get('FNSKU', '')).strip()
        qty = int(row.get('Qty', 0))
        product_name = str(row.get("item", "")).strip()
        
        if fnsku and fnsku != "MISSING" and not is_empty_value(fnsku):
            for _ in range(qty):
                try:
                    label_pdf = generate_combined_label_pdf_direct(pd.DataFrame([row]), fnsku)
                    
                    if label_pdf:
                        with safe_pdf_context(label_pdf.read()) as label_doc:
                            sticker_pdf.insert_pdf(label_doc)
                        sticker_count += 1
                except Exception as e:
                    logger.warning(f"Could not generate Sticker label for FNSKU {fnsku} ({product_name}): {e}")
        else:
            skipped_products.append({
                "Product": product_name,
                "ASIN": row.get("ASIN", "Unknown"),
                "Packet used": "Sticker",
                "Reason": "Missing FNSKU"
            })
    
    # Generate House labels (50mm × 100mm triple labels)
    for _, row in house_products.iterrows():
        fnsku = str(row.get('FNSKU', '')).strip()
        qty = int(row.get('Qty', 0))
        product_name = str(row.get("item", "")).strip()
        
        if fnsku and fnsku != "MISSING" and not is_empty_value(fnsku):
            # Find nutrition data
            nutrition_row = None
            if nutrition_df is not None and not nutrition_df.empty:
                if product_name:
                    nutrition_matches = nutrition_df[
                        nutrition_df["Product"].str.contains(product_name, case=False, na=False)
                    ]
                    if not nutrition_matches.empty:
                        nutrition_row = nutrition_matches.iloc[0]
            
            if nutrition_row is not None:
                for copy_num in range(qty):
                    try:
                        triple_label_pdf = generate_triple_label_combined(
                            pd.DataFrame([row]), nutrition_row, product_name, method="direct"
                        )
                        
                        if triple_label_pdf:
                            with safe_pdf_context(triple_label_pdf.read()) as label_doc:
                                house_pdf.insert_pdf(label_doc)
                            house_count += 1
                    except Exception as e:
                        logger.warning(f"Could not generate House label for {product_name} (copy {copy_num+1}): {e}")
            else:
                skipped_products.append({
                    "Product": product_name,
                    "ASIN": row.get("ASIN", "Unknown"),
                    "Packet used": "House",
                    "Reason": "Missing nutrition data"
                })
        else:
            skipped_products.append({
                "Product": product_name,
                "ASIN": row.get("ASIN", "Unknown"),
                "Packet used": "House",
                "Reason": "Missing FNSKU"
            })
    
    # Save to buffers
    sticker_buffer = BytesIO()
    house_buffer = BytesIO()
    
    try:
        if len(sticker_pdf) > 0:
            sticker_pdf.save(sticker_buffer)
            sticker_buffer.seek(0)
    finally:
        sticker_pdf.close()
    
    try:
        if len(house_pdf) > 0:
            house_pdf.save(house_buffer)
            house_buffer.seek(0)
    finally:
        house_pdf.close()
    
    return sticker_buffer, house_buffer, sticker_count, house_count, skipped_products

