import streamlit as st
import pandas as pd
import fitz
import re
from fpdf import FPDF
from io import BytesIO
from collections import defaultdict
from datetime import datetime
import os
import contextlib
import logging
from app.sidebar import sidebar_controls, load_master_data, MASTER_FILE, BARCODE_PDF_PATH
from app.tools.label_generator import generate_combined_label_pdf, generate_combined_label_vertical_pdf, generate_combined_label_pdf_direct, generate_combined_label_vertical_pdf_direct, generate_pdf, generate_triple_label_combined

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

@contextlib.contextmanager
def safe_pdf_context(pdf_bytes):
    """Context manager for safe PDF handling"""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        yield doc
    finally:
        doc.close()

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

def packing_plan_tool():
    st.title("📦 Packing Plan Generator (Original Orders + Physical Packing)")
    admin_logged_in, _, BARCODE_PDF_PATH, _ = sidebar_controls()

    # Load master data from Google Sheets or Excel backup
    master_df = load_master_data()
    if master_df is None:
        st.stop()
        return

    # Clean column names
    master_df.columns = master_df.columns.str.strip()
    logger.info(f"Loaded master data with {len(master_df)} products")

    with st.expander("📋 Preview Master Data"):
        st.dataframe(master_df.head())

    pdf_files = st.file_uploader("📥 Upload One or More Invoice PDFs", type=["pdf"], accept_multiple_files=True)

    def expand_to_physical(df, master_df):
        """Convert ordered items to physical packing plan"""
        physical_rows = []
        missing_products = []
        
        for _, row in df.iterrows():
            try:
                asin = row.get("ASIN", "UNKNOWN")
                qty = int(row.get("Qty", 1))
                match_row = master_df[master_df["ASIN"] == asin]
                
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
                                    "ASIN": sub.get("ASIN", asin),
                                    "MRP": sub.get("M.R.P", "N/A"),
                                    "FNSKU": sub_fnsku if not is_empty_value(sub_fnsku) else "MISSING",
                                    "FSSAI": sub.get("FSSAI", "N/A"),
                                    "Packed Today": "",
                                    "Available": "",
                                    "Status": status
                                })
                                split_found = True
                        except Exception as e:
                            logger.error(f"Error processing split variant: {str(e)}")
                    
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
                        "ASIN": asin,
                        "MRP": base.get("M.R.P", "N/A"),
                        "FNSKU": fnsku if not is_empty_value(fnsku) else "MISSING",
                        "FSSAI": base.get("FSSAI", "N/A"),
                        "Packed Today": "",
                        "Available": "",
                        "Status": status
                    })
            except Exception as e:
                logger.error(f"Error processing row {asin}: {str(e)}")
                continue

        df_physical = pd.DataFrame(physical_rows)
        
        # Debug information
        logger.info(f"Generated {len(physical_rows)} physical rows")
        logger.info(f"Missing products: {len(missing_products)}")
        
        if not df_physical.empty:
            try:
                # Group by all columns except Qty to sum quantities for identical items
                df_physical = df_physical.groupby(
                    ["item", "weight", "Packet Size", "ASIN", "MRP", "FNSKU", "FSSAI", "Packed Today", "Available", "Status"],
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

    if pdf_files:
        logger.info(f"Processing {len(pdf_files)} PDF files")
        
        # Validate files first
        for pdf_file in pdf_files:
            is_valid, message = validate_uploaded_file(pdf_file)
            if not is_valid:
                st.error(f"File {pdf_file.name}: {message}")
                return

        with st.spinner("🔍 Processing invoices..."):
            asin_qty_data = defaultdict(int)
            highlighted_pdfs = {}
            
            # Improved ASIN pattern
            asin_pattern = re.compile(r"\b(B[0-9A-Z]{9})\b")
            qty_pattern = re.compile(r"\bQty\b.*?(\d+)")
            price_qty_pattern = re.compile(r"₹[\d,.]+\s+(\d+)\s+₹[\d,.]+")

            for uploaded_file in pdf_files:
                try:
                    pdf_name = uploaded_file.name
                    pdf_bytes = uploaded_file.read()
                    
                    with safe_pdf_context(pdf_bytes) as doc:
                        pages_text = [page.get_text().split("\n") for page in doc]

                        for lines in pages_text:
                            for i, line in enumerate(lines):
                                asin_match = asin_pattern.search(line)
                                if asin_match:
                                    asin = asin_match.group(1)
                                    qty = 1
                                    # IMPROVED: Look for quantity in next 6 lines (was 4)
                                    search_range = min(i + 6, len(lines))
                                    for j in range(i, search_range):
                                        line = lines[j]
                                        
                                        # Pattern 1: Original Qty pattern
                                        match = qty_pattern.search(line)
                                        if match:
                                            qty = int(match.group(1))
                                            logger.info(f"Found qty {qty} using Qty pattern: {line.strip()}")
                                            break
                                        
                                        # Pattern 2: Original price pattern  
                                        match = price_qty_pattern.search(line)
                                        if match:
                                            qty = int(match.group(1))
                                            logger.info(f"Found qty {qty} using price pattern: {line.strip()}")
                                            break
                                        
                                        # Pattern 3: NEW - Multi-item pattern like "3 ₹2,768.67 5% IGST"
                                        multi_item_match = re.search(r'^(\d+)\s+₹[\d,]+\.?\d*\s+\d+%?\s*(IGST|CGST|SGST)', line.strip())
                                        if multi_item_match:
                                            potential_qty = int(multi_item_match.group(1))
                                            if 1 <= potential_qty <= 100:
                                                qty = potential_qty
                                                logger.info(f"Found qty {qty} using multi-item pattern: {line.strip()}")
                                                break
                                        
                                        # Pattern 4: NEW - Standalone number followed by price (but not tax %)
                                        standalone_match = re.search(r'^(\d+)', line.strip())
                                        if standalone_match:
                                            potential_qty = int(standalone_match.group(1))
                                            # Avoid tax percentages and ensure it's reasonable quantity
                                            if (1 <= potential_qty <= 100 and 
                                                not re.search(r'^' + str(potential_qty) + r'%', line.strip()) and
                                                not re.search(r'HSN:', line) and
                                                re.search(r'₹[\d,]+\.?\d*', line)):
                                                qty = potential_qty
                                                logger.info(f"Found qty {qty} using standalone pattern: {line.strip()}")
                                                break
                                    
                                    asin_qty_data[asin] += qty

                    # Generate highlighted PDF
                    highlighted = highlight_large_qty(pdf_bytes)
                    if highlighted:
                        highlighted_pdfs[pdf_name] = highlighted
                        
                except Exception as e:
                    logger.error(f"Error processing {uploaded_file.name}: {str(e)}")
                    st.warning(f"Could not process {uploaded_file.name}: {str(e)}")

            if not asin_qty_data:
                st.warning("No ASIN codes found in the uploaded PDFs. Please check the file format.")
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
            for col in ["item", "weight", "Packet Size", "ASIN", "MRP", "FNSKU", "FSSAI"]:
                if col in df_orders.columns:
                    available_columns.append(col)
            
            df_orders = df_orders[available_columns]

            df_physical, missing_products = expand_to_physical(df_orders, master_df)

            st.success("✅ Packing plan generated!")

            # Show alerts for missing products
            if missing_products:
                st.error("⚠️ **ATTENTION: Some products have issues!**")
                with st.expander("🚨 View Missing/Problem Products", expanded=True):
                    for issue in missing_products:
                        st.warning(f"**ASIN:** {issue.get('ASIN', 'Unknown')} - **Issue:** {issue.get('Issue', 'Unknown')} - **Qty:** {issue.get('Qty', 0)}")
                        if 'Product' in issue:
                            st.write(f"Product: {issue['Product']}")
                        if 'Split Info' in issue:
                            st.write(f"Split Info: {issue['Split Info']}")

            st.subheader("📦 Original Ordered Items (from Invoice)")
            st.dataframe(df_orders, use_container_width=True)

            st.subheader("📦 Actual Physical Packing Plan (after split)")
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
                    st.dataframe(df_physical.style.apply(highlight_status, axis=1), use_container_width=True)
                except:
                    # Fallback without styling
                    st.dataframe(df_physical, use_container_width=True)
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

            # PDF and Excel downloads
            if not df_physical.empty:
                try:
                    summary_pdf = generate_summary_pdf(df_orders, df_physical, missing_products)
                    if summary_pdf:
                        st.download_button("📥 Download Packing Plan PDF", data=summary_pdf, file_name="Packing_Plan.pdf", mime="application/pdf")
                    else:
                        st.warning("Could not generate PDF. Try downloading Excel instead.")
                except Exception as e:
                    st.error(f"Error generating PDF: {str(e)}")
                    st.info("PDF generation failed, but you can still download the Excel file below.")

                # Excel export
                try:
                    excel_buffer = BytesIO()
                    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                        df_physical.to_excel(writer, index=False, sheet_name="Physical Packing Plan")
                        df_orders.to_excel(writer, index=False, sheet_name="Original Orders")
                        if missing_products:
                            pd.DataFrame(missing_products).to_excel(writer, index=False, sheet_name="Missing Products")
                    excel_buffer.seek(0)
                    st.download_button("📊 Download Excel (All Data)", data=excel_buffer, file_name="Packing_Plan.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                except Exception as e:
                    st.error(f"Error generating Excel file: {str(e)}")

            # Highlighted PDFs
            if highlighted_pdfs:
                st.markdown("### 🔍 Highlighted Invoices")
                for name, buf in highlighted_pdfs.items():
                    if buf:
                        st.download_button(f"📄 {name}", data=buf, file_name=f"highlighted_{name}", mime="application/pdf")

            # Label generation section
            st.markdown("### 🧾 Combined MRP + Barcode Labels")
            if not os.path.exists(BARCODE_PDF_PATH):
                st.warning("Barcode PDF not found. Upload it via sidebar.")
            else:
                try:
                    # Test if barcode PDF can be opened
                    with safe_pdf_context(open(BARCODE_PDF_PATH, 'rb').read()) as test_doc:
                        pass
                except Exception as e:
                    st.error(f"Error opening barcode PDF: {e}")
                    return

                if not df_physical.empty:
                    # Add method selection
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        label_method = st.radio(
                            "🔧 Choose Generation Method:",
                            ["PDF-Based (Current)", "Direct Generation (NEW)"],
                            index=0,
                            help="PDF-Based: Uses existing barcode PDF | Direct: Generates barcodes automatically"
                        )
                    
                    with col2:
                        label_orientation = st.radio(
                            "🔄 Choose Label Orientation:",
                            ["Horizontal (96mm × 25mm)"],
                            index=0,
                            help="Horizontal: Side-by-side layout"
                        )
                    
                    # Show method info
                    if "Direct" in label_method:
                        st.info("🆕 **Direct Generation**: Generates Code 128 barcodes automatically from FNSKU codes - no PDF file needed!")
                    else:
                        st.info("🗂️ **PDF-Based**: Uses existing barcode PDF file uploaded via sidebar.")
                    
                    try:
                        combined_pdf = fitz.open()
                        labels_generated = 0
                        
                        for _, row in df_physical.iterrows():
                            fnsku = str(row.get('FNSKU', '')).strip()
                            qty = int(row.get('Qty', 0))
                            
                            if fnsku and fnsku != "MISSING" and not is_empty_value(fnsku):
                                for _ in range(qty):
                                    try:
                                        # Choose function based on method
                                        if "Direct" in label_method:
                                            # Direct generation method
                                            label_pdf = generate_combined_label_pdf_direct(pd.DataFrame([row]), fnsku)
                                        else:
                                            # PDF-based method
                                            label_pdf = generate_combined_label_pdf(pd.DataFrame([row]), fnsku, BARCODE_PDF_PATH)
                                        
                                        if label_pdf:
                                            with safe_pdf_context(label_pdf.read()) as label_doc:
                                                combined_pdf.insert_pdf(label_doc)
                                            labels_generated += 1
                                    except Exception as e:
                                        logger.warning(f"Could not generate label for FNSKU {fnsku}: {e}")

                        if len(combined_pdf) > 0:
                            label_buf = BytesIO()
                            combined_pdf.save(label_buf)
                            label_buf.seek(0)
                            
                            # Dynamic filename based on method
                            method_suffix = "Direct" if "Direct" in label_method else "PDF"
                            filename = f"All_Combined_Labels_{method_suffix}.pdf"
                            
                            st.download_button(
                                f"📥 Download All Combined Labels ({method_suffix})", 
                                data=label_buf, 
                                file_name=filename, 
                                mime="application/pdf"
                            )
                            st.success(f"✅ Generated {labels_generated} horizontal labels using {method_suffix} method!")
                        else:
                            if "Direct" in label_method:
                                st.warning("⚠️ No labels could be generated using direct method. Check if python-barcode is installed.")
                            else:
                                st.warning("⚠️ No labels could be generated using PDF method. Check if products have valid FNSKUs.")
                        
                        combined_pdf.close()
                    except Exception as e:
                        st.error(f"Error generating combined labels: {str(e)}")
                else:
                    st.info("ℹ️ No labels to generate - no valid physical packing plan.")

            # MRP-only labels section
            st.markdown("### 🧾 MRP-Only Labels for Non-FNSKU Items")
            if not df_physical.empty:
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
                            st.download_button("📥 Download MRP-Only Labels", data=buf, file_name="MRP_Only_Labels.pdf", mime="application/pdf")
                            st.success(f"✅ Generated {mrp_only_count} MRP-only labels for non-FNSKU items.")
                        else:
                            st.warning("⚠️ No MRP-only labels could be generated.")
                        
                        mrp_only_pdf.close()
                    else:
                        st.info("ℹ️ All items have valid FNSKUs. No separate MRP-only labels needed.")
                except Exception as e:
                    st.error(f"Error generating MRP-only labels: {str(e)}")

            # Triple Label Generator (50×100mm) button - MOVED TO BOTTOM
            st.markdown("---")
            st.markdown("### 🏷️ Triple Label Generator (50×100mm)")
            
            if not df_physical.empty:
                # Load nutrition data for triple labels
                try:
                    from app.data_loader import load_nutrition_data_silent
                    nutrition_df = load_nutrition_data_silent()
                    
                    if nutrition_df is not None and not nutrition_df.empty:
                        # Add method selection for triple labels
                        triple_label_method = st.radio(
                            "🔧 Choose Triple Label Generation Method:",
                            ["PDF-Based (Default)", "Direct Generation"],
                            index=0,
                            help="PDF-Based: Uses existing barcode PDF | Direct: Generates barcodes automatically"
                        )
                        
                        if st.button("🎯 **Generate Triple Labels (50×100mm)**"):  # Removed type="primary" for white color
                            try:
                                # Create progress bar
                                progress_bar = st.progress(0)
                                status_text = st.empty()
                                
                                # Get unique products with valid FNSKUs from physical plan
                                valid_products = df_physical[
                                    (~df_physical["FNSKU"].isin(["", "MISSING", "nan", "None"])) & 
                                    (~df_physical["FNSKU"].isna())
                                ].copy()
                                
                                if not valid_products.empty:
                                    # Combine all triple labels into one PDF
                                    combined_triple_pdf = fitz.open()
                                    total_labels = 0
                                    total_products = len(valid_products)
                                    
                                    for idx, (_, row) in enumerate(valid_products.iterrows()):
                                        try:
                                            # Update progress
                                            progress = (idx + 1) / total_products
                                            progress_bar.progress(progress)
                                            status_text.text(f"Generating triple label for: {row.get('item', 'Unknown')} ({idx + 1}/{total_products})")
                                            
                                            # Find nutrition data for this product
                                            product_name = str(row.get("item", "")).strip()
                                            nutrition_row = None
                                            
                                            # Try to match by product name
                                            if product_name:
                                                nutrition_matches = nutrition_df[
                                                    nutrition_df["Product"].str.contains(product_name, case=False, na=False)
                                                ]
                                                if not nutrition_matches.empty:
                                                    nutrition_row = nutrition_matches.iloc[0]
                                            
                                            if nutrition_row is None:
                                                # Try alternate matching strategies
                                                for col in ["Product", "item"]:
                                                    if col in nutrition_df.columns:
                                                        exact_match = nutrition_df[nutrition_df[col] == product_name]
                                                        if not exact_match.empty:
                                                            nutrition_row = exact_match.iloc[0]
                                                            break
                                            
                                            if nutrition_row is None:
                                                logger.warning(f"No nutrition data found for product: {product_name}")
                                                continue
                                            
                                            # Create master_df for this product
                                            master_df_single = pd.DataFrame([row])
                                            
                                            # Generate triple label for each quantity
                                            qty = int(row.get("Qty", 1))
                                            for q in range(qty):
                                                try:
                                                    # Choose method based on user selection
                                                    method_param = "direct" if "Direct" in triple_label_method else "pdf"
                                                    triple_label_pdf = generate_triple_label_combined(
                                                        master_df_single, nutrition_row, product_name, method=method_param
                                                    )
                                                    
                                                    if triple_label_pdf:
                                                        # Add to combined PDF
                                                        with safe_pdf_context(triple_label_pdf.read()) as label_doc:
                                                            combined_triple_pdf.insert_pdf(label_doc)
                                                        total_labels += 1
                                                    else:
                                                        logger.warning(f"Failed to generate triple label for {product_name} (copy {q+1})")
                                                        
                                                except Exception as e:
                                                    logger.error(f"Error generating triple label copy {q+1} for {product_name}: {str(e)}")
                                                    continue
                                                    
                                        except Exception as e:
                                            logger.error(f"Error processing product {product_name}: {str(e)}")
                                            continue
                                    
                                    # Finalize and provide download
                                    progress_bar.progress(1.0)
                                    status_text.text("Finalizing PDF...")
                                    
                                    if len(combined_triple_pdf) > 0:
                                        # Save combined PDF
                                        triple_buffer = BytesIO()
                                        combined_triple_pdf.save(triple_buffer)
                                        triple_buffer.seek(0)
                                        
                                        # Clear progress indicators
                                        progress_bar.empty()
                                        status_text.empty()
                                        
                                        # Generate filename and button text based on method
                                        triple_method_suffix = "Direct" if "Direct" in triple_label_method else "PDF"
                                        
                                        # Provide download button
                                        st.download_button(
                                            f"📥 **Download Triple Labels PDF (50×100mm) - {triple_method_suffix}**",
                                            data=triple_buffer,
                                            file_name=f"Triple_Labels_50x100mm_{triple_method_suffix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                                            mime="application/pdf"
                                        )
                                        
                                        st.success(f"✅ Successfully generated {total_labels} triple labels (50×100mm) using {triple_method_suffix} method from {len(valid_products)} products!")
                                        
                                    else:
                                        progress_bar.empty()
                                        status_text.empty()
                                        st.warning("⚠️ No triple labels could be generated. Check if products have nutrition data and valid FNSKUs.")
                                    
                                    combined_triple_pdf.close()
                                    
                                else:
                                    st.info("ℹ️ No valid products with FNSKUs found for triple label generation.")
                                    
                            except Exception as e:
                                st.error(f"Error generating triple labels: {str(e)}")
                                logger.error(f"Triple label generation error: {str(e)}")
                                
                    else:
                        st.warning("⚠️ Nutrition data not available. Please ensure nutrition data is loaded in the system.")
                        st.info("Triple labels require nutrition information to generate ingredients and nutrition facts sections.")
                        
                except Exception as e:
                    st.error(f"Error loading nutrition data: {str(e)}")
                    logger.error(f"Nutrition data loading error: {str(e)}")
            else:
                st.info("ℹ️ No physical packing plan available for triple label generation.")
