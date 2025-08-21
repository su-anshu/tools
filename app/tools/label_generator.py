import streamlit as st
import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import mm
from reportlab.lib.utils import ImageReader
from io import BytesIO
from datetime import datetime
from dateutil.relativedelta import relativedelta
import random
import os
import fitz
from PIL import Image
import re
import contextlib
import logging
from app.sidebar import sidebar_controls, load_master_data, MASTER_FILE, BARCODE_PDF_PATH
from app.tools.label_components.ingredients import IngredientsAllergenLabel
from app.tools.label_components.nutritional import NutritionLabel, load_nutrition_data
from app.data_loader import load_nutrition_data_silent

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- CONFIG ---
LABEL_WIDTH = 48 * mm
LABEL_HEIGHT = 25 * mm

# Utility functions
def is_empty_value(value):
    """Standardized check for empty/invalid values"""
    if pd.isna(value):
        return True
    if value is None:
        return True
    str_value = str(value).strip().lower()
    return str_value in ["", "nan", "none", "null", "n/a"]


def parse_expiry_value(expiry_value, reference_date=None):
    """Parse expiry value from the master sheet into a relativedelta or absolute date.

    Supported formats:
    - integer or numeric string: interpreted as months
    - strings containing 'month', 'months', 'mo', 'm' -> extract months
    - strings containing 'day', 'days', 'd' -> extract days
    - ISO-like date strings (YYYY-MM-DD, DD/MM/YYYY, etc.) -> parsed to datetime

    Returns:
    - ('rel', relativedelta) when an offset should be applied
    - ('date', datetime) when expiry is an absolute date
    - (None, None) when parsing failed
    """
    from dateutil.parser import parse as dateparse
    if reference_date is None:
        reference_date = datetime.today()

    if expiry_value is None:
        return None, None

    try:
        # Normalize
        if isinstance(expiry_value, (int, float)) and not isinstance(expiry_value, bool):
            # Treat numeric as months
            months = int(expiry_value)
            return 'rel', relativedelta(months=months)

        s = str(expiry_value).strip()
        if s == "":
            return None, None

        # Pure number in string -> months
        if re.fullmatch(r"\d+", s):
            return 'rel', relativedelta(months=int(s))

        # Patterns like '2 months', '3 mo', '90 days'
        m = re.search(r"(\d+)\s*(months|month|mos|mo|m)\b", s, flags=re.I)
        if m:
            return 'rel', relativedelta(months=int(m.group(1)))

        d = re.search(r"(\d+)\s*(days|day|d)\b", s, flags=re.I)
        if d:
            return 'rel', relativedelta(days=int(d.group(1)))

        # If string looks like a date, try parse
        # dateutil.parse is forgiving and will accept many formats
        try:
            dt = dateparse(s, dayfirst=False, yearfirst=False)
            # If parsed date is before reference_date, assume year-less string like '21 Aug' -> pick next occurrence
            if dt.year == reference_date.year and dt < reference_date:
                # try to bump year
                dt = dt.replace(year=reference_date.year + 1)
            return 'date', dt
        except Exception:
            pass

    except Exception:
        return None, None

    return None, None

@contextlib.contextmanager
def safe_pdf_context(pdf_bytes):
    """Context manager for safe PDF handling"""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        yield doc
    finally:
        doc.close()

def generate_fnsku_barcode_direct(fnsku_code, width_mm=48, height_mm=25):
    """Generate Code 128A barcode directly from FNSKU code - AMAZON STANDARD
    
    Args:
        fnsku_code: The FNSKU code to generate barcode for
        width_mm: Target width in millimeters  
        height_mm: Target height in millimeters
        
    Returns:
        BytesIO buffer with barcode PDF matching original PDF proportions or None if error
    """
    try:
        from barcode import Code128
        from barcode.writer import ImageWriter
        from PIL import Image, ImageDraw, ImageFont
        import io
        
        logger.info(f"Generating Code 128A barcode for FNSKU: {fnsku_code}")
        
        # Create Code 128A barcode (Amazon standard)
        code128 = Code128(fnsku_code, writer=ImageWriter())
        
        # Generate barcode with specific options for proper sizing
        barcode_buffer = io.BytesIO()
        
        # Custom writer options for ULTRA-CRISP barcode quality
        writer_options = {
            'module_width': 0.12,   # Even thinner bars for high-DPI clarity (was 0.12)
            'module_height': 5.5,   # Taller for better definition at high DPI (was 5.5)  
            'quiet_zone': 0.3,      # Tighter margins for high resolution (was 0.5)
            'font_size': 4.5,         # Larger font for clarity at high DPI (was 5)
            'text_distance': 3,     # Better spacing for high DPI (was 4)
            'background': 'white',
            'foreground': 'black',
            'dpi': 1200            # Explicit high DPI for barcode generation
        }
        
        # Add font path if available
        try:
            if os.path.exists('fonts/Helvetica.ttf'):
                writer_options['font_path'] = 'fonts/Helvetica.ttf'
        except:
            pass
        
        # Generate with custom options for ULTRA-HIGH quality
        barcode_img = code128.write(barcode_buffer, options=writer_options)
        barcode_buffer.seek(0)
        
        # Open as PIL Image with high quality settings
        barcode_pil = Image.open(barcode_buffer)
        
        # Ensure barcode is in RGB mode for better quality
        if barcode_pil.mode != 'RGB':
            barcode_pil = barcode_pil.convert('RGB')
        
        # Create a properly sized canvas with HIGH RESOLUTION for crisp barcodes
        dpi = 1200  # Ultra-high DPI for crystal clear barcodes (was 600)
        canvas_width_px = int((width_mm / 25.4) * dpi * 0.85)    # 85% canvas - less white space
        canvas_height_px = int((height_mm / 25.4) * dpi * 0.85)  # 85% canvas - less white space
        
        # Create white background canvas with anti-aliasing support
        final_img = Image.new('RGB', (canvas_width_px, canvas_height_px), 'white')
        
        # Calculate barcode size to EXACTLY match original proportions
        barcode_target_width = int(canvas_width_px * 0.80)   # 80% width - smaller size
        barcode_target_height = int(canvas_height_px * 0.70) # 70% height - smaller size
        
        # Resize barcode with HIGH-QUALITY resampling for crystal clear result
        barcode_resized = barcode_pil.resize((barcode_target_width, barcode_target_height), Image.Resampling.LANCZOS)
        
        # Center the barcode on canvas properly
        x_offset = (canvas_width_px - barcode_target_width) // 2     # Perfect center horizontally
        y_offset = (canvas_height_px - barcode_target_height) // 2   # Perfect center vertically
        
        # Paste barcode onto canvas
        final_img.paste(barcode_resized, (x_offset, y_offset))
        
        # Convert final image to PDF using ReportLab
        pdf_buffer = BytesIO()
        c = canvas.Canvas(pdf_buffer, pagesize=(width_mm * mm, height_mm * mm))
        
        # Convert final image to format for ReportLab with MAXIMUM quality
        img_buffer = BytesIO()
        final_img.save(img_buffer, format='PNG', dpi=(1200, 1200), optimize=False)
        img_buffer.seek(0)
        
        c.drawImage(ImageReader(img_buffer), 0, 0, width=width_mm * mm, height=height_mm * mm)
        c.showPage()
        c.save()
        
        pdf_buffer.seek(0)
        logger.info(f"Successfully generated Code 128A barcode for {fnsku_code}")
        return pdf_buffer
        
    except ImportError:
        logger.error("python-barcode library not installed. Run: pip install python-barcode[images]")
        return None
    except Exception as e:
        logger.error(f"Error generating Code 128A barcode for {fnsku_code}: {str(e)}")
        return None

# --- Exportable Functions for Use in Other Tools ---
def generate_pdf(dataframe):
    """Generate MRP labels with improved error handling"""
    try:
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=(LABEL_WIDTH, LABEL_HEIGHT))
        today = datetime.today()
        mfg_date = today.strftime('%d %b %Y').upper()
        date_code = today.strftime('%d%m%y')

        for _, row in dataframe.iterrows():
            # Safe data extraction
            name = str(row.get('Name') or row.get('item', 'Unknown Product'))
            weight = str(row.get('Net Weight') or row.get('weight', 'N/A'))
            
            # Safer MRP conversion
            try:
                mrp_value = row.get('M.R.P') or row.get('MRP')
                if is_empty_value(mrp_value):
                    mrp = "INR N/A"
                else:
                    mrp = f"INR {int(float(mrp_value))}"
            except (ValueError, TypeError, AttributeError):
                mrp = "INR N/A"
            
            # Safer FSSAI conversion
            try:
                fssai_value = row.get('M.F.G. FSSAI') or row.get('FSSAI', '')
                if is_empty_value(fssai_value):
                    fssai = "N/A"
                else:
                    fssai = str(int(float(fssai_value)))
            except (ValueError, TypeError, AttributeError):
                fssai = "N/A"
            
            # Generate batch code
            try:
                product_prefix = ''.join(filter(str.isalnum, name.upper()))[:2]
                if not product_prefix:
                    product_prefix = "XX"
                batch_code = f"{product_prefix}{date_code}{str(random.randint(1, 999)).zfill(3)}"
            except Exception:
                batch_code = f"XX{date_code}001"

            # Draw label content
            try:
                # Compute per-product use_by based on Expiry column if available
                expiry_candidates = [
                    row.get('Expiry'),
                    row.get('EXPIRY'),
                    row.get('Shelf Life'),
                    row.get('Shelf_Life'),
                    row.get('ShelfLife'),
                    row.get('Expiry Months'),
                    row.get('ShelfLifeMonths'),
                    row.get('L')  # fallback if user used column-letter accidentally
                ]

                parsed_kind = None
                parsed_val = None
                for candidate in expiry_candidates:
                    if not is_empty_value(candidate):
                        parsed_kind, parsed_val = parse_expiry_value(candidate, reference_date=today)
                        if parsed_kind is not None:
                            break

                # Default to 6 months if nothing found or parse failed
                if parsed_kind == 'date' and isinstance(parsed_val, datetime):
                    use_by_dt = parsed_val
                elif parsed_kind == 'rel' and parsed_val is not None:
                    use_by_dt = today + parsed_val
                else:
                    use_by_dt = today + relativedelta(months=6)

                use_by = use_by_dt.strftime('%d %b %Y').upper()

                c.setFont("Helvetica-Bold", 6)
                c.drawString(2 * mm, 22 * mm, f"Name: {name[:30]}")  # Truncate long names
                c.drawString(2 * mm, 18 * mm, f"Net Weight: {weight} Kg")
                c.drawString(2 * mm, 14 * mm, f"M.R.P: {mrp}")
                c.drawString(2 * mm, 10 * mm, f"M.F.G: {mfg_date} | USE BY: {use_by}")
                c.drawString(2 * mm, 6 * mm, f"Batch Code: {batch_code}")
                c.drawString(2 * mm, 2 * mm, f"M.F.G FSSAI: {fssai}")
                c.showPage()
            except Exception as e:
                logger.error(f"Error drawing label content: {str(e)}")
                # Create a basic error label
                c.setFont("Helvetica-Bold", 8)
                c.drawString(2 * mm, 12 * mm, "ERROR GENERATING LABEL")
                c.drawString(2 * mm, 8 * mm, f"Product: {name[:20]}")
                c.showPage()

        c.save()
        buffer.seek(0)
        return buffer
    except Exception as e:
        logger.error(f"Error generating PDF: {str(e)}")
        return None

def extract_fnsku_page(fnsku_code, pdf_path):
    """Extract FNSKU page from barcode PDF with improved error handling"""
    try:
        if not os.path.exists(pdf_path):
            logger.error(f"Barcode PDF not found: {pdf_path}")
            return None
            
        with open(pdf_path, 'rb') as f:
            pdf_bytes = f.read()
            
        with safe_pdf_context(pdf_bytes) as doc:
            for i, page in enumerate(doc):
                try:
                    page_text = page.get_text()
                    if fnsku_code in page_text:
                        single_page_pdf = fitz.open()
                        single_page_pdf.insert_pdf(doc, from_page=i, to_page=i)
                        buffer = BytesIO()
                        single_page_pdf.save(buffer)
                        buffer.seek(0)
                        single_page_pdf.close()
                        return buffer
                except Exception as e:
                    logger.warning(f"Error processing page {i}: {str(e)}")
                    continue
        
        logger.warning(f"FNSKU {fnsku_code} not found in barcode PDF")
        return None
    except Exception as e:
        logger.error(f"Error extracting FNSKU page: {str(e)}")
        return None

def generate_combined_label_pdf(mrp_df, fnsku_code, barcode_pdf_path):
    """Generate combined MRP + barcode label with improved error handling"""
    try:
        buffer = BytesIO()
        
        # Generate MRP label
        mrp_label_buffer = generate_pdf(mrp_df)
        if not mrp_label_buffer:
            logger.error("Failed to generate MRP label")
            return None
        
        # Extract barcode from PDF
        if not os.path.exists(barcode_pdf_path):
            logger.error(f"Barcode PDF not found: {barcode_pdf_path}")
            return None
            
        try:
            with open(barcode_pdf_path, 'rb') as f:
                barcode_pdf_bytes = f.read()
                
            with safe_pdf_context(barcode_pdf_bytes) as doc:
                barcode_pix = None
                for page in doc:
                    try:
                        page_text = page.get_text()
                        if fnsku_code in page_text:
                            barcode_pix = page.get_pixmap(dpi=1200)
                            break
                    except Exception as e:
                        logger.warning(f"Error processing barcode page: {str(e)}")
                        continue
                
                if not barcode_pix:
                    logger.warning(f"FNSKU {fnsku_code} not found in barcode PDF")
                    return None
        except Exception as e:
            logger.error(f"Error opening barcode PDF: {str(e)}")
            return None

        try:
            # Convert PDFs to images
            with safe_pdf_context(mrp_label_buffer.read()) as mrp_pdf:
                mrp_pix = mrp_pdf[0].get_pixmap(dpi=1200)
            
            mrp_img = Image.open(BytesIO(mrp_pix.tobytes("png")))
            barcode_img = Image.open(BytesIO(barcode_pix.tobytes("png")))
        except Exception as e:
            logger.error(f"Error converting to images: {str(e)}")
            return None

        try:
            # Create combined label (horizontal: 96mm x 25mm)
            c = canvas.Canvas(buffer, pagesize=(96 * mm, 25 * mm))
            c.drawImage(ImageReader(mrp_img), 0, 0, width=48 * mm, height=25 * mm)
            c.drawImage(ImageReader(barcode_img), 48 * mm, 0, width=48 * mm, height=25 * mm)
            c.showPage()
            c.save()
            buffer.seek(0)
            return buffer
        except Exception as e:
            logger.error(f"Error creating combined label: {str(e)}")
            return None
            
    except Exception as e:
        logger.error(f"Unexpected error in generate_combined_label_pdf: {str(e)}")
        return None

def generate_combined_label_vertical_pdf(mrp_df, fnsku_code, barcode_pdf_path):
    """Generate vertical combined MRP + barcode label (50mm x 50mm) - EXPORTABLE FUNCTION
    
    Args:
        mrp_df: DataFrame with product MRP data
        fnsku_code: FNSKU code to extract from barcode PDF
        barcode_pdf_path: Path to master barcode PDF file
        
    Returns:
        BytesIO buffer with vertical combined label PDF (50mm x 50mm) or None if error
    """
    try:
        buffer = BytesIO()
        
        # Generate MRP label
        mrp_label_buffer = generate_pdf(mrp_df)
        if not mrp_label_buffer:
            logger.error("Failed to generate MRP label")
            return None
        
        # Extract barcode from PDF
        if not os.path.exists(barcode_pdf_path):
            logger.error(f"Barcode PDF not found: {barcode_pdf_path}")
            return None
            
        try:
            with open(barcode_pdf_path, 'rb') as f:
                barcode_pdf_bytes = f.read()
                
            with safe_pdf_context(barcode_pdf_bytes) as doc:
                barcode_pix = None
                for page in doc:
                    try:
                        page_text = page.get_text()
                        if fnsku_code in page_text:
                            barcode_pix = page.get_pixmap(dpi=1200)
                            break
                    except Exception as e:
                        logger.warning(f"Error processing barcode page: {str(e)}")
                        continue
                
                if not barcode_pix:
                    logger.warning(f"FNSKU {fnsku_code} not found in barcode PDF")
                    return None
        except Exception as e:
            logger.error(f"Error opening barcode PDF: {str(e)}")
            return None

        try:
            # Convert PDFs to images
            with safe_pdf_context(mrp_label_buffer.read()) as mrp_pdf:
                mrp_pix = mrp_pdf[0].get_pixmap(dpi=1200)
            
            mrp_img = Image.open(BytesIO(mrp_pix.tobytes("png")))
            barcode_img = Image.open(BytesIO(barcode_pix.tobytes("png")))
        except Exception as e:
            logger.error(f"Error converting to images: {str(e)}")
            return None

        try:
            # Create vertical combined label (50mm x 40mm - more compact)
            c = canvas.Canvas(buffer, pagesize=(50 * mm, 42 * mm))
            # MRP label on top (maintains aspect ratio)
            c.drawImage(ImageReader(mrp_img), 0, 20 * mm, width=50 * mm, height=21 * mm)
            # Barcode on bottom (maintains aspect ratio)
            c.drawImage(ImageReader(barcode_img), 0, 0, width=50 * mm, height=20 * mm)
            c.showPage()
            c.save()
            buffer.seek(0)
            return buffer
        except Exception as e:
            logger.error(f"Error creating vertical combined label: {str(e)}")
            return None
            
    except Exception as e:
        logger.error(f"Unexpected error in generate_combined_label_vertical_pdf: {str(e)}")
        return None

# --- NEW DIRECT BARCODE GENERATION FUNCTIONS ---
def generate_combined_label_pdf_direct(mrp_df, fnsku_code):
    """Generate horizontal combined MRP + barcode label using DIRECT Code 128A generation
    
    Args:
        mrp_df: DataFrame with product MRP data
        fnsku_code: FNSKU code to generate barcode for
        
    Returns:
        BytesIO buffer with horizontal combined label PDF (96mm x 25mm) or None if error
    """
    try:
        buffer = BytesIO()
        
        # Generate MRP label
        mrp_label_buffer = generate_pdf(mrp_df)
        if not mrp_label_buffer:
            logger.error("Failed to generate MRP label for direct method")
            return None
        
        # Generate Code 128A barcode directly
        barcode_buffer = generate_fnsku_barcode_direct(fnsku_code, 48, 25)
        if not barcode_buffer:
            logger.error(f"Failed to generate Code 128A barcode for {fnsku_code}")
            return None
        
        try:
            # Convert both to images
            with safe_pdf_context(mrp_label_buffer.read()) as mrp_pdf:
                mrp_pix = mrp_pdf[0].get_pixmap(dpi=1200)
            
            with safe_pdf_context(barcode_buffer.read()) as barcode_pdf:
                barcode_pix = barcode_pdf[0].get_pixmap(dpi=1200)
            
            mrp_img = Image.open(BytesIO(mrp_pix.tobytes("png")))
            barcode_img = Image.open(BytesIO(barcode_pix.tobytes("png")))
        except Exception as e:
            logger.error(f"Error converting direct method to images: {str(e)}")
            return None

        try:
            # Create horizontal combined label (96mm x 25mm)
            c = canvas.Canvas(buffer, pagesize=(96 * mm, 25 * mm))
            c.drawImage(ImageReader(mrp_img), 0, 0, width=48 * mm, height=25 * mm)
            c.drawImage(ImageReader(barcode_img), 48 * mm, 0, width=48 * mm, height=25 * mm)
            c.showPage()
            c.save()
            buffer.seek(0)
            return buffer
        except Exception as e:
            logger.error(f"Error creating direct horizontal combined label: {str(e)}")
            return None
            
    except Exception as e:
        logger.error(f"Unexpected error in generate_combined_label_pdf_direct: {str(e)}")
        return None

def generate_combined_label_vertical_pdf_direct(mrp_df, fnsku_code):
    """Generate vertical combined MRP + barcode label using DIRECT Code 128A generation
    
    Args:
        mrp_df: DataFrame with product MRP data
        fnsku_code: FNSKU code to generate barcode for
        
    Returns:
        BytesIO buffer with vertical combined label PDF (50mm x 40mm) or None if error
    """
    try:
        buffer = BytesIO()
        
        # Generate MRP label
        mrp_label_buffer = generate_pdf(mrp_df)
        if not mrp_label_buffer:
            logger.error("Failed to generate MRP label for direct vertical method")
            return None
        
        # Generate Code 128A barcode directly
        barcode_buffer = generate_fnsku_barcode_direct(fnsku_code, 50, 25)
        if not barcode_buffer:
            logger.error(f"Failed to generate Code 128A barcode for vertical {fnsku_code}")
            return None
        
        try:
            # Convert both to images
            with safe_pdf_context(mrp_label_buffer.read()) as mrp_pdf:
                mrp_pix = mrp_pdf[0].get_pixmap(dpi=1200)
            
            with safe_pdf_context(barcode_buffer.read()) as barcode_pdf:
                barcode_pix = barcode_pdf[0].get_pixmap(dpi=1200)
            
            mrp_img = Image.open(BytesIO(mrp_pix.tobytes("png")))
            barcode_img = Image.open(BytesIO(barcode_pix.tobytes("png")))
        except Exception as e:
            logger.error(f"Error converting direct vertical method to images: {str(e)}")
            return None

        try:
            # Create vertical combined label (50mm x 40mm - compact)
            c = canvas.Canvas(buffer, pagesize=(50 * mm, 42 * mm))
            c.drawImage(ImageReader(mrp_img), 0, 20 * mm, width=50 * mm, height=21 * mm)
            c.drawImage(ImageReader(barcode_img), 0, 0, width=50 * mm, height=20 * mm)
            c.showPage()
            c.save()
            buffer.seek(0)
            return buffer
        except Exception as e:
            logger.error(f"Error creating direct vertical combined label: {str(e)}")
            return None
            
    except Exception as e:
        logger.error(f"Unexpected error in generate_combined_label_vertical_pdf_direct: {str(e)}")
        return None

# --- TRIPLE LABEL GENERATION FUNCTIONS ---


def pdf_to_image(pdf_bytes, dpi=1200):
    """Convert PDF bytes to PIL Image"""
    try:
        with safe_pdf_context(pdf_bytes) as doc:
            pix = doc[0].get_pixmap(dpi=dpi)
            return Image.open(BytesIO(pix.tobytes("png")))
    except Exception as e:
        logger.error(f"Error converting PDF to image: {str(e)}")
        return None

def resize_section_to_50mm_width(img, target_height_mm, dpi=1200):
    """Resize section image to 50mm width with target height"""
    try:
        # Convert mm to pixels
        target_width_px = int((50 / 25.4) * dpi)
        target_height_px = int((target_height_mm / 25.4) * dpi)
        
        # Resize image to exact dimensions
        resized_img = img.resize((target_width_px, target_height_px), Image.Resampling.LANCZOS)
        return resized_img
    except Exception as e:
        logger.error(f"Error resizing image: {str(e)}")
        return img

def combine_pdfs_to_triple_label(ingredients_pdf, nutrition_pdf, mrp_barcode_buffer):
    """Combine three PDF sections into 50×100mm layout with proportional white space"""
    try:
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=(50*mm, 100*mm))
        
        # Convert existing PDFs to images
        ingredients_img = pdf_to_image(ingredients_pdf)
        nutrition_img = pdf_to_image(nutrition_pdf) 
        mrp_barcode_img = pdf_to_image(mrp_barcode_buffer.read())
        
        if not all([ingredients_img, nutrition_img, mrp_barcode_img]):
            logger.error("Failed to convert one or more PDFs to images")
            return None
        
        # Resize all sections to 50mm width with target heights
        ingredients_resized = resize_section_to_50mm_width(ingredients_img, 22)  # 22mm height
        nutrition_resized = resize_section_to_50mm_width(nutrition_img, 35)     # 35mm height  
        mrp_barcode_resized = resize_section_to_50mm_width(mrp_barcode_img, 37) # 37mm height
        
        # Draw sections with simple lines between them
        # Section 1: Ingredients (top: 100-1-22 = 77mm)
        c.drawImage(ImageReader(ingredients_resized), 0, 77*mm, width=50*mm, height=22*mm)
        
        # Simple line between ingredients and nutrition
        c.setStrokeColor((0, 0, 0))  # Black color
        c.setLineWidth(1)          # Thin line
        c.line(5*mm, 76*mm, 45*mm, 76*mm)  # Horizontal line with margins
        
        # Section 2: Nutrition (top: 77-2-35 = 40mm)  
        c.drawImage(ImageReader(nutrition_resized), 0, 40*mm, width=50*mm, height=35*mm)
        
        # Simple line between nutrition and MRP+barcode
        c.setStrokeColor((0, 0, 0))  # Black color
        c.setLineWidth(1)          # Thin line
        c.line(5*mm, 39*mm, 45*mm, 39*mm)  # Horizontal line with margins
        
        # Section 3: MRP+Barcode (top: 40-2-37 = 1mm from bottom)
        c.drawImage(ImageReader(mrp_barcode_resized), 0, 1*mm, width=50*mm, height=37*mm)
        
        # 1mm bottom margin (0-1mm)
        
        c.showPage()
        c.save()
        buffer.seek(0)
        return buffer
        
    except Exception as e:
        logger.error(f"Error combining PDFs to triple label: {str(e)}")
        return None

def generate_triple_label_combined(master_df, nutrition_row, product_name, method="direct"):
    """Generate 50×100mm triple label using existing components"""
    try:
        # 1. Ingredients section (reuse existing class)
        ingredients_gen = IngredientsAllergenLabel()
        ingredients_data = {
            "Product": product_name,
            "Ingredients": str(nutrition_row.get("Ingredients", "")),
            "Allergen Info": str(nutrition_row.get("Allergen Info", ""))
        }
        ingredients_pdf = ingredients_gen.create_pdf(ingredients_data)
        
        # 2. Nutrition section (reuse existing class)  
        nutrition_gen = NutritionLabel()
        nutrition_data = {
            "Product": product_name,
            "Serving Size": nutrition_row.get("Serving Size", "30g"),
            "Energy": nutrition_row.get("Energy", 345),
            "Total Fat": nutrition_row.get("Total Fat", 5),
            "Saturated Fat": nutrition_row.get("Saturated Fat", 10),
            "Trans Fat": nutrition_row.get("Trans Fat", 0),
            "Cholesterol": nutrition_row.get("Cholesterol", 0),
            "Sodium(mg)": nutrition_row.get("Sodium(mg)", 2),
            "Total Carbohydrate": nutrition_row.get("Total Carbohydrate", 5),
            "Dietary Fiber": nutrition_row.get("Dietary Fiber", 10),
            "Total Sugars": nutrition_row.get("Total Sugars", 8),
            "Added Sugars": nutrition_row.get("Added Sugars", 2),
            "Protein": nutrition_row.get("Protein", 5)
        }
        nutrition_pdf = nutrition_gen.create_pdf(nutrition_data)
        
        # 3. MRP+Barcode (choose method)
        fnsku = str(master_df.iloc[0].get('FNSKU', '')).strip()
        if is_empty_value(fnsku):
            logger.warning("FNSKU is missing for triple label generation")
            return None
        
        if method == "direct":
            # Use direct generation method
            mrp_barcode_pdf = generate_combined_label_vertical_pdf_direct(master_df, fnsku)
        else:
            # Use PDF method
            mrp_barcode_pdf = generate_combined_label_vertical_pdf(master_df, fnsku, BARCODE_PDF_PATH)
            
        if not mrp_barcode_pdf:
            logger.error(f"Failed to generate MRP+Barcode section using {method} method")
            return None
        
        # 4. Combine into 50×100mm
        return combine_pdfs_to_triple_label(ingredients_pdf, nutrition_pdf, mrp_barcode_pdf)
        
    except Exception as e:
        logger.error(f"Error generating triple label: {str(e)}")
        return None

# --- EXISTING FUNCTIONS CONTINUE BELOW ---
def generate_combined_label_pdf_direct(mrp_df, fnsku_code):
    """Generate horizontal combined MRP + barcode label using DIRECT Code 128A generation
    
    Args:
        mrp_df: DataFrame with product MRP data
        fnsku_code: FNSKU code to generate barcode for
        
    Returns:
        BytesIO buffer with horizontal combined label PDF (96mm x 25mm) or None if error
    """
    try:
        buffer = BytesIO()
        
        # Generate MRP label
        mrp_label_buffer = generate_pdf(mrp_df)
        if not mrp_label_buffer:
            logger.error("Failed to generate MRP label for direct method")
            return None
        
        # Generate Code 128A barcode directly
        barcode_buffer = generate_fnsku_barcode_direct(fnsku_code, 48, 25)
        if not barcode_buffer:
            logger.error(f"Failed to generate Code 128A barcode for {fnsku_code}")
            return None
        
        try:
            # Convert both to images
            with safe_pdf_context(mrp_label_buffer.read()) as mrp_pdf:
                mrp_pix = mrp_pdf[0].get_pixmap(dpi=1200)
            
            with safe_pdf_context(barcode_buffer.read()) as barcode_pdf:
                barcode_pix = barcode_pdf[0].get_pixmap(dpi=1200)
            
            mrp_img = Image.open(BytesIO(mrp_pix.tobytes("png")))
            barcode_img = Image.open(BytesIO(barcode_pix.tobytes("png")))
        except Exception as e:
            logger.error(f"Error converting direct method to images: {str(e)}")
            return None

        try:
            # Create horizontal combined label (96mm x 25mm)
            c = canvas.Canvas(buffer, pagesize=(96 * mm, 25 * mm))
            c.drawImage(ImageReader(mrp_img), 0, 0, width=48 * mm, height=25 * mm)
            c.drawImage(ImageReader(barcode_img), 48 * mm, 0, width=48 * mm, height=25 * mm)
            c.showPage()
            c.save()
            buffer.seek(0)
            return buffer
        except Exception as e:
            logger.error(f"Error creating direct horizontal combined label: {str(e)}")
            return None
            
    except Exception as e:
        logger.error(f"Unexpected error in generate_combined_label_pdf_direct: {str(e)}")
        return None

def generate_combined_label_vertical_pdf_direct(mrp_df, fnsku_code):
    """Generate vertical combined MRP + barcode label using DIRECT Code 128A generation
    
    Args:
        mrp_df: DataFrame with product MRP data
        fnsku_code: FNSKU code to generate barcode for
        
    Returns:
        BytesIO buffer with vertical combined label PDF (50mm x 40mm) or None if error
    """
    try:
        buffer = BytesIO()
        
        # Generate MRP label
        mrp_label_buffer = generate_pdf(mrp_df)
        if not mrp_label_buffer:
            logger.error("Failed to generate MRP label for direct vertical method")
            return None
        
        # Generate Code 128A barcode directly
        barcode_buffer = generate_fnsku_barcode_direct(fnsku_code, 50, 25)
        if not barcode_buffer:
            logger.error(f"Failed to generate Code 128A barcode for vertical {fnsku_code}")
            return None
        
        try:
            # Convert both to images
            with safe_pdf_context(mrp_label_buffer.read()) as mrp_pdf:
                mrp_pix = mrp_pdf[0].get_pixmap(dpi=1200)
            
            with safe_pdf_context(barcode_buffer.read()) as barcode_pdf:
                barcode_pix = barcode_pdf[0].get_pixmap(dpi=1200)
            
            mrp_img = Image.open(BytesIO(mrp_pix.tobytes("png")))
            barcode_img = Image.open(BytesIO(barcode_pix.tobytes("png")))
        except Exception as e:
            logger.error(f"Error converting direct vertical method to images: {str(e)}")
            return None

        try:
            # Create vertical combined label (50mm x 40mm - compact)
            c = canvas.Canvas(buffer, pagesize=(50 * mm, 42 * mm))
            c.drawImage(ImageReader(mrp_img), 0, 20 * mm, width=50 * mm, height=21 * mm)
            c.drawImage(ImageReader(barcode_img), 0, 0, width=50 * mm, height=20 * mm)
            c.showPage()
            c.save()
            buffer.seek(0)
            return buffer
        except Exception as e:
            logger.error(f"Error creating direct vertical combined label: {str(e)}")
            return None
            
    except Exception as e:
        logger.error(f"Unexpected error in generate_combined_label_vertical_pdf_direct: {str(e)}")
        return None

# --- Main App Logic ---
def label_generator_tool():
    st.title("🔖 MRP Label Generator")
    st.markdown("---")
    
    # Header info section
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        st.caption("Generate 48mm x 25mm labels with MRP, batch code, FSSAI & barcode")
    with col2:
        st.metric("Label Size", "48×25mm")
    with col3:
        st.metric("Quality", "1200 DPI")
    
    admin_logged_in, _, BARCODE_PDF_PATH, _ = sidebar_controls()

    def sanitize_filename(name):
        """Sanitize filename for safe file operations"""
        return re.sub(r'[^\w\-_\.]', '_', str(name))

    # Load and validate data from Google Sheets or Excel backup
    df = load_master_data()
    if df is None:
        st.stop()
        return
    
    if df.empty:
        st.warning("⚠️ Master data file is empty.")
        return
    
    # Clean column names
    df.columns = df.columns.str.strip()
    logger.info(f"Loaded master data with {len(df)} products")
    
    # Check required columns
    required_columns = ['Name']
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        st.error(f"Missing required columns in master file: {missing_columns}")
        return

    try:
        # Product Selection Section
        st.markdown("### 🎯 Product Selection")
        
        # Product selection with error handling
        product_options = []
        if 'Name' in df.columns:
            product_options = sorted(df['Name'].dropna().unique())
        
        if not product_options:
            st.warning("No products found in master file.")
            return
        
        # Two column layout for selection
        col1, col2 = st.columns(2)
        
        with col1:
            selected_product = st.selectbox("📦 Select Product", product_options, key="product_select")
        
        with col2:
            # Weight selection
            weight_options = []
            if 'Net Weight' in df.columns:
                product_df = df[df['Name'] == selected_product]
                weight_options = sorted(product_df['Net Weight'].dropna().unique())
            
            if not weight_options:
                st.warning(f"No weight options found for {selected_product}")
                return
                
            selected_weight = st.selectbox("⚖️ Select Weight", weight_options, key="weight_select")

        # Filter data
        filtered_df = df[
            (df['Name'] == selected_product) & 
            (df['Net Weight'] == selected_weight)
        ]

        # Product Info Display
        if not filtered_df.empty:
            st.markdown("---")
            
            # Product details removed - already available in expandable section below
            
            # Data preview in expandable section
            with st.expander("📋 View Complete Product Data"):
                st.dataframe(filtered_df, use_container_width=True)

            st.markdown("---")
            
            # Label Generation Section
            st.markdown("### 📄 Label Options")
            
            safe_name = sanitize_filename(selected_product)
            
            # MRP Only Label
            with st.container():
                st.markdown("#### 🏷️ MRP Label Only")
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.caption("Basic MRP label with batch code and FSSAI")
                with col2:
                    try:
                        label_pdf = generate_pdf(filtered_df)
                        if label_pdf:
                            st.download_button(
                                "📥 Download", 
                                data=label_pdf, 
                                file_name=f"{safe_name}_MRP_Label.pdf", 
                                mime="application/pdf",
                                use_container_width=True
                            )
                        else:
                            st.error("Failed to generate")
                    except Exception as e:
                        st.error(f"Error: {str(e)}")

            st.markdown("---")

            # Barcode and combined label section
            if 'FNSKU' in filtered_df.columns and os.path.exists(BARCODE_PDF_PATH):
                try:
                    fnsku_code = str(filtered_df.iloc[0]['FNSKU']).strip()
                    
                    if not is_empty_value(fnsku_code):
                        
                        # Combined Labels Section
                        st.markdown("#### 🧾 Combined MRP + Barcode Labels")
                        
                        # Create tabs for different methods
                        tab1, tab2 = st.tabs(["�️ PDF Method (Default)", "� Direct Generation"])
                        
                        with tab1:
                            st.caption("✅ Uses existing barcode PDF file from sidebar")
                            
                            # Extract barcode
                            barcode = extract_fnsku_page(fnsku_code, BARCODE_PDF_PATH)
                            if barcode:
                                col1, col2 = st.columns(2)  # Changed from 3 to 2 columns
                                
                                with col1:
                                    st.markdown("**Barcode Only**")
                                    st.download_button(
                                        "📦 Download", 
                                        data=barcode, 
                                        file_name=f"{fnsku_code}_barcode_pdf.pdf", 
                                        mime="application/pdf",
                                        use_container_width=True
                                    )
                                
                                with col2:
                                    st.markdown("**Horizontal (96×25mm)**")
                                    combined = generate_combined_label_pdf(filtered_df, fnsku_code, BARCODE_PDF_PATH)
                                    if combined:
                                        st.download_button(
                                            "🧾 Download", 
                                            data=combined, 
                                            file_name=f"{safe_name}_Horizontal_PDF.pdf", 
                                            mime="application/pdf",
                                            use_container_width=True
                                        )
                                    else:
                                        st.error("Generation failed")
                            else:
                                st.warning(f"⚠️ FNSKU {fnsku_code} not found in barcode PDF")
                        
                        with tab2:
                            st.caption("Amazon-compliant Code 128A barcodes generated directly")
                            
                            col1, col2 = st.columns(2)  # Changed from 3 to 2 columns
                            
                            # Direct barcode only
                            with col1:
                                st.markdown("**Barcode Only**")
                                direct_barcode = generate_fnsku_barcode_direct(fnsku_code)
                                if direct_barcode:
                                    st.download_button(
                                        "📦 Download", 
                                        data=direct_barcode, 
                                        file_name=f"{fnsku_code}_barcode.pdf", 
                                        mime="application/pdf",
                                        use_container_width=True
                                    )
                                else:
                                    st.error("Generation failed")
                            
                            # Direct horizontal combined
                            with col2:
                                st.markdown("**Horizontal (96×25mm)**")
                                direct_combined_h = generate_combined_label_pdf_direct(filtered_df, fnsku_code)
                                if direct_combined_h:
                                    st.download_button(
                                        "🧾 Download", 
                                        data=direct_combined_h, 
                                        file_name=f"{safe_name}_Horizontal.pdf", 
                                        mime="application/pdf",
                                        use_container_width=True
                                    )
                                else:
                                    st.error("Generation failed")
                        
                        st.markdown("---")
                    else:
                        st.warning("⚠️ FNSKU is missing for this product.")
                except Exception as e:
                    st.error(f"Error processing barcode: {str(e)}")
            else:
                st.info("ℹ️ **Barcode labels unavailable**")
                if 'FNSKU' not in filtered_df.columns:
                    st.caption("• FNSKU column not found in master data")
                elif not os.path.exists(BARCODE_PDF_PATH):
                    st.caption("• Barcode PDF not uploaded via sidebar")
                else:
                    st.caption("• FNSKU missing or barcode PDF not available")

            st.markdown("---")
            
            # Triple Label Generator Section
            with st.container():
                st.markdown("#### 🧾 Triple Label Generator (50×100mm)")
                st.caption("Combines Ingredients + Nutrition + MRP+Barcode into one comprehensive label")
                
                try:
                    # Load nutrition data silently in background
                    with st.spinner("🔄 Loading nutrition data..."):
                        nutrition_df = load_nutrition_data_silent()
                    
                    if nutrition_df is not None:
                        nutrition_match = nutrition_df[nutrition_df['Product'] == selected_product]
                        
                        if nutrition_match.empty:
                            st.warning(f"⚠️ Nutrition data not found for '{selected_product}'")
                            with st.expander("📋 View available products"):
                                available_products = sorted(nutrition_df['Product'].dropna().unique())
                                st.write(", ".join(available_products))
                        else:
                            nutrition_row = nutrition_match.iloc[0]
                            
                            # Status display in cards
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.success("✅ Master Data")
                                st.caption("Product & weight found")
                            with col2:
                                st.success("✅ Nutrition Data") 
                                st.caption("Ingredients & facts available")
                            with col3:
                                fnsku_available = not is_empty_value(str(filtered_df.iloc[0].get('FNSKU', '')))
                                if fnsku_available:
                                    st.success("✅ FNSKU Available")
                                    st.caption("Barcode ready")
                                else:
                                    st.warning("⚠️ FNSKU Missing")
                                    st.caption("No barcode available")
                            
                            # Generation tabs
                            tab1, tab2 = st.tabs(["�️ PDF Method (Default)", "� Direct Generation"])
                            
                            with tab1:
                                st.caption("✅ Uses existing barcode PDF file from sidebar")
                                
                                if os.path.exists(BARCODE_PDF_PATH):
                                    col1, col2 = st.columns([2, 1])
                                    with col1:
                                        st.markdown("**Label Composition:**")
                                        st.write("🥗 Ingredients & Allergens (22mm)")
                                        st.write("📊 Nutritional Facts (35mm)")
                                        st.write("🏷️ MRP + Barcode (37mm)")
                                    
                                    with col2:
                                        if st.button("🧾 Generate Triple Label", key="pdf_triple", use_container_width=True):
                                            with st.spinner("🔄 Generating (PDF)..."):
                                                triple_pdf = generate_triple_label_combined(
                                                    filtered_df, 
                                                    nutrition_row, 
                                                    selected_product,
                                                    method="pdf"
                                                )
                                                
                                                if triple_pdf:
                                                    st.success("✅ Ready!")
                                                    st.download_button(
                                                        "📥 Download Triple Label", 
                                                        data=triple_pdf, 
                                                        file_name=f"{safe_name}_{selected_weight}_Triple_PDF.pdf", 
                                                        mime="application/pdf",
                                                        use_container_width=True,
                                                        key="download_pdf_triple"
                                                    )
                                                else:
                                                    st.error("❌ Generation failed")
                                else:
                                    st.warning("⚠️ Barcode PDF not available")
                                    st.caption("Please upload barcode PDF via sidebar to use this method")
                            
                            with tab2:
                                st.caption("Amazon-compliant Code 128A barcodes generated directly")
                                
                                # Generate button centered
                                if st.button("🧾 Generate Triple Label", key="direct_triple", use_container_width=True):
                                    with st.spinner("🔄 Generating (Direct)..."):
                                        triple_pdf = generate_triple_label_combined(
                                            filtered_df, 
                                            nutrition_row, 
                                            selected_product,
                                            method="direct"
                                        )
                                        
                                        if triple_pdf:
                                            st.success("✅ Ready!")
                                            st.download_button(
                                                "📥 Download Triple Label", 
                                                data=triple_pdf, 
                                                file_name=f"{safe_name}_{selected_weight}_Triple_Direct.pdf", 
                                                mime="application/pdf",
                                                use_container_width=True,
                                                key="download_direct_triple"
                                            )
                                        else:
                                            st.error("❌ Generation failed")
                    else:
                        st.error("❌ Could not load nutrition data")
                        st.caption("Check internet connection")
                        
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
                    logger.error(f"Triple label error: {str(e)}")
        else:
            st.warning("⚠️ No matching data found for selected product and weight.")
            
    except Exception as e:
        logger.error(f"Unexpected error in label generator: {str(e)}")
        st.error(f"❌ An unexpected error occurred: {str(e)}")