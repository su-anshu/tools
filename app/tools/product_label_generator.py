import streamlit as st
import pandas as pd
import io
from datetime import datetime
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
import logging
from app.utils import setup_tool_ui, load_and_validate_master_data

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_label_pdf(product_name, label_size, include_date=True):
    """
    Create a PDF with labels based on the selected size
    
    Args:
        product_name (str): Name of the product or custom text
        label_size (str): Either "48x25mm", "96x25mm", "50x100mm", or "100x50mm"
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
    elif label_size == "100x50mm":
        # Horizontal label: 100mm x 50mm
        width = 100 * mm_to_pt
        height = 50 * mm_to_pt
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

def wrap_text(canvas_obj, text, max_width, font_name, font_size, max_lines=3):
    """
    Wrap text into multiple lines that fit within the given width
    
    Args:
        canvas_obj: ReportLab canvas object
        text: Text to wrap
        max_width: Maximum width in points
        font_name: Font name (e.g., "Helvetica-Bold")
        font_size: Font size in points
        max_lines: Maximum number of lines (default 3)
    
    Returns:
        list: List of text lines
    """
    if not text:
        return []
    
    canvas_obj.setFont(font_name, font_size)
    words = text.split()
    
    if not words:
        return []
    
    lines = []
    current_line = words[0]
    
    for word in words[1:]:
        # Test if adding the next word would exceed width
        test_line = current_line + " " + word
        test_width = canvas_obj.stringWidth(test_line, font_name, font_size)
        
        if test_width <= max_width:
            current_line = test_line
        else:
            # Current line is full, start a new line
            lines.append(current_line)
            if len(lines) >= max_lines:
                # If we've reached max lines, truncate the last word if needed
                break
            current_line = word
    
    # Add the last line
    if current_line:
        lines.append(current_line)
    
    return lines[:max_lines]  # Ensure we don't exceed max_lines

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
        
        # Wrap product name into multiple lines instead of reducing font size
        available_width = width * 0.9
        product_lines = wrap_text(canvas_obj, product_name, available_width, "Helvetica-Bold", product_font_size, max_lines=3)
        
        # Calculate text heights for wrapped text
        line_height = product_font_size * 1.2  # Line spacing
        product_text_height = len(product_lines) * line_height
        
        # Baseline offset for proper vertical centering (ReportLab uses baseline as y-coordinate)
        # Ascent ≈ 0.8 × font_size, Descent ≈ 0.2 × font_size
        # To center: baseline_y = center_y - (0.8 × font_size / 2) + (0.2 × font_size / 2) = center_y - 0.3 × font_size
        product_baseline_offset = product_font_size * 0.3
        
        # Calculate padding and usable space
        vertical_padding = height * 0.1  # 10% padding from top and bottom
        usable_height = height - (2 * vertical_padding)
        
        if include_date:
            # Set font for date to calculate dimensions
            canvas_obj.setFont("Helvetica-Bold", date_font_size)
            date_text_height = date_font_size * 1.2
            date_baseline_offset = date_font_size * 0.3
            
            # Calculate spacing between product name and date
            spacing = usable_height * 0.15  # 15% of usable height as spacing
            
            # Total content height (using actual text heights)
            total_content_height = product_text_height + spacing + date_text_height
            
            # Center the entire content block vertically
            content_center_y = height / 2
            
            # Calculate vertical center for product name (top of content block)
            product_center_y = content_center_y - (date_text_height + spacing) / 2
            # Position product name baseline (accounting for baseline offset)
            product_name_y = product_center_y - product_baseline_offset
            
            # Calculate vertical center for date (bottom of content block)
            date_center_y = content_center_y + (product_text_height + spacing) / 2
            # Position date baseline (accounting for baseline offset)
            date_y = date_center_y - date_baseline_offset
        else:
            # Center product name vertically when no date
            center_y = height / 2
            # Position baseline accounting for baseline offset
            product_name_y = center_y - product_baseline_offset
        
        # Draw product name lines (center-aligned horizontally)
        canvas_obj.setFont("Helvetica-Bold", product_font_size)
        line_height = product_font_size * 1.2
        
        # Calculate center Y for the text block
        # product_name_y is the baseline position for single line
        # For multi-line, center the block around this position
        total_lines_height = len(product_lines) * line_height
        # Top line baseline = center_y + (total_height - line_height) / 2
        top_line_y = product_name_y + (total_lines_height - line_height) / 2
        
        # Draw each line (from top to bottom)
        for i, line in enumerate(product_lines):
            line_width = canvas_obj.stringWidth(line, "Helvetica-Bold", product_font_size)
            line_x = x_offset + (width - line_width) / 2
            line_y = top_line_y - (i * line_height)
            canvas_obj.drawString(line_x, line_y, line)
        
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
        
        # Product name font size (large and bold) - maintain consistent size
        product_font_size = max(12, int(16 * scale_factor))
        # Date font size - increased size
        date_font_size = max(8, int(12 * scale_factor))
        
        # Wrap product name into multiple lines instead of reducing font size
        available_width = width * 0.9  # Use 90% of width for text
        product_lines = wrap_text(canvas_obj, product_name, available_width, "Helvetica-Bold", product_font_size, max_lines=3)
        
        # Calculate text heights for wrapped text
        line_height = product_font_size * 1.2  # Line spacing
        product_text_height = len(product_lines) * line_height
        
        # Baseline offset for proper vertical centering (ReportLab uses baseline as y-coordinate)
        # Ascent ≈ 0.8 × font_size, Descent ≈ 0.2 × font_size
        # To center: baseline_y = center_y - (0.8 × font_size / 2) + (0.2 × font_size / 2) = center_y - 0.3 × font_size
        product_baseline_offset = product_font_size * 0.3
        
        # Calculate padding and usable space
        vertical_padding = height * 0.1  # 10% padding from top and bottom
        usable_height = height - (2 * vertical_padding)
        
        if include_date:
            # Set font for date to calculate dimensions
            canvas_obj.setFont("Helvetica-Bold", date_font_size)
            date_text_height = date_font_size * 1.2
            date_baseline_offset = date_font_size * 0.3
            
            # Calculate spacing between product name and date
            spacing = usable_height * 0.1  # 10% of usable height as spacing
            
            # Total content height (using actual text heights)
            total_content_height = product_text_height + spacing + date_text_height
            
            # Center the entire content block vertically within usable area
            content_center_y = vertical_padding + usable_height / 2
            
            # Calculate vertical center for product name (top of content block)
            product_center_y = content_center_y - (date_text_height + spacing) / 2
            # Position product name baseline (accounting for baseline offset)
            product_name_y = product_center_y - product_baseline_offset
            
            # Calculate vertical center for date (bottom of content block)
            date_center_y = content_center_y + (product_text_height + spacing) / 2
            # Position date baseline (accounting for baseline offset)
            date_y = date_center_y - date_baseline_offset
        else:
            # Center product name vertically when no date
            center_y = vertical_padding + usable_height / 2
            # Position baseline accounting for baseline offset
            product_name_y = center_y - product_baseline_offset
        
        # Draw product name lines (center-aligned)
        canvas_obj.setFont("Helvetica-Bold", product_font_size)
        line_height = product_font_size * 1.2
        
        # Calculate center Y for the text block
        # product_name_y is the baseline position for single line
        # For multi-line, center the block around this position
        total_lines_height = len(product_lines) * line_height
        # Top line baseline = center_y + (total_height - line_height) / 2
        top_line_y = product_name_y + (total_lines_height - line_height) / 2
        
        # Draw each line (from top to bottom)
        for i, line in enumerate(product_lines):
            line_width = canvas_obj.stringWidth(line, "Helvetica-Bold", product_font_size)
            line_x = x_offset + (width - line_width) / 2
            line_y = top_line_y - (i * line_height)
            canvas_obj.drawString(line_x, line_y, line)
        
        # Draw date only if include_date is True
        if include_date:
            # Set font for date
            canvas_obj.setFont("Helvetica-Bold", date_font_size)
            
            # Draw date (center-aligned)
            date_text_width = canvas_obj.stringWidth(current_date, "Helvetica-Bold", date_font_size)
            date_x = x_offset + (width - date_text_width) / 2
            canvas_obj.drawString(date_x, date_y, current_date)

def create_pair_label_pdf(product1, product2, include_date=True):
    """
    Create a 96x25mm PDF page with two labels side by side (48x25mm each)
    
    Args:
        product1 (str): Name of the first product (left label)
        product2 (str or None): Name of the second product (right label). If None, right label is blank
        include_date (bool): Whether to include the date on the labels
    
    Returns:
        bytes: PDF content as bytes
    """
    buffer = io.BytesIO()
    
    # Convert mm to points (1 mm = 2.834645669 points)
    mm_to_pt = 2.834645669
    
    # Two labels side by side: 96mm x 25mm total (48mm x 25mm each)
    width = 96 * mm_to_pt
    height = 25 * mm_to_pt
    c = canvas.Canvas(buffer, pagesize=(width, height))
    
    # Draw left label (48x25mm)
    label_width = 48 * mm_to_pt
    draw_single_label(c, product1, label_width, height, x_offset=0, include_date=include_date)
    
    # Draw right label (48x25mm) - only if product2 is provided
    if product2 is not None:
        draw_single_label(c, product2, label_width, height, x_offset=label_width, include_date=include_date)
    # If product2 is None, leave right half blank (no drawing needed)
    
    c.save()
    buffer.seek(0)
    return buffer.getvalue()

def product_label_generator_tool():
    """Product Label Generator Tool - Generates PDF labels with product name and date"""
    # Setup UI with CSS
    setup_tool_ui("Product Label Generator")
    
    # Load data from Google Sheets
    with st.spinner("Loading product data from Google Sheets..."):
        master_df = load_and_validate_master_data(show_error=True)
    
    if master_df is None or master_df.empty:
        st.error("❌ Could not load data from Google Sheets. Please check your connection and try again.")
        st.info("💡 **Solution**: Ensure Google Sheets is accessible and properly configured in the sidebar.")
        return
    
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
        options=["48x25mm", "96x25mm", "50x100mm", "100x50mm"],
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

