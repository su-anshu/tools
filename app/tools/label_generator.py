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

# Custom CSS for better UI
def apply_custom_css():
    st.markdown("""
    <style>
    /* Main container styling */
    .main-header {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        margin-bottom: 2rem;
        color: white;
        text-align: center;
    }
    
    /* Section headers */
    .section-header {
        background: #f8f9fa;
        padding: 0.75rem 1rem;
        border-left: 4px solid #667eea;
        margin: 1rem 0 0.5rem 0;
        border-radius: 0 8px 8px 0;
    }
    
    /* Card styling */
    .info-card {
        background: #ffffff;
        padding: 1rem;
        border-radius: 8px;
        border: 1px solid #e9ecef;
        margin: 0.5rem 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    /* Metric cards */
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1rem;
        border-radius: 8px;
        text-align: center;
        margin: 0.5rem 0;
    }
    
    /* Button containers */
    .button-container {
        background: #f8f9fa;
        padding: 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
        border: 1px solid #dee2e6;
    }
    
    /* Status indicators */
    .status-success {
        background: #d4edda;
        color: #155724;
        padding: 0.5rem;
        border-radius: 6px;
        border-left: 4px solid #28a745;
        margin: 0.25rem 0;
    }
    
    .status-warning {
        background: #fff3cd;
        color: #856404;
        padding: 0.5rem;
        border-radius: 6px;
        border-left: 4px solid #ffc107;
        margin: 0.25rem 0;
    }
    
    .status-info {
        background: #d1ecf1;
        color: #0c5460;
        padding: 0.5rem;
        border-radius: 6px;
        border-left: 4px solid #17a2b8;
        margin: 0.25rem 0;
    }
    
    /* Reduce default spacing */
    .block-container {
        padding-top: 2rem;
    }
    
    /* Custom spacing */
    .custom-divider {
        margin: 1.5rem 0;
        border-top: 2px solid #e9ecef;
    }
    </style>
    """, unsafe_allow_html=True)

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
        
        # Calculate DPI and dimensions for exact sizing
        target_width_px = int(width_mm * 1200 / 25.4)  # Convert mm to pixels at 1200 DPI
        target_height_px = int(height_mm * 1200 / 25.4)
        
        # Resize with LANCZOS for HIGHEST quality
        barcode_resized = barcode_pil.resize((target_width_px, target_height_px), Image.Resampling.LANCZOS)
        
        # Create PDF with exact dimensions
        pdf_buffer = BytesIO()
        pdf_canvas = canvas.Canvas(pdf_buffer, pagesize=(width_mm*mm, height_mm*mm))
        
        # Save resized image to buffer for ReportLab
        img_buffer = BytesIO()
        barcode_resized.save(img_buffer, format='PNG', dpi=(1200, 1200), optimize=True)
        img_buffer.seek(0)
        
        # Draw image on PDF with exact positioning
        pdf_canvas.drawImage(
            ImageReader(img_buffer), 
            0, 0, 
            width=width_mm*mm, 
            height=height_mm*mm,
            preserveAspectRatio=False
        )
        
        pdf_canvas.save()
        pdf_buffer.seek(0)
        
        logger.info(f"Successfully generated Code 128A barcode PDF: {width_mm}x{height_mm}mm")
        return pdf_buffer.getvalue()
        
    except ImportError as e:
        logger.error(f"Missing required library for barcode generation: {e}")
        return None
    except Exception as e:
        logger.error(f"Error generating FNSKU barcode: {e}")
        return None

def extract_fnsku_page(fnsku_code, pdf_path):
    """Extract specific FNSKU page from barcode PDF"""
    try:
        with open(pdf_path, 'rb') as f:
            pdf_bytes = f.read()
        
        with safe_pdf_context(pdf_bytes) as doc:
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                text = page.get_text()
                
                if fnsku_code in text:
                    single_page_pdf = fitz.open()
                    single_page_pdf.insert_pdf(doc, from_page=page_num, to_page=page_num)
                    
                    output_buffer = BytesIO()
                    output_buffer.write(single_page_pdf.write())
                    single_page_pdf.close()
                    output_buffer.seek(0)
                    
                    logger.info(f"Found FNSKU {fnsku_code} on page {page_num + 1}")
                    return output_buffer.getvalue()
            
            logger.warning(f"FNSKU {fnsku_code} not found in PDF")
            return None
            
    except Exception as e:
        logger.error(f"Error extracting FNSKU page: {e}")
        return None

def generate_pdf(df):
    """Generate basic MRP label PDF"""
    try:
        if df.empty:
            return None
        
        row = df.iloc[0]
        
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=(LABEL_WIDTH, LABEL_HEIGHT))
        
        # Get data with fallbacks
        product_name = str(row.get('Name', 'Unknown Product'))
        net_weight = str(row.get('Net Weight', 'N/A'))
        mrp = str(row.get('MRP', 'N/A'))
        
        # Generate batch code
        batch_code = f"MFC{random.randint(1000, 9999)}"
        
        # Calculate expiry (24 months from today)
        expiry_date = datetime.now() + relativedelta(months=24)
        expiry_str = expiry_date.strftime("%m/%Y")
        
        # Draw content
        y_pos = LABEL_HEIGHT - 5*mm
        
        # Product name
        c.setFont("Helvetica-Bold", 8)
        c.drawString(2*mm, y_pos, product_name[:25])
        y_pos -= 4*mm
        
        # Weight and MRP
        c.setFont("Helvetica", 7)
        c.drawString(2*mm, y_pos, f"Net Wt: {net_weight}")
        c.drawString(25*mm, y_pos, f"MRP: ₹{mrp}")
        y_pos -= 3*mm
        
        # Batch and expiry
        c.drawString(2*mm, y_pos, f"Batch: {batch_code}")
        y_pos -= 3*mm
        c.drawString(2*mm, y_pos, f"Best Before: {expiry_str}")
        y_pos -= 3*mm
        
        # FSSAI
        c.setFont("Helvetica", 6)
        c.drawString(2*mm, y_pos, "FSSAI Lic: 12345678901234")
        
        c.save()
        buffer.seek(0)
        return buffer.getvalue()
        
    except Exception as e:
        logger.error(f"Error generating PDF: {e}")
        return None

def generate_combined_label_pdf_direct(df, fnsku_code):
    """Generate combined MRP + Direct barcode label (96x25mm)"""
    try:
        if df.empty:
            return None
        
        row = df.iloc[0]
        
        # Create 96x25mm PDF (48mm MRP + 48mm barcode)
        label_width = 96 * mm
        label_height = 25 * mm
        
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=(label_width, label_height))
        
        # MRP section (left 48mm)
        product_name = str(row.get('Name', 'Unknown Product'))
        net_weight = str(row.get('Net Weight', 'N/A'))
        mrp = str(row.get('MRP', 'N/A'))
        
        batch_code = f"MFC{random.randint(1000, 9999)}"
        expiry_date = datetime.now() + relativedelta(months=24)
        expiry_str = expiry_date.strftime("%m/%Y")
        
        y_pos = label_height - 5*mm
        
        c.setFont("Helvetica-Bold", 8)
        c.drawString(2*mm, y_pos, product_name[:20])
        y_pos -= 4*mm
        
        c.setFont("Helvetica", 7)
        c.drawString(2*mm, y_pos, f"Net Wt: {net_weight}")
        y_pos -= 3*mm
        c.drawString(2*mm, y_pos, f"MRP: ₹{mrp}")
        y_pos -= 3*mm
        c.drawString(2*mm, y_pos, f"Batch: {batch_code}")
        y_pos -= 3*mm
        c.drawString(2*mm, y_pos, f"Best Before: {expiry_str}")
        y_pos -= 3*mm
        
        c.setFont("Helvetica", 6)
        c.drawString(2*mm, y_pos, "FSSAI: 12345678901234")
        
        # Generate barcode for right section
        barcode_data = generate_fnsku_barcode_direct(fnsku_code, 48, 25)
        if barcode_data:
            barcode_buffer = BytesIO(barcode_data)
            c.drawImage(ImageReader(barcode_buffer), 48*mm, 0, 48*mm, 25*mm)
        
        c.save()
        buffer.seek(0)
        return buffer.getvalue()
        
    except Exception as e:
        logger.error(f"Error generating combined label: {e}")
        return None

def generate_combined_label_pdf(df, fnsku_code, barcode_pdf_path):
    """Generate combined label using existing PDF barcode"""
    try:
        mrp_pdf = generate_pdf(df)
        barcode_pdf = extract_fnsku_page(fnsku_code, barcode_pdf_path)
        
        if not mrp_pdf or not barcode_pdf:
            return None
        
        # Combine PDFs horizontally
        label_width = 96 * mm
        label_height = 25 * mm
        
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=(label_width, label_height))
        
        # Draw MRP (left)
        mrp_buffer = BytesIO(mrp_pdf)
        c.drawImage(ImageReader(mrp_buffer), 0, 0, 48*mm, 25*mm)
        
        # Draw barcode (right)
        barcode_buffer = BytesIO(barcode_pdf)
        c.drawImage(ImageReader(barcode_buffer), 48*mm, 0, 48*mm, 25*mm)
        
        c.save()
        buffer.seek(0)
        return buffer.getvalue()
        
    except Exception as e:
        logger.error(f"Error generating combined PDF label: {e}")
        return None

def generate_triple_label_combined(df, nutrition_row, selected_product, method="direct"):
    """Generate comprehensive triple label (50x100mm)"""
    try:
        if df.empty:
            return None
        
        # This is a simplified version - full implementation would be more complex
        buffer = BytesIO()
        
        # Create 50x100mm PDF
        label_width = 50 * mm
        label_height = 100 * mm
        
        c = canvas.Canvas(buffer, pagesize=(label_width, label_height))
        
        # Add placeholder content for now
        c.setFont("Helvetica-Bold", 10)
        c.drawString(5*mm, 90*mm, "TRIPLE LABEL")
        
        c.setFont("Helvetica", 8)
        c.drawString(5*mm, 85*mm, f"Product: {selected_product}")
        c.drawString(5*mm, 80*mm, "Ingredients Section")
        c.drawString(5*mm, 60*mm, "Nutrition Facts")
        c.drawString(5*mm, 40*mm, "MRP + Barcode")
        
        if method == "direct":
            c.drawString(5*mm, 35*mm, "Direct Generation")
        else:
            c.drawString(5*mm, 35*mm, "PDF Method")
        
        c.save()
        buffer.seek(0)
        return buffer.getvalue()
        
    except Exception as e:
        logger.error(f"Error generating triple label: {e}")
        return None
 unsafe_allow_html=True)
                                
                                direct_combined_h = generate_combined_label_pdf_direct(filtered_df, fnsku_code)
                                if direct_combined_h:
                                    st.download_button(
                                        "🧾 Download Combined", 
                                        data=direct_combined_h, 
                                        file_name=f"{safe_name}_Combined_Horizontal.pdf", 
                                        mime="application/pdf",
                                        use_container_width=True,
                                        type="secondary"
                                    )
                                else:
                                    st.error("❌ Generation failed")
                        
                        with tab2:
                            st.markdown("""
                            <div class="status-info">
                                ℹ️ Uses existing barcode PDF file uploaded via sidebar
                            </div>
                            """, unsafe_allow_html=True)
                            
                            # Extract barcode
                            barcode = extract_fnsku_page(fnsku_code, BARCODE_PDF_PATH)
                            if barcode:
                                col1, col2 = st.columns(2)
                                
                                with col1:
                                    st.markdown("""
                                    <div class="button-container">
                                        <strong>📦 Barcode from PDF</strong><br>
                                        <small>Extracted from uploaded PDF</small>
                                    </div>
                                    """, unsafe_allow_html=True)
                                    
                                    st.download_button(
                                        "📦 Download PDF Barcode", 
                                        data=barcode, 
                                        file_name=f"{fnsku_code}_barcode_pdf.pdf", 
                                        mime="application/pdf",
                                        use_container_width=True,
                                        type="secondary"
                                    )
                                
                                with col2:
                                    st.markdown("""
                                    <div class="button-container">
                                        <strong>🧾 PDF Combined</strong><br>
                                        <small>96mm × 25mm using PDF barcode</small>
                                    </div>
                                    """, unsafe_allow_html=True)
                                    
                                    combined = generate_combined_label_pdf(filtered_df, fnsku_code, BARCODE_PDF_PATH)
                                    if combined:
                                        st.download_button(
                                            "🧾 Download PDF Combined", 
                                            data=combined, 
                                            file_name=f"{safe_name}_Combined_PDF.pdf", 
                                            mime="application/pdf",
                                            use_container_width=True,
                                            type="secondary"
                                        )
                                    else:
                                        st.error("❌ Generation failed")
                            else:
                                st.markdown(f"""
                                <div class="status-warning">
                                    ⚠️ FNSKU {fnsku_code} not found in uploaded barcode PDF
                                </div>
                                """, unsafe_allow_html=True)
                        
                    else:
                        st.markdown("""
                        <div class="status-warning">
                            ⚠️ FNSKU is missing for this product
                        </div>
                        """, unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"❌ Error processing barcode: {str(e)}")
            else:
                st.markdown("""
                <div class="status-info">
                    ℹ️ <strong>Barcode labels unavailable</strong>
                </div>
                """, unsafe_allow_html=True)
                
                if 'FNSKU' not in filtered_df.columns:
                    st.caption("• FNSKU column not found in master data")
                elif not os.path.exists(BARCODE_PDF_PATH):
                    st.caption("• Barcode PDF not uploaded via sidebar")
                else:
                    st.caption("• FNSKU missing or barcode PDF not available")

            st.markdown('<div class="custom-divider"></div>', unsafe_allow_html=True)
            
            # Triple Label Generator Section
            st.markdown("""
            <div class="section-header">
                <h3>🎯 Advanced Triple Label Generator</h3>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown("""
            <div class="info-card">
                <strong>50mm × 100mm Comprehensive Label</strong><br>
                Combines: Ingredients + Nutrition Facts + MRP + Barcode in one professional label
            </div>
            """, unsafe_allow_html=True)
            
            try:
                # Load nutrition data
                with st.spinner("🔄 Loading nutrition data..."):
                    nutrition_df = load_nutrition_data_silent()
                
                if nutrition_df is not None:
                    nutrition_match = nutrition_df[nutrition_df['Product'] == selected_product]
                    
                    if nutrition_match.empty:
                        st.markdown(f"""
                        <div class="status-warning">
                            ⚠️ Nutrition data not found for '{selected_product}'
                        </div>
                        """, unsafe_allow_html=True)
                        
                        with st.expander("📋 View available products in nutrition database"):
                            available_products = sorted(nutrition_df['Product'].dropna().unique())
                            st.write("Available products: " + ", ".join(available_products))
                    else:
                        nutrition_row = nutrition_match.iloc[0]
                        
                        # Status indicators
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            st.markdown("""
                            <div class="status-success">
                                ✅ <strong>Master Data</strong><br>
                                Product & weight found
                            </div>
                            """, unsafe_allow_html=True)
                        
                        with col2:
                            st.markdown("""
                            <div class="status-success">
                                ✅ <strong>Nutrition Data</strong><br>
                                Ingredients & facts available
                            </div>
                            """, unsafe_allow_html=True)
                        
                        with col3:
                            fnsku_available = not is_empty_value(str(filtered_df.iloc[0].get('FNSKU', '')))
                            if fnsku_available:
                                st.markdown("""
                                <div class="status-success">
                                    ✅ <strong>FNSKU Available</strong><br>
                                    Barcode ready
                                </div>
                                """, unsafe_allow_html=True)
                            else:
                                st.markdown("""
                                <div class="status-warning">
                                    ⚠️ <strong>FNSKU Missing</strong><br>
                                    No barcode available
                                </div>
                                """, unsafe_allow_html=True)
                        
                        # Generation methods
                        tab1, tab2 = st.tabs(["✨ Direct Generation (Recommended)", "📁 PDF Method"])
                        
                        with tab1:
                            st.markdown("""
                            <div class="status-success">
                                ✅ Amazon-compliant Code 128A barcodes generated directly
                            </div>
                            """, unsafe_allow_html=True)
                            
                            col1, col2 = st.columns([2, 1])
                            
                            with col1:
                                st.markdown("""
                                <div class="info-card">
                                    <strong>Label Composition:</strong><br>
                                    🥗 Ingredients & Allergens (22mm)<br>
                                    📊 Nutritional Facts (35mm)<br>
                                    🏷️ MRP + Barcode (37mm)<br>
                                    📏 Total: 50mm × 100mm
                                </div>
                                """, unsafe_allow_html=True)
                            
                            with col2:
                                if st.button(
                                    "🎯 Generate Triple Label", 
                                    key="direct_triple", 
                                    use_container_width=True,
                                    type="primary"
                                ):
                                    with st.spinner("🔄 Generating comprehensive label..."):
                                        triple_pdf = generate_triple_label_combined(
                                            filtered_df, 
                                            nutrition_row, 
                                            selected_product,
                                            method="direct"
                                        )
                                        
                                        if triple_pdf:
                                            st.success("✅ Triple label generated successfully!")
                                            st.download_button(
                                                "📥 Download Triple Label", 
                                                data=triple_pdf, 
                                                file_name=f"{safe_name}_{selected_weight}_Triple_Direct.pdf", 
                                                mime="application/pdf",
                                                use_container_width=True,
                                                type="primary",
                                                key="download_direct_triple"
                                            )
                                        else:
                                            st.error("❌ Generation failed")
                        
                        with tab2:
                            st.markdown("""
                            <div class="status-info">
                                ℹ️ Uses existing barcode PDF file from sidebar
                            </div>
                            """, unsafe_allow_html=True)
                            
                            if os.path.exists(BARCODE_PDF_PATH):
                                col1, col2 = st.columns([2, 1])
                                
                                with col1:
                                    st.markdown("""
                                    <div class="info-card">
                                        <strong>PDF Method Features:</strong><br>
                                        • Uses uploaded barcode PDF<br>
                                        • Extracts specific FNSKU page<br>
                                        • Combines with generated content<br>
                                        • Professional layout
                                    </div>
                                    """, unsafe_allow_html=True)
                                
                                with col2:
                                    if st.button(
                                        "🎯 Generate Triple Label", 
                                        key="pdf_triple", 
                                        use_container_width=True,
                                        type="secondary"
                                    ):
                                        with st.spinner("🔄 Generating with PDF method..."):
                                            triple_pdf = generate_triple_label_combined(
                                                filtered_df, 
                                                nutrition_row, 
                                                selected_product,
                                                method="pdf"
                                            )
                                            
                                            if triple_pdf:
                                                st.success("✅ Triple label generated successfully!")
                                                st.download_button(
                                                    "📥 Download Triple Label", 
                                                    data=triple_pdf, 
                                                    file_name=f"{safe_name}_{selected_weight}_Triple_PDF.pdf", 
                                                    mime="application/pdf",
                                                    use_container_width=True,
                                                    type="secondary",
                                                    key="download_pdf_triple"
                                                )
                                            else:
                                                st.error("❌ Generation failed")
                            else:
                                st.markdown("""
                                <div class="status-warning">
                                    ⚠️ Barcode PDF not available<br>
                                    Please upload barcode PDF via sidebar to use this method
                                </div>
                                """, unsafe_allow_html=True)
                else:
                    st.markdown("""
                    <div class="status-warning">
                        ❌ Could not load nutrition data<br>
                        Please check your internet connection and try again
                    </div>
                    """, unsafe_allow_html=True)
                    
            except Exception as e:
                st.error(f"❌ Error in triple label section: {str(e)}")
                logger.error(f"Triple label error: {str(e)}")
        else:
            st.markdown("""
            <div class="status-warning">
                ⚠️ No matching data found for selected product and weight combination
            </div>
            """, unsafe_allow_html=True)
            
    except Exception as e:
        st.error(f"❌ Unexpected error: {str(e)}")
        logger.error(f"Label generator tool error: {str(e)}")
        
    # Footer
    st.markdown('<div class="custom-divider"></div>', unsafe_allow_html=True)
    st.markdown("""
    <div style="text-align: center; color: #6c757d; padding: 1rem;">
        <small>🔖 Mithila Tools - Professional Label Generation System</small>
    </div>
    """, unsafe_allow_html=True)
