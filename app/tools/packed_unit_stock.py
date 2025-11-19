import streamlit as st
import pandas as pd
import io
import matplotlib.pyplot as plt
from fpdf import FPDF

def is_number(s):
    """Check if a string is a number (SKU)."""
    try:
        float(str(s))
        return True
    except ValueError:
        return False

def is_sku_line(s):
    """Check if a line represents an SKU line (Number or 'In lot')."""
    s = str(s).strip()
    if s == "": return False
    if is_number(s): return True
    if "in lot" in s.lower(): return True
    if "sku+inlot" in s.lower(): return True
    return False

def is_text_line(s):
    """Check if a line is a text line (potential Category or Product)."""
    s = str(s).strip()
    if s == "" or s.lower() == "nan": return False
    return not is_sku_line(s)

def process_stock_data(file):
    """
    Parses the uploaded Excel/CSV file to extract Product Name, SKU, and Count.
    Logic:
    1. Iterate through rows.
    2. Identify Product Name (Text lines).
    3. Identify SKU (Numeric lines).
    4. Extract Count from Column Y (Index 24).
    5. Filter > 0 and exclude 'In Lot'.
    """
    try:
        # Determine file type and read
        if file.name.endswith('.csv'):
            df = pd.read_csv(file, header=None)
        else:
            df = pd.read_excel(file, header=None)
    except Exception as e:
        st.error(f"Error reading file: {e}")
        return pd.DataFrame()

    # Ensure we have enough columns (Column Y is index 24, so we need at least 25 cols)
    if df.shape[1] < 25:
        st.error("The uploaded file does not have enough columns. Expected at least 25 columns (Column Y).")
        return pd.DataFrame()

    rows = df.iloc[1:].copy().reset_index(drop=True)
    results = []
    current_product = "Unknown Product"

    i = 0
    while i < len(rows):
        row = rows.iloc[i]
        col_a = str(row[0]).strip()
        
        # Skip empty rows
        if col_a == "" or col_a.lower() == "nan":
            i += 1
            continue
            
        # --- SKU Line Logic ---
        if is_sku_line(col_a):
            # User Requirement: Exclude "In Lot" and "SKU+INLOT"
            if "in lot" in col_a.lower() or "sku+inlot" in col_a.lower():
                i += 1
                continue

            # Extract Count from Column Y (Index 24)
            col_y_raw = row[24]
            try:
                col_y = float(col_y_raw)
            except:
                col_y = 0.0
            
            if pd.isna(col_y): col_y = 0.0
            
            # Filter: Count must be > 0
            if col_y > 0:
                # Format quantity: integer if no decimal needed
                qty_val = int(col_y) if col_y.is_integer() else col_y
                
                # Format SKU/Unit: If >= 1 add "kg", if < 1 multiply by 1000 and add "g"
                try:
                    sku_val = float(col_a)
                    if sku_val >= 1:
                        # Format as kg with 2 decimal places
                        sku_formatted = f"{sku_val:.2f} kg"
                    else:
                        # Format as g with 2 decimal places (multiply by 1000)
                        grams = sku_val * 1000
                        sku_formatted = f"{grams:.2f} g"
                except:
                    # If SKU is not a number, keep original value
                    sku_formatted = col_a
                
                results.append({
                    "Product Name": current_product,
                    "SKU/Unit": sku_formatted,
                    "Count(Qty)": qty_val
                })
            i += 1
            continue
            
        # --- Product Name Logic ---
        # We need to determine if this text line is a Product or a Category.
        # Logic: Look ahead. If the NEXT non-empty line is an SKU (number), then THIS line is a Product.
        # If the NEXT line is also text, then THIS line is likely a Category (which we ignore).
        
        j = i + 1
        has_next = False
        next_is_sku = False
        
        while j < len(rows):
            next_val = str(rows.iloc[j, 0]).strip()
            if next_val != "" and next_val.lower() != "nan":
                has_next = True
                if is_sku_line(next_val):
                    next_is_sku = True
                else:
                    next_is_sku = False
                break
            j += 1
            
        if has_next:
            if next_is_sku:
                # Next line is a number, so this line is the Product Name
                current_product = col_a
            else:
                # Next line is text, so this line is likely a Category header.
                # We do nothing, just move on.
                pass
        else:
            # End of file, assume product if we found text
            current_product = col_a
            
        i += 1

    return pd.DataFrame(results)

def generate_pdf(dataframe):
    """Generates a simple PDF table from the dataframe."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', size=13)
    
    pdf.cell(200, 10, txt="Packed Unit Stocks", ln=True, align='C')
    pdf.ln(10)

    # Table Header
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(90, 10, "Product Name", 1)
    pdf.cell(50, 10, "SKU/Unit", 1)
    pdf.cell(40, 10, "Count(Qty)", 1)
    pdf.ln()

    # Table Rows
    pdf.set_font("Arial", 'B', size=11)
    for i, row in dataframe.iterrows():
        # Truncate long product names for PDF
        prod_name = str(row['Product Name'])
        if len(prod_name) > 45:
            prod_name = prod_name[:42] + "..."
            
        pdf.cell(90, 10, prod_name, 1)
        pdf.cell(50, 10, str(row['SKU/Unit']), 1)
        pdf.cell(40, 10, str(row['Count(Qty)']), 1)
        pdf.ln()
    
    # pdf.output(dest='S') returns bytes directly in fpdf2, no need to encode
    pdf_bytes = pdf.output(dest='S')
    # Ensure it's bytes (handle both bytes and bytearray)
    if isinstance(pdf_bytes, bytearray):
        return bytes(pdf_bytes)
    return pdf_bytes

def generate_png(dataframe):
    """Generates a PNG image of the table using Matplotlib."""
    # Estimate height based on rows (approx 0.3 inches per row + header + title)
    height = 1.5 + (len(dataframe) * 0.3)
    fig, ax = plt.subplots(figsize=(10, height))
    
    # Add heading at the top
    ax.text(0.5, 0.95, "Packed Unit Stocks", 
            transform=ax.transAxes, 
            fontsize=13, 
            fontweight='bold',
            ha='center', 
            va='top')
    
    ax.axis('off')
    
    table_data = [dataframe.columns.values.tolist()] + dataframe.values.tolist()
    
    # Position table below the heading (adjust y position)
    table = ax.table(cellText=table_data, colLabels=None, cellLoc='center', 
                     loc='upper center', bbox=[0, 0, 1, 0.85])
    table.set_fontsize(11)
    table.scale(1, 1.5) # Scale width and height
    
    # Style all cells - make bold
    for (i, j), cell in table.get_celld().items():
        cell.set_text_props(weight='bold')
        if i == 0:
            # Header row styling
            cell.set_text_props(weight='bold', color='white')
            cell.set_facecolor('#40466e')
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', dpi=150)
    plt.close(fig)  # Close figure to prevent memory leaks
    buf.seek(0)
    return buf

def packed_unit_stock():
    """Main function for Packed Unit Stock tool."""
    st.title("📊 Stock Sheet Processor")
    st.markdown("Upload your **Stock Count working.xlsx** or **.csv** file. The app will extract Product Names and SKUs with positive counts (excluding 'In Lot' items).")

    uploaded_file = st.file_uploader("Choose a file", type=['xlsx', 'csv'])

    if uploaded_file is not None:
        with st.spinner('Processing file...'):
            df_result = process_stock_data(uploaded_file)

        if not df_result.empty:
            st.success(f"Found {len(df_result)} records!")
            
            # Display Data
            st.dataframe(df_result, use_container_width=True)
            
            st.subheader("Downloads")
            col1, col2, col3 = st.columns(3)
            
            # CSV Download
            csv = df_result.to_csv(index=False).encode('utf-8')
            with col1:
                st.download_button(
                    label="📄 Download CSV",
                    data=csv,
                    file_name='stock_count_filtered.csv',
                    mime='text/csv',
                )
                
            # PDF Download
            try:
                pdf_bytes = generate_pdf(df_result)
                with col2:
                    st.download_button(
                        label="📕 Download PDF",
                        data=pdf_bytes,
                        file_name='stock_count_filtered.pdf',
                        mime='application/pdf',
                    )
            except Exception as e:
                with col2:
                    st.error(f"PDF Error: {e}")

            # PNG Download
            try:
                png_buffer = generate_png(df_result)
                with col3:
                    st.download_button(
                        label="🖼️ Download PNG",
                        data=png_buffer,
                        file_name='stock_count_filtered.png',
                        mime='image/png',
                    )
            except Exception as e:
                with col3:
                    st.error(f"PNG Error: {e}")
                    
        else:
            st.warning("No matching data found. Please check if the file format matches the requirement (Column A for Names/SKUs, Column Y for Count).")

