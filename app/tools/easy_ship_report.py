import streamlit as st
import pandas as pd
import re
from io import BytesIO
from datetime import date
import logging
from app.sidebar import sidebar_controls, load_master_data
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, KeepTogether, PageBreak
)
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
import os

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def is_empty_value(value):
    """Standardized check for empty/invalid values"""
    if pd.isna(value):
        return True
    if value is None:
        return True
    str_value = str(value).strip().lower()
    return str_value in ["", "nan", "none", "null", "n/a"]

def detect_multi_item_orders(df):
    """Detect orders with multiple different products"""
    try:
        # Group by tracking-id and count unique products
        order_analysis = df.groupby('tracking-id').agg({
            'product-name': 'nunique',  # Count unique products per order
            'asin': 'nunique',          # Count unique ASINs per order  
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

def easy_ship_report():
    # Inject custom CSS
    try:
        from app.utils.ui_components import inject_custom_css
        inject_custom_css()
    except Exception:
        pass
    
    # Minimal header
    st.markdown("### Easy Ship Order Report Generator")
    admin_logged_in, _, _, _ = sidebar_controls()

    # Load master data from Google Sheets or Excel backup
    mrp_df = None
    asin_map = pd.DataFrame()
    
    mrp_df = load_master_data()
    if mrp_df is not None:
        try:
            if 'Name' in mrp_df.columns and 'Net Weight' in mrp_df.columns:
                mrp_df['clean_product_name'] = (
                    mrp_df['Name'].fillna('Unknown') + " " + 
                    mrp_df['Net Weight'].fillna('N/A').astype(str) + "kg"
                )
                asin_map = mrp_df[['ASIN', 'clean_product_name']].dropna()
                logger.info(f"Loaded {len(asin_map)} ASIN mappings from master data")
            else:
                st.warning("Master data missing required columns (Name, Net Weight)")
        except Exception as e:
            st.warning(f"Could not process master data: {str(e)}")
            logger.error(f"Error processing master data: {str(e)}")
    else:
        st.warning("Master data not available. Product names may not be cleaned.")

    # Easy Ship file uploader
    uploaded_file = st.file_uploader("Upload your Amazon Easy Ship Excel file", type="xlsx")

    if uploaded_file:
        try:
            # Validate file size
            if uploaded_file.size > 50 * 1024 * 1024:  # 50MB limit
                st.error("File too large. Please upload a file smaller than 50MB.")
                return

            # Read the Excel file
            try:
                # Try to read with automatic sheet detection
                xl_file = pd.ExcelFile(uploaded_file)
                if not xl_file.sheet_names:
                    st.error("No sheets found in Excel file")
                    return
                
                # Use first sheet if "Sheet1" doesn't exist
                sheet_name = "Sheet1" if "Sheet1" in xl_file.sheet_names else xl_file.sheet_names[0]
                df = pd.read_excel(uploaded_file, sheet_name=sheet_name)
                
                if sheet_name != "Sheet1":
                    st.info(f"Using sheet: {sheet_name}")
                    
            except Exception as e:
                st.error(f"Error reading Excel file: {str(e)}")
                st.info("Please ensure the file is a valid Excel file with the correct format.")
                return

            # Validate required columns
            required_columns = ['tracking-id', 'asin', 'product-name', 'quantity-purchased', 'pickup-slot']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                st.error(f"Missing required columns: {missing_columns}")
                st.info("Required columns: tracking-id, asin, product-name, quantity-purchased, pickup-slot")
                return

            # Filter and process data
            try:
                df = df[required_columns].copy()
                df = df.dropna(subset=['tracking-id', 'asin'])  # Remove rows with missing critical data
                df = df.sort_values(by="asin")
                
                if df.empty:
                    st.warning("No valid data found in the uploaded file.")
                    return

                logger.info(f"Processing {len(df)} orders")

                # Truncate messy product names
                def truncate_product_name(text):
                    try:
                        if is_empty_value(text):
                            return "Unknown Product"
                        words = str(text).split()
                        return ' '.join(words[:10])[:70]
                    except Exception:
                        return "Unknown Product"

                df['product-name'] = df['product-name'].apply(truncate_product_name)

                # Clean pickup date with improved regex
                def extract_month_day(slot):
                    try:
                        if is_empty_value(slot):
                            return "No Date"
                        # Look for patterns like "January 15", "Feb 3", etc.
                        match = re.search(r'[A-Za-z]{3,9}\s+\d{1,2}', str(slot))
                        return match.group(0) if match else str(slot)[:20]
                    except Exception:
                        return "Invalid Date"

                df['pickup-slot'] = df['pickup-slot'].apply(extract_month_day)

                # Rename quantity column and add highlighting
                df = df.rename(columns={'quantity-purchased': 'qty'})
                
                # Safe quantity conversion
                def safe_int_conversion(value):
                    try:
                        return int(float(value)) if pd.notna(value) else 1
                    except (ValueError, TypeError):
                        return 1

                df['qty'] = df['qty'].apply(safe_int_conversion)
                df['highlight'] = df['qty'] > 1

                # Merge clean names using ASIN if mapping exists
                if not asin_map.empty:
                    try:
                        df = df.merge(asin_map, left_on='asin', right_on='ASIN', how='left')
                        # Use clean name if available, otherwise keep original
                        df['product-name'] = df['clean_product_name'].fillna(df['product-name'])
                        df.drop(columns=['clean_product_name', 'ASIN'], inplace=True, errors='ignore')
                        logger.info("Applied ASIN mapping to product names")
                    except Exception as e:
                        logger.warning(f"Could not apply ASIN mapping: {str(e)}")

                # Detect multi-item orders
                multi_item_orders, order_stats = detect_multi_item_orders(df)

                st.caption(f"{len(df)} orders processed successfully")
                
                # Show order analysis
                st.markdown("**Order Analysis**")
                col1, col2, col3 = st.columns(3)
                
                total_orders = len(df['tracking-id'].unique())
                multi_item_count = len(multi_item_orders)
                single_item_count = total_orders - multi_item_count
                
                with col1:
                    st.metric("Total Orders", total_orders)
                with col2:
                    st.metric("Multi-Item Orders", multi_item_count)
                with col3:
                    risk_level = "High" if multi_item_count > 20 else "Medium" if multi_item_count > 10 else "Low"
                    st.metric("Risk Level", risk_level)

                # Show warning if multi-item orders exist
                if multi_item_count > 0:
                    st.warning(f"{multi_item_count} orders contain multiple items - require complete packing")
                    
                    # Show multi-item order details
                    with st.expander("View Multi-Item Order Details"):
                        for tracking_id in multi_item_orders[:5]:  # Show first 5
                            order_items = df[df['tracking-id'] == tracking_id]
                            items_list = order_items['product-name'].tolist()
                            st.write(f"**{tracking_id}:** {', '.join(items_list)}")
                        if len(multi_item_orders) > 5:
                            st.write(f"... and {len(multi_item_orders) - 5} more multi-item orders")
                else:
                    st.caption("All orders are single-item orders - no risk of incomplete packing")

                # Show preview of data
                with st.expander("Preview Processed Data"):
                    display_df = df.drop(columns=['highlight'], errors='ignore')
                    st.dataframe(display_df)

                # Grouping style selector
                st.markdown("**Report Generation**")
                grouping_style = st.radio(
                    "Select Report Grouping Style:",
                    [
                        "By Product Only (Current Method)",
                        "Multi-Item First, Then By Product (Recommended)", 
                        "By Product with Multi-Item Warnings"
                    ],
                    index=1 if multi_item_count > 0 else 0,  # Default to recommended if multi-item orders exist
                    help="Choose how to organize the PDF report for your packers"
                )

                # Orientation selector
                orientation = st.radio("Select Page Orientation", ["Portrait", "Landscape"], horizontal=True)

                # Enhanced PDF generation function
                def generate_grouped_pdf(dataframe, orientation, grouping_style, multi_item_orders):
                    try:
                        buffer = BytesIO()
                        styles = getSampleStyleSheet()
                        
                        # Define custom styles
                        title_style = ParagraphStyle(
                            name='CustomTitle',
                            parent=styles['Heading1'],
                            fontSize=16,
                            alignment=1,  # Center
                            fontName='Helvetica-Bold'
                        )
                        
                        warning_style = ParagraphStyle(
                            name='Warning',
                            parent=styles['Normal'],
                            fontSize=12,
                            textColor=colors.red,
                            alignment=1,  # Center
                            fontName='Helvetica-Bold'
                        )
                        
                        section_style = ParagraphStyle(
                            name='SectionHeader',
                            parent=styles['Heading2'],
                            fontSize=14,
                            textColor=colors.darkblue,
                            fontName='Helvetica-Bold'
                        )
                        
                        order_header_style = ParagraphStyle(
                            name='OrderHeader',
                            parent=styles['Heading3'],
                            fontSize=11,
                            textColor=colors.darkgreen,
                            fontName='Helvetica-Bold'
                        )
                        
                        product_header_style = ParagraphStyle(
                            name='ProductHeader',
                            parent=styles['Heading3'],
                            fontSize=12,
                            textColor=colors.darkblue,
                            fontName='Helvetica-Bold'
                        )

                        today_str = date.today().strftime("%Y-%m-%d")
                        page_size = A4 if orientation == "Portrait" else landscape(A4)

                        # Calculate statistics first (used in title, doc title, and stats)
                        total_orders = len(dataframe['tracking-id'].unique())
                        multi_count = len(multi_item_orders)
                        single_count = total_orders - multi_count

                        doc = SimpleDocTemplate(
                            buffer, 
                            pagesize=page_size, 
                            title=f"Easy Ship Report - {total_orders} Orders - {today_str}"
                        )
                        elements = []

                        # Title and summary
                        title = f"Easy Ship Report - {total_orders} Orders - {today_str}"
                        elements.append(Paragraph(title, title_style))
                        elements.append(Spacer(1, 12))
                        
                        # Statistics summary
                        
                        stats_text = f"📊 Total Orders: {total_orders} | Multi-Item Orders: {multi_count} | Single-Item Orders: {single_count}"
                        elements.append(Paragraph(stats_text, styles['Normal']))
                        elements.append(Spacer(1, 12))

                        # Generate content based on grouping style
                        if grouping_style == "Multi-Item First, Then By Product (Recommended)":
                            # Section 1: Multi-item orders
                            if len(multi_item_orders) > 0:
                                elements.append(Paragraph("🔥 SECTION 1: MULTI-ITEM ORDERS (Pack Complete Orders)", section_style))
                                elements.append(Spacer(1, 8))
                                elements.append(Paragraph("⚠️ CRITICAL: Each order below contains multiple items - PACK ALL ITEMS TOGETHER", warning_style))
                                elements.append(Spacer(1, 12))
                                
                                # Process each multi-item order
                                for tracking_id in multi_item_orders:
                                    order_items = dataframe[dataframe['tracking-id'] == tracking_id]
                                    
                                    # Order header
                                    elements.append(Paragraph(f"📋 Order #{tracking_id} - COMPLETE ORDER", order_header_style))
                                    elements.append(Spacer(1, 4))
                                    
                                    # Items table
                                    table_data = [['Product', 'Qty', 'Pickup Date']]
                                    for _, item in order_items.iterrows():
                                        table_data.append([
                                            f"✅ {str(item['product-name'])[:50]}",
                                            str(item['qty']),
                                            str(item['pickup-slot'])[:15]
                                        ])
                                    
                                    # Add "PACK TOGETHER" row
                                    table_data.append(['📦 PACK ALL ITEMS TOGETHER - DO NOT SPLIT!', '', ''])
                                    
                                    table = Table(table_data, colWidths=[250, 60, 100])
                                    table.setStyle(TableStyle([
                                        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                                        ('BACKGROUND', (0, -1), (-1, -1), colors.lightcoral),  # Pack together row
                                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                                        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),  # Pack together row
                                        ('FONTSIZE', (0, 0), (-1, -1), 10),
                                        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                                        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                                        ('TEXTCOLOR', (0, -1), (-1, -1), colors.red),  # Pack together row
                                    ]))
                                    elements.append(table)
                                    elements.append(Spacer(1, 12))
                                
                                # Add extra space before single items section (no page break)
                                elements.append(Spacer(1, 20))
                            
                            # Section 2: Single-item orders (current grouping)
                            elements.append(Paragraph("✅ SECTION 2: SINGLE-ITEM ORDERS (Group by Product)", section_style))
                            elements.append(Spacer(1, 12))
                            
                            # Filter out multi-item orders
                            single_item_df = dataframe[~dataframe['tracking-id'].isin(multi_item_orders)]
                            
                            if not single_item_df.empty:
                                grouped = single_item_df.groupby('product-name')
                                for product_name, group in grouped:
                                    elements.append(Paragraph(f"📦 {str(product_name).upper()}", product_header_style))
                                    elements.append(Spacer(1, 4))
                                    
                                    table_data = [['Tracking ID', 'Qty', 'Pickup Date']]
                                    for _, row in group.iterrows():
                                        table_data.append([
                                            str(row['tracking-id'])[-12:],  # Last 12 characters
                                            str(row['qty']),
                                            str(row['pickup-slot'])[:15]
                                        ])

                                    table = Table(table_data, colWidths=[180, 60, 90])
                                    table.hAlign = 'LEFT'
                                    table.setStyle(TableStyle([
                                        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                                        ('FONTSIZE', (0, 0), (-1, -1), 10),
                                        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                                        ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
                                    ]))
                                    
                                    # Highlight high quantity orders
                                    for i, row in enumerate(group.itertuples(), start=1):
                                        if getattr(row, 'highlight', False):
                                            table.setStyle(TableStyle([
                                                ('BACKGROUND', (1, i), (1, i), colors.lightgrey),
                                                ('FONTNAME', (1, i), (1, i), 'Helvetica-Bold')
                                            ]))

                                    block = KeepTogether([table, Spacer(1, 8)])
                                    elements.append(block)
                            else:
                                elements.append(Paragraph("No single-item orders found.", styles['Normal']))

                        elif grouping_style == "By Product with Multi-Item Warnings":
                            # Current grouping with warnings
                            grouped = dataframe.groupby('product-name')
                            for product_name, group in grouped:
                                elements.append(Paragraph(f"📦 {str(product_name).upper()}", product_header_style))
                                elements.append(Spacer(1, 4))
                                
                                table_data = [['Tracking ID', 'Qty', 'Pickup Date', 'Order Type']]
                                for _, row in group.iterrows():
                                    order_type = "⚠️ MULTI-ITEM" if row['tracking-id'] in multi_item_orders else "✅ Single Item"
                                    
                                    # Add additional info for multi-item orders
                                    if row['tracking-id'] in multi_item_orders:
                                        other_items = dataframe[(dataframe['tracking-id'] == row['tracking-id']) & 
                                                       (dataframe['product-name'] != product_name)]['product-name'].tolist()
                                        if other_items:
                                            order_type += f" - ALSO HAS: {', '.join(other_items[:2])}"
                                    
                                    table_data.append([
                                        str(row['tracking-id'])[-12:],
                                        str(row['qty']),
                                        str(row['pickup-slot'])[:15],
                                        order_type[:60]  # Truncate long text
                                    ])

                                table = Table(table_data, colWidths=[100, 40, 80, 180])
                                table.hAlign = 'LEFT'
                                table_style = TableStyle([
                                    ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                                    ('FONTSIZE', (0, 0), (-1, -1), 9),
                                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                                    ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
                                ])
                                
                                # Highlight multi-item rows
                                for i, (idx, row) in enumerate(group.iterrows(), start=1):
                                    if row['tracking-id'] in multi_item_orders:
                                        table_style.add('BACKGROUND', (0, i), (-1, i), colors.lightyellow)
                                        table_style.add('TEXTCOLOR', (3, i), (3, i), colors.red)
                                
                                table.setStyle(table_style)
                                elements.append(table)
                                elements.append(Spacer(1, 8))

                        else:  # Default: By Product Only (Original)
                            grouped = dataframe.groupby('product-name')
                            for product_name, group in grouped:
                                elements.append(Paragraph(f"📦 {str(product_name).upper()}", product_header_style))
                                elements.append(Spacer(1, 4))
                                
                                table_data = [['Tracking ID', 'Qty', 'Pickup Date']]
                                for _, row in group.iterrows():
                                    table_data.append([
                                        str(row['tracking-id'])[-12:],
                                        str(row['qty']),
                                        str(row['pickup-slot'])[:15]
                                    ])

                                table = Table(table_data, colWidths=[180, 60, 90])
                                table.hAlign = 'LEFT'
                                table.setStyle(TableStyle([
                                    ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                                    ('FONTSIZE', (0, 0), (-1, -1), 10),
                                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                                    ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
                                ]))

                                # Highlight high quantity orders
                                for i, row in enumerate(group.itertuples(), start=1):
                                    if getattr(row, 'highlight', False):
                                        table.setStyle(TableStyle([
                                            ('BACKGROUND', (1, i), (1, i), colors.lightgrey),
                                            ('FONTNAME', (1, i), (1, i), 'Helvetica-Bold')
                                        ]))

                                block = KeepTogether([table, Spacer(1, 8)])
                                elements.append(block)

                        # Build PDF
                        doc.build(elements)
                        buffer.seek(0)
                        return buffer
                        
                    except Exception as e:
                        logger.error(f"Error generating PDF: {str(e)}")
                        st.error(f"Error generating PDF: {str(e)}")
                        return None

                # PDF generation button
                if st.button("Generate PDF Report", use_container_width=True):
                    with st.spinner("Generating enhanced report..."):
                        pdf_buffer = generate_grouped_pdf(df, orientation, grouping_style, multi_item_orders)
                        
                        if pdf_buffer:
                            # Generate filename based on grouping style
                            if "Multi-Item" in grouping_style:
                                style_suffix = "MultiItem"
                            elif "Warnings" in grouping_style:
                                style_suffix = "WithWarnings"
                            else:
                                style_suffix = "Standard"
                                
                            filename = f"EasyShip_{style_suffix}_{len(df)}_Orders_{date.today().strftime('%Y%m%d')}.pdf"
                            
                            st.download_button(
                                label="Download Enhanced PDF",
                                data=pdf_buffer,
                                file_name=filename,
                                mime="application/pdf",
                                use_container_width=True
                            )
                            st.caption("PDF generated successfully")
                        else:
                            st.error("Failed to generate PDF. Please try again.")

                # Excel export option
                if st.button("Generate Excel Export", use_container_width=True):
                    try:
                        excel_buffer = BytesIO()
                        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                            # Export main data
                            export_df = df.drop(columns=['highlight'], errors='ignore')
                            export_df.to_excel(writer, index=False, sheet_name="Easy Ship Orders")
                            
                            # Export multi-item orders summary
                            if multi_item_orders:
                                multi_item_summary = []
                                for tracking_id in multi_item_orders:
                                    order_items = df[df['tracking-id'] == tracking_id]
                                    items_list = order_items['product-name'].tolist()
                                    multi_item_summary.append({
                                        'tracking-id': tracking_id,
                                        'item_count': len(items_list),
                                        'products': ', '.join(items_list),
                                        'total_qty': order_items['qty'].sum(),
                                        'pickup_date': order_items['pickup-slot'].iloc[0]
                                    })
                                
                                summary_df = pd.DataFrame(multi_item_summary)
                                summary_df.to_excel(writer, index=False, sheet_name="Multi-Item Orders")
                            
                            # Export summary by product
                            product_summary = df.groupby('product-name').agg({
                                'qty': 'sum',
                                'tracking-id': 'count'
                            }).rename(columns={'tracking-id': 'order_count'}).reset_index()
                            product_summary.to_excel(writer, index=False, sheet_name="Summary by Product")
                        
                        excel_buffer.seek(0)
                        filename = f"Easy_Ship_Data_{len(df)}_Orders_{date.today().strftime('%Y%m%d')}.xlsx"
                        st.download_button(
                            label="Download Excel",
                            data=excel_buffer,
                            file_name=filename,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )
                    except Exception as e:
                        st.error(f"Error generating Excel: {str(e)}")

            except Exception as e:
                logger.error(f"Error processing data: {str(e)}")
                st.error(f"Error processing data: {str(e)}")

        except Exception as e:
            logger.error(f"Error processing file: {str(e)}")
            st.error(f"❌ Error processing file: {str(e)}")
            st.info("Please ensure the file is a valid Excel file with the correct format.")
