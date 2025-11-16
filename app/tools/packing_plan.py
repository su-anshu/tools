import streamlit as st
import pandas as pd
import fitz
import re
from fpdf import FPDF
from io import BytesIO
from collections import defaultdict
from datetime import datetime
import os
import logging
import hashlib
from app.sidebar import MASTER_FILE, BARCODE_PDF_PATH
from app.tools.label_generator import generate_combined_label_pdf_direct, generate_pdf, generate_triple_label_combined
from app.tools.product_label_generator import create_label_pdf, create_pair_label_pdf
from app.utils import (
    is_empty_value, get_unique_key_suffix, setup_tool_ui, 
    load_and_validate_master_data, should_include_product_label,
    initialize_packing_plan_variables, create_packing_plan_tabs,
    create_download_buttons
)
from app.pdf_utils import safe_pdf_context

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def validate_uploaded_file(uploaded_file, max_size_mb=50):
    """Validate uploaded files before processing"""
    if uploaded_file is None:
        return False, "No file uploaded"
    
    if uploaded_file.size > max_size_mb * 1024 * 1024:
        return False, f"File too large (max {max_size_mb}MB)"
    
    if uploaded_file.type not in ['application/pdf']:
        return False, "Invalid file type - only PDF files allowed"
    
    return True, "Valid file"

def highlight_large_qty(pdf_bytes):
    """Improved highlighting function for large quantities in PDF invoices"""
    try:
        with safe_pdf_context(pdf_bytes) as doc:
            in_table = False
            highlighted_count = 0

            for page_num, page in enumerate(doc):
                text_blocks = page.get_text("blocks")
                logger.info(f"Processing page {page_num + 1} with {len(text_blocks)} blocks")

                for block_idx, block in enumerate(text_blocks):
                    if len(block) < 5:
                        continue
                    x0, y0, x1, y1, text = block[:5]

                    # Detect table start
                    if "Description" in text and "Qty" in text:
                        in_table = True
                        logger.info(f"Table started at block {block_idx}")
                        continue

                    if in_table:
                        # Skip blocks without digits
                        if not any(char.isdigit() for char in text):
                            continue
                        
                        # Skip obvious header blocks
                        if any(header in text for header in ["Qty", "Unit Price", "Total", "Description"]):
                            continue

                        # Look for quantities > 1 in the text block
                        should_highlight = False
                        found_qty = None
                        
                        # Method 1: Look for standalone numbers > 1
                        values = text.split()
                        for val in values:
                            if val.isdigit():
                                qty_val = int(val)
                                if qty_val > 1 and qty_val <= 100:  # Reasonable quantity range
                                    should_highlight = True
                                    found_qty = qty_val
                                    break
                        
                        # Method 2: Look for price-quantity patterns
                        if not should_highlight:
                            price_qty_matches = re.findall(r'(\d+)\s+₹[\d,]+\.?\d*\s+\d+%?\s*(IGST|CGST|SGST)', text)
                            for match in price_qty_matches:
                                qty_val = int(match[0])
                                if qty_val > 1:
                                    should_highlight = True
                                    found_qty = qty_val
                                    break
                        
                        # Method 3: Look for lines starting with quantity but avoid tax percentages
                        if not should_highlight:
                            lines_in_block = text.split('\n')
                            for line in lines_in_block:
                                line = line.strip()
                                if line:
                                    # Look for pattern: "3 ₹2,768.67 5% IGST" but not "5% IGST"
                                    qty_match = re.search(r'^(\d+)\s+₹[\d,]+\.?\d*\s+\d+%?\s*(IGST|CGST|SGST)', line)
                                    if qty_match:
                                        qty_val = int(qty_match.group(1))
                                        if qty_val > 1:
                                            should_highlight = True
                                            found_qty = qty_val
                                            break
                                    
                                    # Alternative pattern: look for standalone numbers > 1 followed by price
                                    # but exclude tax percentages
                                    alt_match = re.search(r'^(\d+)', line)
                                    if alt_match:
                                        qty_val = int(alt_match.group(1))
                                        if (qty_val > 1 and qty_val <= 100 and
                                            not re.search(r'^' + str(qty_val) + r'%', line) and
                                            re.search(r'₹[\d,]+\.?\d*', line)):
                                            should_highlight = True
                                            found_qty = qty_val
                                            break
                        
                        # Highlight the block if quantity > 1 found
                        if should_highlight:
                            highlight_box = fitz.Rect(x0, y0, x1, y1)
                            page.draw_rect(highlight_box, color=(1, 0, 0), fill_opacity=0.4)
                            highlighted_count += 1
                            logger.info(f"Highlighted block {block_idx} on page {page_num + 1} with qty {found_qty}")

                    # Exit table when we see TOTAL
                    if "TOTAL" in text.upper():
                        in_table = False
                        logger.info(f"Table ended at block {block_idx}")

            logger.info(f"Total blocks highlighted: {highlighted_count}")
            output_buffer = BytesIO()
            doc.save(output_buffer)
            output_buffer.seek(0)
            return output_buffer
    except Exception as e:
        logger.error(f"Error highlighting PDF: {str(e)}")
        return None

def validate_asin_context(line, line_index, all_lines, asin):
    """
    Validate if ASIN appears in valid invoice table context vs address sections
    
    Args:
        line: The line containing the ASIN
        line_index: Index of the line in all_lines
        all_lines: All lines from the page
        asin: The extracted ASIN
    
    Returns:
        bool: True if ASIN appears in valid context, False otherwise
    """
    # Check if we're in invoice table section (between "Description" and "TOTAL")
    in_invoice_table = False
    description_found = False
    total_found = False
    
    # Look backwards and forwards to determine context
    look_back = max(0, line_index - 20)
    look_forward = min(len(all_lines), line_index + 20)
    
    for i in range(look_back, look_forward):
        if i >= len(all_lines):
            break
        line_text = all_lines[i].upper()
        
        # Check for invoice table markers
        if "DESCRIPTION" in line_text and ("QTY" in line_text or "QUANTITY" in line_text):
            description_found = True
            in_invoice_table = True
        
        # Check for end of table
        if "TOTAL" in line_text and description_found:
            if i > line_index:
                total_found = True
                break
    
    # If we found description but not total yet, we're likely in the table
    if description_found and not total_found and line_index > look_back:
        in_invoice_table = True
    
    # Check for address/shipping indicators (negative signals)
    address_keywords = [
        "SHIP TO", "DELIVERY ADDRESS", "SHIPPING ADDRESS", "BILLING ADDRESS",
        "PIN CODE", "PINCODE", "POSTAL CODE", "STATE:", "CITY:",
        "MOBILE", "PHONE", "CONTACT", "CUSTOMER NAME"
    ]
    
    context_text = " ".join(all_lines[max(0, line_index-5):min(len(all_lines), line_index+5)]).upper()
    is_in_address = any(keyword in context_text for keyword in address_keywords)
    
    # Check for positive signals - ASIN near product-related content
    product_indicators = ["HSN", "NET WEIGHT", "MRP", "UNIT PRICE", "DISCOUNT", "TAX"]
    has_product_context = any(indicator in line.upper() for indicator in product_indicators)
    
    # ASIN is valid if:
    # 1. In invoice table section AND not in address section
    # 2. OR has product context (HSN, price, etc.) AND not in address section
    if is_in_address:
        return False
    
    if in_invoice_table or has_product_context:
        return True
    
    # If context is ambiguous, be conservative and reject
    return False

def extract_asin_from_page(page_text):
    """Extract ASIN from page text with context validation"""
    asin_pattern = re.compile(r"\b(B[0-9A-Z]{9})\b")
    lines = page_text.split("\n")
    
    # Look for ASINs - prefer those in invoice table context, but accept others if not in address
    best_asin = None
    best_asin_score = 0
    
    for i, line in enumerate(lines):
        match = asin_pattern.search(line)
        if match:
            asin = match.group(1)
            # Validate context - returns True if valid, False if invalid
            is_valid = validate_asin_context(line, i, lines, asin)
            
            if is_valid:
                # Score ASINs: higher score for those in invoice table or with product context
                score = 0
                line_upper = line.upper()
                if "DESCRIPTION" in " ".join(lines[max(0, i-10):i]).upper():
                    score += 2  # In invoice table area
                if any(indicator in line_upper for indicator in ["HSN", "MRP", "UNIT PRICE", "TAX"]):
                    score += 1  # Has product context
                
                if score > best_asin_score:
                    best_asin = asin
                    best_asin_score = score
            else:
                # If validation failed, check if it's just ambiguous (not clearly in address)
                # In that case, still consider it but with lower priority
                context_text = " ".join(lines[max(0, i-5):min(len(lines), i+5)]).upper()
                is_in_address = any(keyword in context_text for keyword in 
                                    ["SHIP TO", "DELIVERY ADDRESS", "SHIPPING ADDRESS", "BILLING ADDRESS",
                                     "PIN CODE", "PINCODE", "POSTAL CODE"])
                
                if not is_in_address and best_asin is None:
                    # Accept ambiguous ASINs if no better one found and not clearly in address
                    best_asin = asin
                    best_asin_score = 0
    
    return best_asin

def get_product_name_from_asin(asin, master_df):
    """
    Get product name from master_df using ASIN
    
    Args:
        asin: ASIN code
        master_df: Master data DataFrame
    
    Returns:
        Product name string or "Unknown" if not found
    """
    if master_df is None or master_df.empty:
        return "Unknown"
    
    if "ASIN" not in master_df.columns or "Name" not in master_df.columns:
        return "Unknown"
    
    try:
        match = master_df[master_df["ASIN"] == asin]
        if not match.empty:
            name = str(match.iloc[0].get("Name", "Unknown")).strip()
            return name if name else "Unknown"
    except Exception as e:
        logger.warning(f"Error looking up product name for ASIN {asin}: {str(e)}")
    
    return "Unknown"

def create_asin_lookup_dict(master_df):
    """
    Create O(1) lookup dictionary for ASIN to Name mapping (Phase 1 optimization)
    
    Args:
        master_df: Master data DataFrame
    
    Returns:
        Dictionary mapping ASIN to Name, or None if invalid
    """
    if master_df is None or master_df.empty:
        return None
    
    if "ASIN" not in master_df.columns or "Name" not in master_df.columns:
        return None
    
    try:
        # Create dictionary with ASIN as key, Name as value
        # Handle duplicate ASINs by taking first occurrence
        lookup_dict = {}
        for _, row in master_df.iterrows():
            asin = str(row.get("ASIN", "")).strip()
            name = str(row.get("Name", "Unknown")).strip()
            if asin and asin not in lookup_dict:  # Only add if not already present
                lookup_dict[asin] = name if name else "Unknown"
        
        logger.info(f"Created ASIN lookup dictionary with {len(lookup_dict)} entries")
        return lookup_dict
    except Exception as e:
        logger.error(f"Error creating ASIN lookup dictionary: {str(e)}")
        return None

def highlight_invoice_page(page):
    """Apply highlighting to a single invoice page for quantities > 1"""
    try:
        in_table = False
        highlighted_count = 0
        text_blocks = page.get_text("blocks")
        
        for block_idx, block in enumerate(text_blocks):
            if len(block) < 5:
                continue
            x0, y0, x1, y1, text = block[:5]
            
            # Detect table start
            if "Description" in text and "Qty" in text:
                in_table = True
                continue
            
            if in_table:
                # Skip blocks without digits
                if not any(char.isdigit() for char in text):
                    continue
                
                # Skip obvious header blocks
                if any(header in text for header in ["Qty", "Unit Price", "Total", "Description"]):
                    continue
                
                # Look for quantities > 1
                should_highlight = False
                found_qty = None
                
                # Method 1: Look for standalone numbers > 1
                values = text.split()
                for val in values:
                    if val.isdigit():
                        qty_val = int(val)
                        if qty_val > 1 and qty_val <= 100:
                            should_highlight = True
                            found_qty = qty_val
                            break
                
                # Method 2: Look for price-quantity patterns
                if not should_highlight:
                    price_qty_matches = re.findall(r'(\d+)\s+₹[\d,]+\.?\d*\s+\d+%?\s*(IGST|CGST|SGST)', text)
                    for match in price_qty_matches:
                        qty_val = int(match[0])
                        if qty_val > 1:
                            should_highlight = True
                            found_qty = qty_val
                            break
                
                # Method 3: Look for lines starting with quantity
                if not should_highlight:
                    lines_in_block = text.split('\n')
                    for line in lines_in_block:
                        line = line.strip()
                        if line:
                            qty_match = re.search(r'^(\d+)\s+₹[\d,]+\.?\d*\s+\d+%?\s*(IGST|CGST|SGST)', line)
                            if qty_match:
                                qty_val = int(qty_match.group(1))
                                if qty_val > 1:
                                    should_highlight = True
                                    found_qty = qty_val
                                    break
                            
                            alt_match = re.search(r'^(\d+)', line)
                            if alt_match:
                                qty_val = int(alt_match.group(1))
                                if (qty_val > 1 and qty_val <= 100 and
                                    not re.search(r'^' + str(qty_val) + r'%', line) and
                                    re.search(r'₹[\d,]+\.?\d*', line)):
                                    should_highlight = True
                                    found_qty = qty_val
                                    break
                
                # Highlight the block if quantity > 1 found
                if should_highlight:
                    highlight_box = fitz.Rect(x0, y0, x1, y1)
                    page.draw_rect(highlight_box, color=(1, 0, 0), fill_opacity=0.4)
                    highlighted_count += 1
                
                # Exit table when we see TOTAL
                if "TOTAL" in text.upper():
                    in_table = False
        
        return highlighted_count
    except Exception as e:
        logger.error(f"Error highlighting invoice page: {str(e)}")
        return 0

def sort_pdf_by_asin(pdf_bytes, master_df=None, asin_lookup_dict=None):
    """
    Sort PDF pages by ASIN (primary) and Product Name (secondary)
    while keeping customer pairs (2 pages) together
    
    Args:
        pdf_bytes: Original PDF bytes
        master_df: Master data DataFrame for product name lookup (optional, deprecated - use asin_lookup_dict)
        asin_lookup_dict: O(1) lookup dictionary for ASIN to Name (Phase 1 optimization)
    
    Returns:
        BytesIO buffer with sorted and highlighted PDF, or None if error
    """
    try:
        with safe_pdf_context(pdf_bytes) as doc:
            total_pages = len(doc)
            
            if total_pages == 0:
                logger.warning("Empty PDF provided")
                return None
            
            # Phase 1: Use lookup dictionary if available, fallback to function
            if asin_lookup_dict is None and master_df is not None:
                asin_lookup_dict = create_asin_lookup_dict(master_df)
            
            # Group pages in pairs (2 pages per customer)
            customer_pairs = []
            for i in range(0, total_pages, 2):
                if i + 1 < total_pages:
                    # Pair: page i (shipping label) + page i+1 (invoice)
                    shipping_page_idx = i
                    invoice_page_idx = i + 1
                    
                    # Extract ASIN from invoice page
                    invoice_page = doc[invoice_page_idx]
                    invoice_text = invoice_page.get_text()
                    asin = extract_asin_from_page(invoice_text)
                    
                    # Phase 1: Use O(1) dictionary lookup instead of DataFrame search
                    if asin and asin_lookup_dict:
                        product_name = asin_lookup_dict.get(asin, "Unknown")
                    elif asin:
                        product_name = get_product_name_from_asin(asin, master_df)
                    else:
                        product_name = "Unknown"
                    
                    customer_pairs.append({
                        'asin': asin if asin else "ZZZ_NO_ASIN",  # Put no-ASIN at end
                        'product_name': product_name,
                        'shipping_page_idx': shipping_page_idx,
                        'invoice_page_idx': invoice_page_idx,
                        'original_pair_num': len(customer_pairs) + 1
                    })
                elif i < total_pages:
                    # Odd number of pages - last page alone
                    single_page_idx = i
                    single_page = doc[single_page_idx]
                    page_text = single_page.get_text()
                    asin = extract_asin_from_page(page_text)
                    
                    # Phase 1: Use O(1) dictionary lookup instead of DataFrame search
                    if asin and asin_lookup_dict:
                        product_name = asin_lookup_dict.get(asin, "Unknown")
                    elif asin:
                        product_name = get_product_name_from_asin(asin, master_df)
                    else:
                        product_name = "Unknown"
                    
                    customer_pairs.append({
                        'asin': asin if asin else "ZZZ_NO_ASIN",
                        'product_name': product_name,
                        'shipping_page_idx': single_page_idx,
                        'invoice_page_idx': None,
                        'original_pair_num': len(customer_pairs) + 1
                    })
            
            # Sort pairs by Product Name (primary) and ASIN (secondary)
            # This groups similar products together (e.g., all Sattu variants)
            customer_pairs.sort(key=lambda x: (x['product_name'], x['asin']))
            
            # Create new PDF with sorted pages
            sorted_pdf = fitz.open()
            
            for pair in customer_pairs:
                # Add shipping label page
                sorted_pdf.insert_pdf(doc, from_page=pair['shipping_page_idx'], to_page=pair['shipping_page_idx'])
                
                # Add invoice page (if exists)
                if pair['invoice_page_idx'] is not None:
                    sorted_pdf.insert_pdf(doc, from_page=pair['invoice_page_idx'], to_page=pair['invoice_page_idx'])
            
            # Apply highlighting to invoice pages in sorted PDF
            # Invoice pages are at odd indices (1, 3, 5, ...) in sorted PDF
            for i in range(1, len(sorted_pdf), 2):
                if i < len(sorted_pdf):
                    highlight_invoice_page(sorted_pdf[i])
            
            # Also handle case where last page is single (if odd total pages)
            if total_pages % 2 == 1 and len(sorted_pdf) % 2 == 1:
                # Last page might be an invoice if it was a single page
                last_idx = len(sorted_pdf) - 1
                last_page_text = sorted_pdf[last_idx].get_text()
                # Check if it looks like an invoice (has "Description" or "Qty")
                if "Description" in last_page_text or "Qty" in last_page_text:
                    highlight_invoice_page(sorted_pdf[last_idx])
            
            # Save to buffer
            output_buffer = BytesIO()
            sorted_pdf.save(output_buffer)
            output_buffer.seek(0)
            sorted_pdf.close()
            
            logger.info(f"Sorted {len(customer_pairs)} customer pairs by ASIN")
            return output_buffer
            
    except Exception as e:
        logger.error(f"Error sorting PDF by ASIN: {str(e)}")
        return None


def packing_plan_tool():
    # Setup UI with CSS and components
    css_loaded, UI_ENABLED = setup_tool_ui("Amazon Packing Plan Generator", load_ui_components=True)
    
    # Load and validate master data
    master_df, admin_logged_in, BARCODE_PDF_PATH = load_and_validate_master_data(return_barcode_path=True)

    # Organize content into tabs
    tab1, tab2, tab3, tab4 = create_packing_plan_tabs()
    
    # Initialize variables
    vars_dict = initialize_packing_plan_variables()
    df_orders = vars_dict['df_orders']
    df_physical = vars_dict['df_physical']
    missing_products = vars_dict['missing_products']
    total_orders = vars_dict['total_orders']
    total_physical_items = vars_dict['total_physical_items']
    total_qty_ordered = vars_dict['total_qty_ordered']
    total_qty_physical = vars_dict['total_qty_physical']
    sorted_highlighted_pdf = vars_dict['sorted_highlighted_pdf']
    
    with tab1:
        # File Upload Section - Simple and compact
        pdf_files = st.file_uploader(
            "Upload Invoice PDFs",
            type=["pdf"],
            accept_multiple_files=True,
            help="Upload one or more invoice PDF files"
        )
        
        # Master Data Preview - Collapsed by default
        with st.expander("📋 Master Data", expanded=False):
            st.dataframe(master_df.head(10), use_container_width=True)
            st.caption(f"Total: {len(master_df)} products")
    
    # Simple file info - minimal display
    if pdf_files:
        total_size = sum(f.size for f in pdf_files)
        total_size_mb = total_size / (1024 * 1024)
        file_count = len(pdf_files)
        
        # Simple inline text instead of large cards
        st.caption(f"{file_count} files • {total_size_mb:.2f} MB total")
        
        if total_size_mb > 100:
            st.caption(f"⚠️ Large batch - processing may take longer")
        elif total_size_mb > 50:
            if UI_ENABLED:
                info_card("Processing", f"Processing {file_count} files ({total_size_mb:.2f} MB total). This may take a moment.", "info")
            else:
                st.info(f"ℹ️ Processing {file_count} files ({total_size_mb:.2f} MB total). This may take a moment.")

    def expand_to_physical(df, master_df, asin_lookup_dict=None):
        """
        Convert ordered items to physical packing plan
        
        Args:
            df: Orders DataFrame
            master_df: Master data DataFrame
            asin_lookup_dict: Optional ASIN lookup dictionary for faster access (Phase 1 optimization)
        """
        physical_rows = []
        missing_products = []
        
        # Phase 1: Create lookup dictionary if not provided
        if asin_lookup_dict is None:
            asin_lookup_dict = create_asin_lookup_dict(master_df)
        
        # Phase 1: Create ASIN to row index mapping for faster lookups
        asin_to_index = {}
        if "ASIN" in master_df.columns:
            for idx, row in master_df.iterrows():
                asin = str(row.get("ASIN", "")).strip()
                if asin and asin not in asin_to_index:
                    asin_to_index[asin] = idx
        
        for _, row in df.iterrows():
            try:
                asin = row.get("ASIN", "UNKNOWN")
                qty = int(row.get("Qty", 1))
                
                # Phase 1: Use index lookup for faster access
                if asin in asin_to_index:
                    match_idx = asin_to_index[asin]
                    match_row = master_df.iloc[[match_idx]]
                else:
                    match_row = pd.DataFrame()  # Empty DataFrame if not found
                
                if match_row.empty:
                    logger.warning(f"Product not found in master file: {asin}")
                    missing_products.append({
                        "ASIN": asin,
                        "Issue": "Not found in master file",
                        "Qty": qty
                    })
                    physical_rows.append({
                        "item": f"UNKNOWN PRODUCT ({asin})",
                        "weight": "N/A",
                        "Qty": qty,
                        "Packet Size": "N/A",
                        "Packet used": "N/A",
                        "ASIN": asin,
                        "MRP": "N/A",
                        "FNSKU": "MISSING",
                        "FSSAI": "N/A",
                        "Packed Today": "",
                        "Available": "",
                        "Status": "⚠️ MISSING FROM MASTER"
                    })
                    continue
                
                base = match_row.iloc[0]
                split = str(base.get("Split Into", "")).strip()
                name = base.get("Name", "Unknown Product")
                fnsku = str(base.get("FNSKU", "")).strip()
                
                # Check if FNSKU is missing
                if is_empty_value(fnsku):
                    missing_products.append({
                        "ASIN": asin,
                        "Issue": "Missing FNSKU",
                        "Product": name,
                        "Qty": qty
                    })
                
                # Handle products with split information
                if split and not is_empty_value(split):
                    sizes = [s.strip().replace("kg", "").strip() for s in split.split(",")]
                    split_found = False
                    
                    for size in sizes:
                        try:
                            sub_match = master_df[
                                (master_df["Name"] == name) &
                                (master_df["Net Weight"].astype(str).str.replace("kg", "").str.strip() == size)
                            ]
                            if not sub_match.empty:
                                sub = sub_match.iloc[0]
                                sub_fnsku = str(sub.get("FNSKU", "")).strip()
                                status = "✅ READY" if not is_empty_value(sub_fnsku) else "⚠️ MISSING FNSKU"
                                
                                physical_rows.append({
                                    "item": name,
                                    "weight": sub.get("Net Weight", "N/A"),
                                    "Qty": qty,
                                    "Packet Size": sub.get("Packet Size", "N/A"),
                                    "Packet used": sub.get("Packet used", "N/A"),
                                    "ASIN": sub.get("ASIN", asin),
                                    "MRP": sub.get("M.R.P", "N/A"),
                                    "FNSKU": sub_fnsku if not is_empty_value(sub_fnsku) else "MISSING",
                                    "FSSAI": sub.get("FSSAI", "N/A"),
                                    "Packed Today": "",
                                    "Available": "",
                                    "Status": status
                                })
                                split_found = True
                        except (ValueError, KeyError, AttributeError) as e:
                            # Phase 3: Specific exception handling
                            error_type = type(e).__name__
                            logger.error(f"Error processing split variant for {name}: {error_type} - {str(e)}")
                        except Exception as e:
                            # Phase 3: Catch-all
                            logger.error(f"Unexpected error processing split variant for {name}: {str(e)}")
                    
                    if not split_found:
                        missing_products.append({
                            "ASIN": asin,
                            "Issue": "Split sizes not found in master file",
                            "Product": name,
                            "Split Info": split,
                            "Qty": qty
                        })
                else:
                    # No split information - use base product
                    status = "✅ READY" if not is_empty_value(fnsku) else "⚠️ MISSING FNSKU"
                    
                    physical_rows.append({
                        "item": name,
                        "weight": base.get("Net Weight", "N/A"),
                        "Qty": qty,
                        "Packet Size": base.get("Packet Size", "N/A"),
                        "Packet used": base.get("Packet used", "N/A"),
                        "ASIN": asin,
                        "MRP": base.get("M.R.P", "N/A"),
                        "FNSKU": fnsku if not is_empty_value(fnsku) else "MISSING",
                        "FSSAI": base.get("FSSAI", "N/A"),
                        "Packed Today": "",
                        "Available": "",
                        "Status": status
                    })
            except (ValueError, KeyError) as e:
                # Phase 3: Specific exception handling
                error_type = type(e).__name__
                logger.error(f"Error processing row {asin}: {error_type} - {str(e)}")
                continue
            except Exception as e:
                # Phase 3: Catch-all for unexpected errors
                logger.error(f"Unexpected error processing row {asin}: {str(e)}")
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
            # If no physical rows were created, this means there's an issue with data processing
            logger.warning("No physical rows generated - this may indicate data processing issues")
        
        return df_physical, missing_products

    def generate_summary_pdf(original_df, physical_df, missing_products=None):
        """Generate PDF summary with proper encoding handling"""
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

            def add_table(df, title, include_tracking=False, hide_asin=False):
                """Add table to PDF"""
                pdf.set_font("Arial", "B", 12)
                pdf.cell(0, 10, clean_text(title), 0, 1, "C")
                pdf.set_font("Arial", "", 10)
                pdf.cell(0, 8, f"Generated on: {timestamp}", 0, 1, "C")
                pdf.ln(2)

                headers = ["Item", "Weight", "Qty", "Packet Size"]
                col_widths = [50, 25, 20, 35]

                if not hide_asin:
                    headers.append("ASIN")
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
                    values = [
                        clean_text(str(row.get("item", "")))[:20],
                        clean_text(str(row.get("weight", ""))),
                        str(row.get("Qty", 0)),
                        clean_text(str(row.get("Packet Size", "")))[:15]
                    ]
                    if not hide_asin:
                        values.append(clean_text(str(row.get("ASIN", ""))))
                    if include_tracking:
                        values += [
                            clean_text(str(row.get("Packed Today", ""))),
                            clean_text(str(row.get("Available", "")))
                        ]
                        
                    for val, width in zip(values, col_widths):
                        pdf.cell(width, 10, str(val)[:width//2], 1)  # Truncate to fit
                    pdf.ln()

            pdf.add_page()
            add_table(original_df, "Original Ordered Items (from Invoice)", hide_asin=False)
            pdf.ln(5)
            add_table(physical_df, "Actual Physical Packing Plan", include_tracking=True, hide_asin=True)
            
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

    def generate_labels_by_packet_used(df_physical, master_df, nutrition_df, progress_callback=None):
        """
        Automatically generate labels based on 'Packet used' column using direct barcode generation
        
        IMPORTANT: All labels from all products are accumulated into single combined PDF buffers.
        This function processes all products and combines them into two outputs: sticker labels and house labels.
        
        Args:
            df_physical: Physical packing plan DataFrame (contains all products from all uploaded PDFs)
            master_df: Master data DataFrame
            nutrition_df: Nutrition data DataFrame (for triple labels)
            progress_callback: Optional callback function(progress, status) for progress updates
        
        Returns:
            tuple: (sticker_pdf_buffer, house_pdf_buffer, sticker_count, house_count, skipped_products)
            - sticker_pdf_buffer: Single combined PDF with all sticker labels
            - house_pdf_buffer: Single combined PDF with all house labels
        """
        # IMPORTANT: All labels are accumulated into single combined PDFs
        sticker_pdf = fitz.open()  # Single combined PDF for all sticker labels
        house_pdf = fitz.open()    # Single combined PDF for all house labels
        sticker_count = 0
        house_count = 0
        skipped_products = []
        
        # Phase 0: Progress tracking
        total_products = len(df_physical)
        processed_count = 0
        
        if df_physical.empty:
            return BytesIO(), BytesIO(), 0, 0, []
        
        # Check if "Packet used" column exists
        if "Packet used" not in df_physical.columns:
            logger.warning("'Packet used' column not found in physical packing plan")
            return BytesIO(), BytesIO(), 0, 0, []
        
        # Separate products by "Packet used" value (case-insensitive, strip whitespace)
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
        sticker_total = len(sticker_products)
        for idx, (_, row) in enumerate(sticker_products.iterrows()):
            fnsku = str(row.get('FNSKU', '')).strip()
            qty = int(row.get('Qty', 0))
            product_name = str(row.get("item", "")).strip()
            
            # Removed progress callback to prevent reruns - labels are cached in session state
            
            if fnsku and fnsku != "MISSING" and not is_empty_value(fnsku):
                for _ in range(qty):
                    try:
                        # Always use direct generation method
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
        house_total = len(house_products)
        for idx, (_, row) in enumerate(house_products.iterrows()):
            fnsku = str(row.get('FNSKU', '')).strip()
            qty = int(row.get('Qty', 0))
            product_name = str(row.get("item", "")).strip()
            
            # Removed progress callback to prevent reruns - labels are cached in session state
            
            if fnsku and fnsku != "MISSING" and not is_empty_value(fnsku):
                # Find nutrition data
                nutrition_row = None
                if nutrition_df is not None and not nutrition_df.empty:
                    # Try to match by product name
                    if product_name:
                        nutrition_matches = nutrition_df[
                            nutrition_df["Product"].str.contains(product_name, case=False, na=False)
                        ]
                        if not nutrition_matches.empty:
                            nutrition_row = nutrition_matches.iloc[0]
                    
                    # Try alternate matching strategies if first attempt failed
                    if nutrition_row is None:
                        for col in ["Product", "item"]:
                            if col in nutrition_df.columns:
                                exact_match = nutrition_df[nutrition_df[col] == product_name]
                                if not exact_match.empty:
                                    nutrition_row = exact_match.iloc[0]
                                    break
                
                if nutrition_row is not None:
                    for copy_num in range(qty):
                        try:
                            # Always use direct generation method
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
        
        # Phase 1: Explicit resource cleanup
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

    if pdf_files:
        logger.info(f"Processing {len(pdf_files)} PDF files")
        
        # Phase 1: Enhanced input validation
        MAX_FILES = 50  # Reasonable limit
        MAX_TOTAL_SIZE_MB = 200  # Reasonable limit
        
        if len(pdf_files) > MAX_FILES:
            st.error(f"❌ **Too Many Files**: Maximum {MAX_FILES} files allowed. You uploaded {len(pdf_files)} files.")
            st.info(f"💡 **Solution**: Please split your files into batches of {MAX_FILES} or fewer.")
            return
        
        total_size = sum(f.size for f in pdf_files)
        total_size_mb = total_size / (1024 * 1024)
        
        if total_size_mb > MAX_TOTAL_SIZE_MB:
            st.error(f"❌ **Files Too Large**: Maximum total size is {MAX_TOTAL_SIZE_MB} MB. Your files total {total_size_mb:.2f} MB.")
            st.info(f"💡 **Solution**: Please reduce the number of files or their sizes.")
            return
        
        # Validate individual files
        invalid_files = []
        for pdf_file in pdf_files:
            is_valid, message = validate_uploaded_file(pdf_file)
            if not is_valid:
                invalid_files.append((pdf_file.name, message))
        
        if invalid_files:
            st.error(f"❌ **Invalid Files Detected**: {len(invalid_files)} file(s) have issues:")
            for filename, msg in invalid_files:
                st.write(f"• **{filename}**: {msg}")
            st.info("💡 **Solution**: Please upload only valid PDF files and try again.")
            return

        # Phase 0: Progress indicators (Zero Risk - UI only)
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # Phase 1: Create ASIN lookup dictionary once (Low Risk - Performance optimization)
        asin_lookup_dict = create_asin_lookup_dict(master_df)
        
        asin_qty_data = defaultdict(int)
        all_pdf_bytes = []
        
        # Improved ASIN pattern
        asin_pattern = re.compile(r"\b(B[0-9A-Z]{9})\b")
        qty_pattern = re.compile(r"\bQty\b.*?(\d+)")
        price_qty_pattern = re.compile(r"₹[\d,.]+\s+(\d+)\s+₹[\d,.]+")

        # First pass: Extract ASINs and quantities, collect all PDF bytes
        total_files = len(pdf_files)
        for file_idx, uploaded_file in enumerate(pdf_files):
            # Phase 0: Update progress
            progress = (file_idx + 1) / (total_files * 2)  # Half progress for first pass
            progress_bar.progress(progress)
            status_text.text(f"📄 Processing file {file_idx + 1}/{total_files}: {uploaded_file.name}")
            try:
                pdf_name = uploaded_file.name
                pdf_bytes = uploaded_file.read()
                all_pdf_bytes.append(pdf_bytes)
                
                with safe_pdf_context(pdf_bytes) as doc:
                    pages_text = [page.get_text().split("\n") for page in doc]

                    for lines in pages_text:
                        # Track location context for invoice table vs address sections
                        in_invoice_table = False
                        description_found = False
                        
                        for i, line in enumerate(lines):
                            # Update location tracking
                            line_upper = line.upper()
                            if "DESCRIPTION" in line_upper and ("QTY" in line_upper or "QUANTITY" in line_upper):
                                description_found = True
                                in_invoice_table = True
                            
                            if "TOTAL" in line_upper and description_found:
                                in_invoice_table = False
                            
                            # Check for address sections (negative signal)
                            address_keywords = [
                                "SHIP TO", "DELIVERY ADDRESS", "SHIPPING ADDRESS", "BILLING ADDRESS",
                                "PIN CODE", "PINCODE", "POSTAL CODE"
                            ]
                            is_in_address = any(keyword in line_upper for keyword in address_keywords)
                            if is_in_address:
                                in_invoice_table = False
                            
                            # Extract ASIN with context validation
                            asin_match = asin_pattern.search(line)
                            if asin_match:
                                asin = asin_match.group(1)
                                
                                # Check for positive signals (product-related context)
                                has_product_context = any(indicator in line_upper for indicator in 
                                                         ["HSN", "NET WEIGHT", "MRP", "UNIT PRICE", "DISCOUNT", "TAX", "IGST", "CGST", "SGST"])
                                
                                # Check surrounding context for address indicators (more comprehensive check)
                                context_start = max(0, i - 5)
                                context_end = min(len(lines), i + 5)
                                context_lines = lines[context_start:context_end]
                                context_text = " ".join(context_lines).upper()
                                
                                # Strong address indicators - if found, definitely skip
                                strong_address_patterns = [
                                    r"SHIP\s+TO\s*:?", r"DELIVERY\s+ADDRESS\s*:?", r"SHIPPING\s+ADDRESS\s*:?",
                                    r"BILLING\s+ADDRESS\s*:?", r"PIN\s*CODE\s*:?", r"PINCODE\s*:?",
                                    r"POSTAL\s+CODE\s*:?", r"STATE\s*:?", r"CITY\s*:?"
                                ]
                                is_in_strong_address = any(re.search(pattern, context_text) for pattern in strong_address_patterns)
                                
                                # Check if line itself contains address keywords
                                address_in_line = any(keyword in line_upper for keyword in 
                                                      ["SHIP TO", "DELIVERY ADDRESS", "SHIPPING ADDRESS", 
                                                       "BILLING ADDRESS", "PIN CODE", "PINCODE", "POSTAL CODE"])
                                
                                # Only skip if clearly in address section AND not in invoice table AND no product context
                                if (is_in_strong_address or address_in_line) and not in_invoice_table and not has_product_context:
                                    logger.debug(f"Skipping ASIN {asin} - found in address section: {line.strip()[:50]}")
                                    continue
                                
                                # Pre-validate against master data to filter false positives
                                # Only reject if: not in master AND clearly in address context AND no product context AND not in invoice table
                                if asin_lookup_dict and asin not in asin_lookup_dict:
                                    if (is_in_strong_address or address_in_line) and not has_product_context and not in_invoice_table:
                                        logger.debug(f"Skipping ASIN {asin} - not in master, in address context, no product context: {line.strip()[:50]}")
                                        continue
                                    # Otherwise, accept it (might be new product or legitimate ASIN)
                                    logger.info(f"ASIN {asin} not found in master data but accepted (context: invoice_table={in_invoice_table}, product_context={has_product_context})")
                                
                                qty = 1
                                # IMPROVED: Look for quantity in next 6 lines (was 4)
                                search_range = min(i + 6, len(lines))
                                for j in range(i, search_range):
                                    qty_line = lines[j]
                                    
                                    # Pattern 1: Original Qty pattern
                                    match = qty_pattern.search(qty_line)
                                    if match:
                                        qty = int(match.group(1))
                                        logger.info(f"Found qty {qty} using Qty pattern: {qty_line.strip()}")
                                        break
                                    
                                    # Pattern 2: Original price pattern  
                                    match = price_qty_pattern.search(qty_line)
                                    if match:
                                        qty = int(match.group(1))
                                        logger.info(f"Found qty {qty} using price pattern: {qty_line.strip()}")
                                        break
                                    
                                    # Pattern 3: NEW - Multi-item pattern like "3 ₹2,768.67 5% IGST"
                                    multi_item_match = re.search(r'^(\d+)\s+₹[\d,]+\.?\d*\s+\d+%?\s*(IGST|CGST|SGST)', qty_line.strip())
                                    if multi_item_match:
                                        potential_qty = int(multi_item_match.group(1))
                                        if 1 <= potential_qty <= 100:
                                            qty = potential_qty
                                            logger.info(f"Found qty {qty} using multi-item pattern: {qty_line.strip()}")
                                            break
                                    
                                    # Pattern 4: NEW - Standalone number followed by price (but not tax %)
                                    standalone_match = re.search(r'^(\d+)', qty_line.strip())
                                    if standalone_match:
                                        potential_qty = int(standalone_match.group(1))
                                        # Avoid tax percentages and ensure it's reasonable quantity
                                        if (1 <= potential_qty <= 100 and 
                                            not re.search(r'^' + str(potential_qty) + r'%', qty_line.strip()) and
                                            not re.search(r'HSN:', qty_line) and
                                            re.search(r'₹[\d,]+\.?\d*', qty_line)):
                                            qty = potential_qty
                                            logger.info(f"Found qty {qty} using standalone pattern: {qty_line.strip()}")
                                            break
                                
                                asin_qty_data[asin] += qty
                                logger.info(f"Added ASIN {asin} with qty {qty} (context: invoice_table={in_invoice_table}, product_context={has_product_context})")

            except (ValueError, KeyError, IOError, OSError) as e:
                # Phase 3: Specific exception handling
                error_type = type(e).__name__
                error_msg = f"Error processing {uploaded_file.name}: {error_type} - {str(e)}"
                logger.error(error_msg)
                st.warning(f"⚠️ **File Processing Error** ({error_type}): Could not process '{uploaded_file.name}'. Error: {str(e)}. This file will be skipped.")
            except Exception as e:
                # Phase 3: Catch-all for unexpected errors
                error_msg = f"Unexpected error processing {uploaded_file.name}: {str(e)}"
                logger.error(error_msg)
                st.warning(f"⚠️ **Unexpected Error**: Could not process '{uploaded_file.name}'. Error: {str(e)}")
        
        # Second pass: Combine all PDFs and sort by ASIN (OUTSIDE LOOP - FIXED)
        # Phase 0: Update progress for second pass
        status_text.text("🔄 Combining PDFs and sorting by Product Name & ASIN...")
        progress_bar.progress(0.5)
        
        sorted_highlighted_pdf = None
        if all_pdf_bytes:
            try:
                # Combine all PDFs into one
                combined_pdf = fitz.open()
                for pdf_bytes in all_pdf_bytes:
                    with safe_pdf_context(pdf_bytes) as doc:
                        combined_pdf.insert_pdf(doc)
                
                # Convert combined PDF to bytes
                combined_buffer = BytesIO()
                combined_pdf.save(combined_buffer)
                combined_buffer.seek(0)
                combined_bytes = combined_buffer.read()
                combined_pdf.close()
                combined_buffer.close()
                
                # Phase 0: Update progress
                progress_bar.progress(0.75)
                status_text.text("🎨 Applying highlighting and finalizing sorted PDF...")
                
                # Phase 1: Pass lookup dictionary for faster processing
                # IMPORTANT: All uploaded PDFs are combined into a single sorted PDF
                sorted_highlighted_pdf = sort_pdf_by_asin(combined_bytes, master_df, asin_lookup_dict)
                
                # Phase 0: Complete progress
                progress_bar.progress(1.0)
                status_text.text("✅ PDF processing complete!")
                
                # Document that all PDFs are combined
                logger.info(f"Combined {len(all_pdf_bytes)} PDF files into single sorted PDF")
                
            except (IOError, OSError, MemoryError) as e:
                # Phase 3: Specific exception handling for PDF operations
                error_type = type(e).__name__
                error_msg = f"Error combining and sorting PDFs: {error_type} - {str(e)}"
                logger.error(error_msg)
                if isinstance(e, MemoryError):
                    st.error(f"❌ **Memory Error**: PDFs are too large to process together ({total_size_mb:.2f} MB). Try processing fewer files at once.")
                else:
                    st.error(f"❌ **PDF Processing Error** ({error_type}): {str(e)}. The sorted PDF will not be available, but other features will still work.")
            except Exception as e:
                # Phase 3: Catch-all for unexpected errors
                error_msg = f"Unexpected error combining and sorting PDFs: {str(e)}"
                logger.error(error_msg)
                st.error(f"❌ **Unexpected Error**: {str(e)}. The sorted PDF will not be available, but other features will still work.")
        else:
            progress_bar.progress(1.0)
            status_text.empty()

        # Phase 0: Clear progress indicators
        progress_bar.empty()
        status_text.empty()

        if not asin_qty_data:
            st.error("❌ **No ASIN Codes Found**: No ASIN codes were found in the uploaded PDFs.")
            st.info("**Possible causes:**")
            st.write("• PDFs may not be Amazon invoice PDFs")
            st.write("• PDFs may be corrupted or unreadable")
            st.write("• ASIN format may have changed")
            st.write("• Please verify the PDF files are valid Amazon invoices")
            return

        # Create orders dataframe
        df_orders = pd.DataFrame([{"ASIN": asin, "Qty": qty} for asin, qty in asin_qty_data.items()])
        df_orders = pd.merge(df_orders, master_df, on="ASIN", how="left")
        
        # Safe column renaming
        rename_dict = {}
        if "Name" in df_orders.columns:
            rename_dict["Name"] = "item"
        if "Net Weight" in df_orders.columns:
            rename_dict["Net Weight"] = "weight"
        if "M.R.P" in df_orders.columns:
            rename_dict["M.R.P"] = "MRP"
        
        df_orders.rename(columns=rename_dict, inplace=True)
        
        # Select available columns
        available_columns = ["Qty"]
        for col in ["item", "weight", "Packet Size", "Packet used", "ASIN", "MRP", "FNSKU", "FSSAI"]:
            if col in df_orders.columns:
                available_columns.append(col)
        
        df_orders = df_orders[available_columns]

        # Phase 1: Pass lookup dictionary for faster processing
        df_physical, missing_products = expand_to_physical(df_orders, master_df, asin_lookup_dict)

        # Phase 0: Summary statistics
        total_orders = len(df_orders)
        total_physical_items = len(df_physical) if not df_physical.empty else 0
        total_qty_ordered = df_orders['Qty'].sum() if 'Qty' in df_orders.columns else 0
        total_qty_physical = df_physical['Qty'].sum() if not df_physical.empty and 'Qty' in df_physical.columns else 0
        
        # Minimal success notification
        st.caption("✅ Packing plan generated")
        
        # Simple metrics - no custom cards
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Orders", total_orders)
        with col2:
            st.metric("Items", total_physical_items)
        with col3:
            st.metric("Qty Ordered", int(total_qty_ordered))
        with col4:
            st.metric("Qty Physical", int(total_qty_physical))

        # Simple error message for missing products
        if missing_products:
            st.warning(f"{len(missing_products)} product(s) have issues")
            with st.expander("View Missing Products", expanded=False):
                missing_df = pd.DataFrame(missing_products)
                st.dataframe(missing_df, use_container_width=True)

    with tab2:
        # Results & Preview Tab - Simple layout
        if pdf_files and not df_orders.empty:
            # Summary metrics - Compact
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
                    # Fallback without styling
                    st.dataframe(df_physical, use_container_width=True, height=300)
            else:
                if missing_products:
                    st.error("⚠️ **No physical packing plan generated!**")
                    st.info("**Possible causes:**")
                    st.write("• All products may be missing from the master file")
                    st.write("• Check the missing products listed above")
                    st.write("• Verify that your master file contains the required ASINs")
                    st.write("• Missing FSSAI numbers are automatically handled with 'N/A'")
                else:
                    st.warning("No orders to process. Please upload a valid orders file.")
        else:
            st.info("Please upload invoice PDFs to see results.")

    with tab3:
        # Downloads Tab - Simple layout
        if pdf_files and not df_physical.empty:
            # Generate unique key suffix from data
            pdf_key_suffix = get_unique_key_suffix(df_physical)
            
            # Generate summary PDF
            summary_pdf = None
            try:
                summary_pdf = generate_summary_pdf(df_orders, df_physical, missing_products)
            except Exception as e:
                st.error(f"Error generating PDF: {str(e)}")
            
            # Create download buttons
            missing_products_df = pd.DataFrame(missing_products) if missing_products else None
            create_download_buttons(
                pdf_data=summary_pdf,
                excel_dataframes=[("Physical Packing Plan", df_physical), ("Original Orders", df_orders)],
                pdf_filename="Packing_Plan.pdf",
                excel_filename="Packing_Plan.xlsx",
                key_suffix=f"packing_plan_{pdf_key_suffix}",
                pdf_label="Packing Plan PDF",
                excel_label="Excel Workbook",
                missing_products_df=missing_products_df
            )
            
            st.markdown("---")
            
            # Sorted PDF
            if sorted_highlighted_pdf:
                sorted_pdf_key_suffix = get_unique_key_suffix(sorted_highlighted_pdf)
                st.download_button(
                    "Sorted Invoices PDF", 
                    data=sorted_highlighted_pdf, 
                    file_name=f"Sorted_Invoices_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf", 
                    mime="application/pdf",
                    key=f"download_sorted_pdf_{sorted_pdf_key_suffix}",
                    use_container_width=True
                )
        else:
            st.info("Please upload invoice PDFs to generate downloads.")

    with tab4:
        # Labels Tab - Minimal layout
        if pdf_files and not df_physical.empty:
            # Check if "Packet used" column exists
            if "Packet used" not in df_physical.columns:
                st.warning("'Packet used' column not found")
            else:
                # Load nutrition data for House labels
                try:
                    from app.data_loader import load_nutrition_data_silent
                    nutrition_df = load_nutrition_data_silent()
                except Exception as e:
                    logger.error(f"Error loading nutrition data: {str(e)}")
                    nutrition_df = None
                
                # Fix: Use session state caching to prevent regeneration on every rerun
                # Create hash of input data to detect changes
                try:
                    # Create hash from relevant columns of df_physical
                    hash_data = pd.util.hash_pandas_object(df_physical[['ASIN', 'Qty', 'FNSKU', 'Packet used']] if all(col in df_physical.columns for col in ['ASIN', 'Qty', 'FNSKU', 'Packet used']) else df_physical).values
                    data_hash = hashlib.md5(hash_data.tobytes()).hexdigest()
                except Exception as e:
                    # Fallback: hash entire dataframe
                    logger.warning(f"Could not create selective hash, using full dataframe: {e}")
                    data_hash = hashlib.md5(pd.util.hash_pandas_object(df_physical).values.tobytes()).hexdigest()
                
                # Check if labels already generated for this data
                if 'label_cache_hash' not in st.session_state or st.session_state.label_cache_hash != data_hash:
                    # Generate labels (without progress callback to prevent reruns)
                    with st.spinner("🔄 Generating labels..."):
                        try:
                            sticker_buffer, house_buffer, sticker_count, house_count, skipped_products = generate_labels_by_packet_used(
                                df_physical, master_df, nutrition_df, progress_callback=None
                            )
                            
                            # Store in session state
                            st.session_state.label_cache_hash = data_hash
                            st.session_state.sticker_buffer = sticker_buffer
                            st.session_state.house_buffer = house_buffer
                            st.session_state.sticker_count = sticker_count
                            st.session_state.house_count = house_count
                            st.session_state.skipped_products = skipped_products
                            
                            logger.info(f"Labels generated and cached. Hash: {data_hash[:8]}...")
                        except Exception as e:
                            error_msg = f"Error generating labels: {str(e)}"
                            logger.error(error_msg)
                            st.error(f"❌ **Label Generation Error**: {str(e)}")
                            st.info("💡 **Troubleshooting**: Check that products have valid FNSKU codes and 'Packet used' values in the master sheet.")
                            # Set empty values to prevent retry loop
                            st.session_state.label_cache_hash = data_hash
                            st.session_state.sticker_buffer = BytesIO()
                            st.session_state.house_buffer = BytesIO()
                            st.session_state.sticker_count = 0
                            st.session_state.house_count = 0
                            st.session_state.skipped_products = []
                else:
                    # Use cached values
                    logger.info(f"Using cached labels. Hash: {data_hash[:8]}...")
                    sticker_buffer = st.session_state.sticker_buffer
                    house_buffer = st.session_state.house_buffer
                    sticker_count = st.session_state.sticker_count
                    house_count = st.session_state.house_count
                    skipped_products = st.session_state.skipped_products
                
                # Display results and download buttons
                # IMPORTANT: All labels from all uploaded PDFs are combined into single PDF files
                try:
                    # Generate unique key suffixes from label data hash (data_hash is in scope here)
                    sticker_key_suffix = data_hash[:8]
                    house_key_suffix = data_hash[:8]
                    
                    # Simple label download buttons
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        if sticker_buffer and sticker_count > 0:
                            st.metric("Sticker Labels", sticker_count)
                            st.download_button(
                                f"Download ({sticker_count})",
                                data=sticker_buffer,
                                file_name=f"Sticker_Labels_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
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
                                file_name=f"House_Labels_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
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
                            st.caption(f"Total skipped: {len(skipped_products)} products")
                        
                except Exception as e:
                    # Phase 0: Better error messages
                    error_msg = f"Error displaying labels: {str(e)}"
                    logger.error(error_msg)
                    st.error(f"❌ **Error Displaying Labels**: {str(e)}")
                
                # Product Labels Section (96x25mm - two labels side by side)
                # This section is outside the try-except to ensure it always shows
                st.markdown("---")
                st.markdown("**Product Labels (96x25mm)**")
                
                # Extract unique product names from sticker and house labels
                try:
                    sticker_house_products = df_physical[
                        df_physical["Packet used"].astype(str).str.strip().str.lower().isin(["sticker", "house"])
                    ]
                    
                    if not sticker_house_products.empty:
                        # Filter out rows with invalid product names
                        sticker_house_products = sticker_house_products[
                            sticker_house_products["item"].notna() & 
                            (sticker_house_products["item"].astype(str).str.strip() != "") &
                            (sticker_house_products["item"].astype(str).str.strip().str.lower() != "nan")
                        ]
                        
                        if not sticker_house_products.empty:
                            # Check if product labels already generated for this data
                            product_label_cache_key = f'product_label_cache_{data_hash}'
                            
                            if product_label_cache_key not in st.session_state or st.session_state.get(f'{product_label_cache_key}_hash') != data_hash:
                                # Generate product labels
                                with st.spinner("🔄 Generating product labels..."):
                                    try:
                                        # Create combined PDFs for product labels
                                        product_labels_with_date = fitz.open()
                                        product_labels_without_date = fitz.open()
                                        
                                        # Create a flat list of all product names (repeated by quantity)
                                        # Only include products with "Product Label" = "Yes" in master data
                                        product_list = []
                                        for _, row in sticker_house_products.iterrows():
                                            try:
                                                product_name = str(row.get("item", "")).strip()
                                                qty = int(row.get("Qty", 1))
                                                
                                                if not product_name or product_name.lower() == "nan":
                                                    continue
                                                
                                                # Check if product should be included based on "Product Label" column
                                                if should_include_product_label(product_name, master_df, row):
                                                    # Add product name qty times to the list
                                                    product_list.extend([product_name] * qty)
                                                else:
                                                    logger.debug(f"Product '{product_name}' excluded from labels (Product Label != 'Yes')")
                                            except Exception as e:
                                                logger.warning(f"Could not process product for {row.get('item', 'unknown')}: {e}")
                                        
                                        # Process product list in pairs (2 labels per page)
                                        for i in range(0, len(product_list), 2):
                                            try:
                                                product1 = product_list[i]
                                                product2 = product_list[i + 1] if i + 1 < len(product_list) else None
                                                
                                                # Generate label with date (96x25mm - two labels side by side)
                                                label_pdf_bytes_with_date = create_pair_label_pdf(product1, product2, include_date=True)
                                                if label_pdf_bytes_with_date:
                                                    with safe_pdf_context(label_pdf_bytes_with_date) as label_doc:
                                                        product_labels_with_date.insert_pdf(label_doc)
                                                
                                                # Generate label without date (96x25mm - two labels side by side)
                                                label_pdf_bytes_without_date = create_pair_label_pdf(product1, product2, include_date=False)
                                                if label_pdf_bytes_without_date:
                                                    with safe_pdf_context(label_pdf_bytes_without_date) as label_doc:
                                                        product_labels_without_date.insert_pdf(label_doc)
                                            except Exception as e:
                                                logger.warning(f"Could not generate product label pair: {e}")
                                        
                                        # Save to buffers
                                        product_label_buffer_with_date = BytesIO()
                                        product_label_buffer_without_date = BytesIO()
                                        
                                        if len(product_labels_with_date) > 0:
                                            product_labels_with_date.save(product_label_buffer_with_date)
                                            product_label_buffer_with_date.seek(0)
                                            # Store bytes for reliable downloads
                                            product_label_bytes_with_date = product_label_buffer_with_date.getvalue()
                                        else:
                                            product_label_bytes_with_date = b''
                                        
                                        if len(product_labels_without_date) > 0:
                                            product_labels_without_date.save(product_label_buffer_without_date)
                                            product_label_buffer_without_date.seek(0)
                                            # Store bytes for reliable downloads
                                            product_label_bytes_without_date = product_label_buffer_without_date.getvalue()
                                        else:
                                            product_label_bytes_without_date = b''
                                        
                                        product_labels_with_date.close()
                                        product_labels_without_date.close()
                                        
                                        # Store in session state (store bytes for reliable downloads)
                                        total_label_count = int(sticker_house_products['Qty'].sum()) if 'Qty' in sticker_house_products.columns else 0
                                        st.session_state[product_label_cache_key] = {
                                            'with_date': product_label_bytes_with_date,
                                            'without_date': product_label_bytes_without_date,
                                            'count': total_label_count
                                        }
                                        st.session_state[f'{product_label_cache_key}_hash'] = data_hash
                                        
                                        logger.info(f"Product labels generated: {total_label_count} total labels")
                                    except Exception as e:
                                        logger.error(f"Error generating product labels: {str(e)}")
                                        st.error(f"❌ **Error Generating Product Labels**: {str(e)}")
                                        # Set empty values
                                        st.session_state[product_label_cache_key] = {
                                            'with_date': b'',
                                            'without_date': b'',
                                            'count': 0
                                        }
                                        st.session_state[f'{product_label_cache_key}_hash'] = data_hash
                            else:
                                # Use cached values
                                logger.info(f"Using cached product labels. Hash: {data_hash[:8]}...")
                            
                            # Display product label download buttons
                            cached_labels = st.session_state.get(product_label_cache_key, {})
                            total_label_count = cached_labels.get('count', int(sticker_house_products['Qty'].sum()) if 'Qty' in sticker_house_products.columns else 0)
                            product_label_bytes_with_date = cached_labels.get('with_date', b'')
                            product_label_bytes_without_date = cached_labels.get('without_date', b'')
                            
                            if total_label_count > 0:
                                st.caption(f"Product labels: {total_label_count} total labels")
                                
                                # Display download button for labels without date only
                                if product_label_bytes_without_date and len(product_label_bytes_without_date) > 0:
                                    st.download_button(
                                        "📥 Download without Date",
                                        data=product_label_bytes_without_date,
                                        file_name=f"Product_Labels_No_Date_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                                        mime="application/pdf",
                                        key=f"download_product_labels_no_date_{data_hash[:8]}",
                                        use_container_width=True
                                    )
                                else:
                                    st.caption("No labels available")
                        else:
                            st.caption("No product names found for label generation")
                    else:
                        st.caption("No sticker or house products found for product label generation")
                except Exception as e:
                    logger.error(f"Error in product labels section: {str(e)}")
                    st.warning(f"⚠️ Error processing product labels: {str(e)}")
        else:
            if pdf_files:
                st.info("ℹ️ No physical packing plan available for label generation.")
            else:
                st.info("Please upload invoice PDFs to generate labels.")

        # MRP-only labels section
        if pdf_files and not df_physical.empty:
            try:
                mrp_only_rows = df_physical[df_physical["FNSKU"].isin(["", "MISSING", "nan", "None"]) | df_physical["FNSKU"].isna()]

                if not mrp_only_rows.empty:
                    mrp_only_pdf = fitz.open()
                    mrp_only_count = 0

                    for _, row in mrp_only_rows.iterrows():
                        qty = int(row.get("Qty", 0))
                        for _ in range(qty):
                            try:
                                single_label_pdf = generate_pdf(pd.DataFrame([row]))
                                if single_label_pdf:
                                    with safe_pdf_context(single_label_pdf.read()) as label_doc:
                                        mrp_only_pdf.insert_pdf(label_doc)
                                    mrp_only_count += 1
                            except Exception as e:
                                logger.warning(f"Failed to generate MRP label for {row.get('item', 'unknown')}: {e}")

                    if len(mrp_only_pdf) > 0:
                        buf = BytesIO()
                        mrp_only_pdf.save(buf)
                        buf.seek(0)
                        
                        mrp_key_suffix = get_unique_key_suffix(mrp_only_rows)
                        
                        st.metric("MRP-Only Labels", mrp_only_count)
                        st.download_button(
                            f"Download ({mrp_only_count})", 
                            data=buf, 
                            file_name="MRP_Only_Labels.pdf", 
                            mime="application/pdf", 
                            key=f"download_mrp_labels_{mrp_key_suffix}",
                            use_container_width=True
                        )
                    else:
                        st.caption("No MRP-only labels")
                    
                    mrp_only_pdf.close()
            except Exception as e:
                st.error(f"Error generating MRP-only labels: {str(e)}")

