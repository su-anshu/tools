import fitz
import re
from collections import defaultdict
import contextlib
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import mm
from reportlab.lib.utils import ImageReader
from PIL import Image

@contextlib.contextmanager
def safe_pdf_context(pdf_bytes):
    """Context manager for safe PDF handling"""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        yield doc
    finally:
        doc.close()

def highlight_large_qty(pdf_bytes):
    """Improved highlighting function for large quantities in PDF invoices"""
    try:
        with safe_pdf_context(pdf_bytes) as doc:
            in_table = False
            highlighted_count = 0

            for page_num, page in enumerate(doc):
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

                    # Exit table when we see TOTAL
                    if "TOTAL" in text.upper():
                        in_table = False

            output_buffer = BytesIO()
            doc.save(output_buffer)
            output_buffer.seek(0)
            return output_buffer
    except Exception as e:
        return None

def pdf_to_image(pdf_bytes, dpi=1200):
    """Convert PDF bytes to PIL Image"""
    try:
        with safe_pdf_context(pdf_bytes) as doc:
            pix = doc[0].get_pixmap(dpi=dpi)
            return Image.open(BytesIO(pix.tobytes("png")))
    except Exception as e:
        return None
