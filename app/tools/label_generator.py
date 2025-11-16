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
import logging
from app.sidebar import MASTER_FILE, BARCODE_PDF_PATH
from app.tools.label_components.ingredients import IngredientsAllergenLabel
from app.tools.label_components.nutritional import NutritionLabel, load_nutrition_data
from app.data_loader import load_nutrition_data_silent
from app.utils import is_empty_value, setup_tool_ui, load_and_validate_master_data, sanitize_filename
from app.pdf_utils import safe_pdf_context

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- CONFIG ---
LABEL_WIDTH = 48 * mm
LABEL_HEIGHT = 25 * mm


def find_allergen_column(nutrition_row):
    """Find allergen column in nutrition data with flexible matching
    
    Tries multiple methods:
    1. Exact match: "Allergen Info"
    2. Case-insensitive partial match: contains "allergen"
    3. Access by position: column D (index 3)
    
    Returns the allergen value or empty string if not found
    """
    # Method 1: Try exact match
    if "Allergen Info" in nutrition_row.index:
        allergen_value = nutrition_row.get("Allergen Info", "")
        if not is_empty_value(allergen_value):
            logger.info("Found allergen info using exact match 'Allergen Info'")
            return str(allergen_value)
    
    # Method 2: Try case-insensitive partial match
    for col in nutrition_row.index:
        if 'allergen' in str(col).lower():
            allergen_value = nutrition_row.get(col, "")
            if not is_empty_value(allergen_value):
                logger.info(f"Found allergen info using column: {col}")
                return str(allergen_value)
    
    # Method 3: Try accessing by position (column D = index 3)
    try:
        if len(nutrition_row.index) > 3:
            allergen_value = nutrition_row.iloc[3]
            column_name = nutrition_row.index[3]
            if not is_empty_value(allergen_value):
                logger.info(f"Found allergen info using column D (index 3): {column_name}")
                return str(allergen_value)
    except (IndexError, KeyError, AttributeError) as e:
        logger.debug(f"Could not access column D by position: {str(e)}")
        pass
    
    # Log available columns for debugging
    logger.warning(f"Allergen column not found. Available columns: {list(nutrition_row.index)}")
    return ""





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

            'dpi': 600            # High DPI for crisp barcodes (optimized from 1200)

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

        dpi = 600  # High DPI for crisp barcodes (optimized from 1200)

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

        final_img.save(img_buffer, format='PNG', dpi=(600, 600), optimize=False)

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

                            barcode_pix = page.get_pixmap(dpi=600)

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

                mrp_pix = mrp_pdf[0].get_pixmap(dpi=600)

            

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

                            barcode_pix = page.get_pixmap(dpi=600)

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

                mrp_pix = mrp_pdf[0].get_pixmap(dpi=600)

            

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

                mrp_pix = mrp_pdf[0].get_pixmap(dpi=600)

            

            with safe_pdf_context(barcode_buffer.read()) as barcode_pdf:

                barcode_pix = barcode_pdf[0].get_pixmap(dpi=600)

            

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

                mrp_pix = mrp_pdf[0].get_pixmap(dpi=600)

            

            with safe_pdf_context(barcode_buffer.read()) as barcode_pdf:

                barcode_pix = barcode_pdf[0].get_pixmap(dpi=600)

            

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





def pdf_to_image(pdf_bytes, dpi=600):

    """Convert PDF bytes to PIL Image"""

    try:

        with safe_pdf_context(pdf_bytes) as doc:

            pix = doc[0].get_pixmap(dpi=dpi)

            return Image.open(BytesIO(pix.tobytes("png")))

    except Exception as e:

        logger.error(f"Error converting PDF to image: {str(e)}")

        return None



def resize_section_to_50mm_width(img, target_height_mm, dpi=600):

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

    """Generate 50×100mm triple label using existing components
    
    Note: The method parameter is kept for backward compatibility but is ignored.
    This function always uses direct barcode generation.
    """

    try:

        # 1. Ingredients section (reuse existing class)

        ingredients_gen = IngredientsAllergenLabel()

        # Find allergen info using flexible column detection
        allergen_info = find_allergen_column(nutrition_row)
        
        # Get ingredients - try flexible matching too
        ingredients = str(nutrition_row.get("Ingredients", ""))
        if is_empty_value(ingredients):
            # Try case-insensitive match
            for col in nutrition_row.index:
                if 'ingredient' in str(col).lower():
                    ingredients = str(nutrition_row.get(col, ""))
                    if not is_empty_value(ingredients):
                        break

        ingredients_data = {

            "Product": product_name,

            "Ingredients": ingredients,

            "Allergen Info": allergen_info

        }
        
        logger.info(f"Allergen info for {product_name}: {allergen_info[:50] if allergen_info else 'EMPTY'}...")

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

        

        # 3. MRP+Barcode (always use direct generation method)

        fnsku = str(master_df.iloc[0].get('FNSKU', '')).strip()

        if is_empty_value(fnsku):

            logger.warning("FNSKU is missing for triple label generation")

            return None

        

        # Always use direct generation method (method parameter kept for backward compatibility)

        mrp_barcode_pdf = generate_combined_label_vertical_pdf_direct(master_df, fnsku)

            

        if not mrp_barcode_pdf:

            logger.error("Failed to generate MRP+Barcode section using direct method")

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

                mrp_pix = mrp_pdf[0].get_pixmap(dpi=600)

            

            with safe_pdf_context(barcode_buffer.read()) as barcode_pdf:

                barcode_pix = barcode_pdf[0].get_pixmap(dpi=600)

            

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

                mrp_pix = mrp_pdf[0].get_pixmap(dpi=600)

            

            with safe_pdf_context(barcode_buffer.read()) as barcode_pdf:

                barcode_pix = barcode_pdf[0].get_pixmap(dpi=600)

            

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
    # Setup UI with CSS
    setup_tool_ui("MRP Label Generator")
    
    # Load and validate master data
    df, admin_logged_in, BARCODE_PDF_PATH = load_and_validate_master_data(
        require_columns=['Name'], 
        return_barcode_path=True
    )
    
    if df.empty:
        st.warning("No data available")
        return



    try:

        col1, col2 = st.columns(2)

        with col1:

            product_options = sorted(df['Name'].dropna().unique()) if 'Name' in df.columns else []

            if not product_options:

                st.warning("No products found")

                return

            selected_product = st.selectbox("Select Product", product_options, key="product_select")

        

        with col2:

            weight_options = []

            if 'Net Weight' in df.columns:

                product_df = df[df['Name'] == selected_product]

                weight_options = sorted(product_df['Net Weight'].dropna().unique())

            if not weight_options:

                st.warning("No weight options")

                return

            selected_weight = st.selectbox("Select Weight", weight_options, key="weight_select")



        # Filter data

        filtered_df = df[

            (df['Name'] == selected_product) & 

            (df['Net Weight'] == selected_weight)

        ]



        if not filtered_df.empty:

            safe_name = sanitize_filename(selected_product)

            

            # MRP and Barcode Labels

            st.markdown("**MRP LABEL**")

            col1, col2 = st.columns(2)

            with col1:

                try:

                    label_pdf = generate_pdf(filtered_df)

                    if label_pdf:

                        st.download_button(

                            "Download MRP Label", 

                            data=label_pdf, 

                            file_name=f"{safe_name}_MRP_Label.pdf", 

                            mime="application/pdf",

                            use_container_width=True

                        )

                    else:

                        st.error("Failed to generate")

                except Exception as e:

                    st.error(f"Error: {str(e)}")

            with col2:

                if 'FNSKU' in filtered_df.columns:

                    try:

                        fnsku_code = str(filtered_df.iloc[0]['FNSKU']).strip()

                        if not is_empty_value(fnsku_code):

                            direct_barcode = generate_fnsku_barcode_direct(fnsku_code)

                            if direct_barcode:

                                st.download_button(

                                    "Download Barcode", 

                                    data=direct_barcode, 

                                    file_name=f"{fnsku_code}_barcode.pdf", 

                                    mime="application/pdf",

                                    use_container_width=True

                                )

                            else:

                                st.error("Failed")

                        else:

                            st.warning("FNSKU missing")

                    except Exception as e:

                        st.error(f"Error: {str(e)}")

                else:

                    st.warning("FNSKU not available")

            # Sticker Label and House Label section

            col1, col2 = st.columns(2)

            with col1:

                # Sticker Label section

                if 'FNSKU' in filtered_df.columns:

                    try:

                        fnsku_code = str(filtered_df.iloc[0]['FNSKU']).strip()

                        if not is_empty_value(fnsku_code):

                            st.markdown("**Sticker Label**")

                            direct_combined_h = generate_combined_label_pdf_direct(filtered_df, fnsku_code)

                            if direct_combined_h:

                                st.download_button(

                                    "Download Combined Label", 

                                    data=direct_combined_h, 

                                    file_name=f"{safe_name}_Horizontal.pdf", 

                                    mime="application/pdf",

                                    use_container_width=True

                                )

                            else:

                                st.error("Failed")

                    except Exception as e:

                        st.error(f"Error: {str(e)}")

            with col2:

                # House Label section

                try:

                    with st.spinner("Loading nutrition data..."):

                        nutrition_df = load_nutrition_data_silent()

                    

                    if nutrition_df is not None:

                        nutrition_match = nutrition_df[nutrition_df['Product'] == selected_product]

                        

                        if nutrition_match.empty:

                            st.warning("Nutrition data not found")

                        else:

                            nutrition_row = nutrition_match.iloc[0]

                            

                            st.markdown("**House Label**")

                            # Generate PDF and show single download button

                            with st.spinner("Generating..."):

                                triple_pdf = generate_triple_label_combined(

                                    filtered_df, 

                                    nutrition_row, 

                                    selected_product

                                )

                                

                                if triple_pdf:

                                    st.download_button(

                                        "Download Triple Label", 

                                        data=triple_pdf, 

                                        file_name=f"{safe_name}_{selected_weight}_Triple.pdf", 

                                        mime="application/pdf",

                                        use_container_width=True,

                                        key="download_triple"

                                    )

                                else:

                                    st.error("Failed")

                    else:

                        st.error("Could not load nutrition data")

                except Exception as e:

                    st.error(f"Error: {str(e)}")

                    logger.error(f"Triple label error: {str(e)}")

        else:

            st.warning("No matching data found")

            

    except Exception as e:

        logger.error(f"Unexpected error in label generator: {str(e)}")

        st.error(f"An unexpected error occurred: {str(e)}")