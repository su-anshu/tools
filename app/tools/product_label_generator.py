import streamlit as st
import pandas as pd
import io
from datetime import datetime
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_label_pdf(product_name, label_size, include_date=True):
    """
    Create a PDF with labels based on the selected size
    
    Args:
        product_name (str): Name of the product or custom text
        label_size (str): Either "48x25mm", "96x25mm", or "50x100mm"
        include_date (bool): Whether to include the date on the label
    
    Returns:
        bytes: PDF content as bytes
    """
    buffer = io.BytesIO()
    
    # Convert mm to points (1 mm = 2.834645669 points)
    mm_to_pt = 2.834645669
    
    if label_size == "48x25mm":
        # Single label: 48mm x 25mm
        width = 48 * mm_to_pt
        height = 25 * mm_to_pt
        c = canvas.Canvas(buffer, pagesize=(width, height))
        draw_single_label(c, product_name, width, height, x_offset=0.0, include_date=include_date)
    elif label_size == "96x25mm":
        # Two labels side by side: 96mm x 25mm total (48mm x 25mm each)
        width = 96 * mm_to_pt
        height = 25 * mm_to_pt
        c = canvas.Canvas(buffer, pagesize=(width, height))
        
        # Draw two identical labels side by side
        label_width = 48 * mm_to_pt
        draw_single_label(c, product_name, label_width, height, x_offset=0, include_date=include_date)
        draw_single_label(c, product_name, label_width, height, x_offset=label_width, include_date=include_date)
    elif label_size == "50x100mm":
        # Vertical label: 50mm x 100mm
        width = 50 * mm_to_pt
        height = 100 * mm_to_pt
        c = canvas.Canvas(buffer, pagesize=(width, height))
        draw_single_label(c, product_name, width, height, x_offset=0.0, include_date=include_date)
    else:
        # Default to 48x25mm if unknown size
        width = 48 * mm_to_pt
        height = 25 * mm_to_pt
        c = canvas.Canvas(buffer, pagesize=(width, height))
        draw_single_label(c, product_name, width, height, x_offset=0.0, include_date=include_date)
    
    c.save()
    buffer.seek(0)
    return buffer.getvalue()

def draw_single_label(canvas_obj, product_name, width, height, x_offset=0.0, include_date=True):
    """
    Draw a single label on the canvas with improved sizing and spacing
    
    Args:
        canvas_obj: ReportLab canvas object
        product_name (str): Name of the product or custom text
        width (float): Width of the label in points
        height (float): Height of the label in points
        x_offset (float): Horizontal offset for positioning
        include_date (bool): Whether to include the date on the label
    """
    # Get current date in DD/MM/YYYY format
    current_date = datetime.now().strftime("%d/%m/%Y")
    
    # Determine if this is a vertical label (50x100mm) or horizontal
    is_vertical = height > width
    
    if is_vertical:
        # Vertical label (50x100mm) - adjust layout for vertical orientation
        # Calculate font sizes based on height for vertical labels
        base_height = 100 * 2.834645669  # 100mm in points
        scale_factor = height / base_height
        
        # Product name font size - larger for vertical labels
        product_font_size = max(14, int(20 * scale_factor))
        # Date font size
        date_font_size = max(10, int(14 * scale_factor))
        
        # Set font for product name to calculate text dimensions
        canvas_obj.setFont("Helvetica-Bold", product_font_size)
        
        # Check if product name fits, if not, reduce font size
        text_width = canvas_obj.stringWidth(product_name, "Helvetica-Bold", product_font_size)
        available_width = width * 0.9
        
        # Adjust font size if text is too wide
        while text_width > available_width and product_font_size > 8:
            product_font_size -= 1
            canvas_obj.setFont("Helvetica-Bold", product_font_size)
            text_width = canvas_obj.stringWidth(product_name, "Helvetica-Bold", product_font_size)
        
        # Calculate text heights (approximate: font_size * 1.2 for line height)
        product_text_height = product_font_size * 1.2
        
        # Calculate padding and usable space
        vertical_padding = height * 0.1  # 10% padding from top and bottom
        usable_height = height - (2 * vertical_padding)
        
        if include_date:
            # Set font for date to calculate dimensions
            canvas_obj.setFont("Helvetica-Bold", date_font_size)
            date_text_height = date_font_size * 1.2
            
            # Calculate spacing between product name and date
            spacing = usable_height * 0.15  # 15% of usable height as spacing
            
            # Total content height
            total_content_height = product_text_height + spacing + date_text_height
            
            # Center the entire content block vertically
            content_start_y = (height - total_content_height) / 2
            
            # Position product name at top of content block
            product_name_y = content_start_y + product_text_height
            # Position date below product name with spacing
            date_y = content_start_y + product_text_height + spacing
        else:
            # Center product name vertically when no date
            product_name_y = (height + product_text_height) / 2
        
        # Draw product name (center-aligned horizontally)
        product_name_x = x_offset + (width - text_width) / 2
        canvas_obj.setFont("Helvetica-Bold", product_font_size)
        canvas_obj.drawString(product_name_x, product_name_y, product_name)
        
        # Draw date only if include_date is True
        if include_date:
            # Set font for date
            canvas_obj.setFont("Helvetica-Bold", date_font_size)
            
            # Draw date (center-aligned horizontally)
            date_text_width = canvas_obj.stringWidth(current_date, "Helvetica-Bold", date_font_size)
            date_x = x_offset + (width - date_text_width) / 2
            canvas_obj.drawString(date_x, date_y, current_date)
    else:
        # Horizontal label (48x25mm or 96x25mm) - original layout
        # Calculate dynamic font sizes based on label dimensions
        base_width = 48 * 2.834645669  # 48mm in points
        scale_factor = width / base_width
        
        # Product name font size (large and bold) - increased size
        product_font_size = max(12, int(16 * scale_factor))
        # Date font size - increased size
        date_font_size = max(8, int(12 * scale_factor))
        
        # Set font for product name to calculate text dimensions
        canvas_obj.setFont("Helvetica-Bold", product_font_size)
        
        # Check if product name fits, if not, reduce font size
        text_width = canvas_obj.stringWidth(product_name, "Helvetica-Bold", product_font_size)
        available_width = width * 0.9  # Use 90% of width for text
        
        # Adjust font size if text is too wide
        while text_width > available_width and product_font_size > 8:
            product_font_size -= 1
            canvas_obj.setFont("Helvetica-Bold", product_font_size)
            text_width = canvas_obj.stringWidth(product_name, "Helvetica-Bold", product_font_size)
        
        # Calculate text heights (approximate: font_size * 1.2 for line height)
        product_text_height = product_font_size * 1.2
        
        # Calculate padding and usable space
        vertical_padding = height * 0.1  # 10% padding from top and bottom
        usable_height = height - (2 * vertical_padding)
        
        if include_date:
            # Set font for date to calculate dimensions
            canvas_obj.setFont("Helvetica-Bold", date_font_size)
            date_text_height = date_font_size * 1.2
            
            # Calculate spacing between product name and date
            spacing = usable_height * 0.1  # 10% of usable height as spacing
            
            # Total content height
            total_content_height = product_text_height + spacing + date_text_height
            
            # Center the entire content block vertically
            content_start_y = vertical_padding + (usable_height - total_content_height) / 2
            
            # Position product name at top of content block
            product_name_y = content_start_y + product_text_height
            # Position date below product name with spacing
            date_y = content_start_y + product_text_height + spacing
        else:
            # Center product name vertically when no date
            product_name_y = vertical_padding + (usable_height + product_text_height) / 2
        
        # Draw product name (center-aligned)
        product_name_x = x_offset + (width - text_width) / 2
        canvas_obj.setFont("Helvetica-Bold", product_font_size)
        canvas_obj.drawString(product_name_x, product_name_y, product_name)
        
        # Draw date only if include_date is True
        if include_date:
            # Set font for date
            canvas_obj.setFont("Helvetica-Bold", date_font_size)
            
            # Draw date (center-aligned)
            date_text_width = canvas_obj.stringWidth(current_date, "Helvetica-Bold", date_font_size)
            date_x = x_offset + (width - date_text_width) / 2
            canvas_obj.drawString(date_x, date_y, current_date)

def product_label_generator_tool():
    """Product Label Generator Tool - Generates PDF labels with product name and date"""
    # Inject custom CSS
    try:
        from app.utils.ui_components import inject_custom_css
        inject_custom_css()
    except Exception:
        pass
    
    # Minimal header
    st.markdown("### Product Label Generator")
    
    # Sidebar controls
    from app.sidebar import sidebar_controls, load_master_data
    admin_logged_in, _, _, _ = sidebar_controls()
    
    # Load data from Google Sheets only
    with st.spinner("Loading product data from Google Sheets..."):
        master_df = load_master_data()
    
    if master_df is None or master_df.empty:
        st.error("❌ Could not load data from Google Sheets. Please check your connection and try again.")
        st.info("💡 **Solution**: Ensure Google Sheets is accessible and properly configured in the sidebar.")
        return
    
    # Clean column names
    master_df.columns = master_df.columns.str.strip()
    
    # Extract product names from "Name" column
    name_column = None
    for col in master_df.columns:
        if col.lower().strip() in ['name', 'product name', 'product', 'item name', 'item']:
            name_column = col
            break
    
    if name_column is None:
        st.error("❌ No 'Name' column found in the Google Sheet")
        st.info(f"📋 Available columns: {', '.join(master_df.columns)}")
        return
    
    # Get unique product names
    product_names = master_df[name_column].dropna().unique().tolist()
    product_names = [str(name).strip() for name in product_names if str(name).strip() and str(name).strip().lower() != 'nan']
    
    if not product_names:
        st.warning("⚠️ No product names found in the Google Sheet")
        return
    
    st.success(f"✅ Loaded {len(product_names)} products from Google Sheets")
    
    # Mode selection: Product from Sheet or Custom Text
    mode = st.radio(
        "Mode:",
        options=["Product from Sheet", "Custom Text"],
        index=0,
        key="product_label_mode_radio"
    )
    
    # Initialize session state for custom text
    if 'custom_text' not in st.session_state:
        st.session_state.custom_text = ""
    
    # Conditional rendering based on mode
    if mode == "Product from Sheet":
        # Product preview (collapsed by default)
        with st.expander(f"Show all products ({len(product_names)})", expanded=False):
            cols = st.columns(3)
            for i, name in enumerate(product_names):
                col_idx = i % 3
                cols[col_idx].write(f"{i+1}. {name}")
        
        # Product selection
        selected_product = st.selectbox(
            "Select product:",
            options=product_names,
            index=0,
            key="product_label_product_select"
        )
        display_text = selected_product
    else:
        # Custom text input
        custom_text = st.text_input(
            "Enter custom text:",
            value=st.session_state.custom_text,
            key="product_label_custom_text_input",
            placeholder="Enter any text for the label..."
        )
        st.session_state.custom_text = custom_text
        selected_product = custom_text if custom_text else "Sample Text"
        display_text = custom_text if custom_text else "Enter text above"
    
    # Label size selection
    label_size = st.radio(
        "Label size:",
        options=["48x25mm", "96x25mm", "50x100mm"],
        key="product_label_size_radio"
    )
    
    # Preview section
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"<div style='text-align: center; font-size: 20px; font-weight: bold; padding: 10px; border: 2px solid #ddd; border-radius: 5px; margin: 10px 0;'>{display_text}</div>", unsafe_allow_html=True)
    with col2:
        current_date = datetime.now().strftime("%d/%m/%Y")
        st.markdown(f"<div style='text-align: center; font-size: 16px; font-weight: bold; padding: 10px; border: 2px solid #ddd; border-radius: 5px; margin: 10px 0;'>{current_date}</div>", unsafe_allow_html=True)
    
    # Two download buttons: one with date, one without
    if display_text and display_text != "Enter text above":
        try:
            safe_text = str(selected_product).replace(' ', '_').replace('/', '_').replace('\\', '_')
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            # Generate PDF with date
            pdf_bytes_with_date = create_label_pdf(selected_product, label_size, include_date=True)
            filename_with_date = f"{safe_text}_{label_size}_with_date_{timestamp}.pdf"
            
            # Generate PDF without date
            pdf_bytes_without_date = create_label_pdf(selected_product, label_size, include_date=False)
            filename_without_date = f"{safe_text}_{label_size}_no_date_{timestamp}.pdf"
            
            # Display two download buttons side by side
            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    label="📥 Download with Date",
                    data=pdf_bytes_with_date,
                    file_name=filename_with_date,
                    mime="application/pdf",
                    type="primary",
                    key=f"product_label_download_with_date_{label_size}_{hash(selected_product)}"
                )
            with col2:
                st.download_button(
                    label="📥 Download without Date",
                    data=pdf_bytes_without_date,
                    file_name=filename_without_date,
                    mime="application/pdf",
                    type="secondary",
                    key=f"product_label_download_no_date_{label_size}_{hash(selected_product)}"
                )
        except Exception as e:
            st.error(f"❌ Error generating PDF: {str(e)}")
            logger.error(f"Error generating product label PDF: {str(e)}")
    else:
        st.info("👆 Please select a product or enter custom text to generate a label")

