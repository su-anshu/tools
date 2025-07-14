import streamlit as st
import pandas as pd
import os
from fpdf import FPDF
from datetime import datetime
import logging
from app.sidebar import sidebar_controls, load_master_data, MANUAL_PLAN_FILE

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

def manual_packing_plan():
    st.title("🔖 Manual Packing Plan Generator")
    sidebar_controls()

    def process_uploaded_file(path):
        """Process uploaded Excel file with improved error handling"""
        try:
            if not os.path.exists(path):
                raise FileNotFoundError(f"File not found: {path}")
                
            xl = pd.ExcelFile(path)
            if not xl.sheet_names:
                raise ValueError("No sheets found in Excel file")
                
            df = xl.parse(xl.sheet_names[0])
            df.columns = df.columns.str.strip()

            # Add missing columns with safe defaults
            if 'Pouch Size' not in df.columns:
                df['Pouch Size'] = "N/A"
            if 'ASIN' not in df.columns:
                df['ASIN'] = "N/A"

            df['Total Weight Sold (kg)'] = None
            current_parent = None
            parent_indices = []

            # Process rows to calculate weights
            for idx, row in df.iterrows():
                try:
                    item = str(row.get('Row Labels', '')).strip()
                    if not item.replace('.', '', 1).isdigit():
                        current_parent = item
                        parent_indices.append(idx)
                    else:
                        try:
                            weight = float(item)
                            units = row.get('Sum of Units Ordered', 0)
                            if pd.notna(units):
                                df.at[idx, 'Total Weight Sold (kg)'] = weight * units
                        except (ValueError, TypeError):
                            logger.warning(f"Could not process weight for row {idx}: {item}")
                except Exception as e:
                    logger.error(f"Error processing row {idx}: {str(e)}")
                    continue

            # Calculate parent totals
            for idx in parent_indices:
                try:
                    total = 0
                    for next_idx in range(idx + 1, len(df)):
                        if next_idx >= len(df):
                            break
                        next_item = str(df.at[next_idx, 'Row Labels']).strip()
                        if not next_item.replace('.', '', 1).isdigit():
                            break
                        weight = df.at[next_idx, 'Total Weight Sold (kg)']
                        if pd.notna(weight):
                            total += weight
                    df.at[idx, 'Total Weight Sold (kg)'] = total
                except Exception as e:
                    logger.error(f"Error calculating parent total for index {idx}: {str(e)}")

            # Calculate contribution percentages
            df['Contribution %'] = None
            current_parent_total = None

            for idx, row in df.iterrows():
                try:
                    item = str(row.get('Row Labels', '')).strip()
                    if not item.replace('.', '', 1).isdigit():
                        current_parent_total = row.get('Total Weight Sold (kg)')
                    else:
                        try:
                            weight = row.get('Total Weight Sold (kg)')
                            if (pd.notna(weight) and pd.notna(current_parent_total) and 
                                current_parent_total != 0 and weight != 0):
                                contribution = (weight / current_parent_total) * 100
                                df.at[idx, 'Contribution %'] = round(contribution, 2)
                        except (ValueError, TypeError, ZeroDivisionError):
                            logger.warning(f"Could not calculate contribution for row {idx}")
                except Exception as e:
                    logger.error(f"Error calculating contribution for row {idx}: {str(e)}")

            return df
        except Exception as e:
            logger.error(f"Error processing uploaded file: {str(e)}")
            st.error(f"Error processing file: {str(e)}")
            return None

    def round_to_nearest_2(x):
        """Round to nearest 2 with validation"""
        try:
            if pd.isna(x) or x is None:
                return 0
            return int(2 * round(float(x) / 2))
        except (ValueError, TypeError):
            return 0

    def adjust_packets(result_df, target_weight):
        """Adjust packet counts to meet target weight with improved logic"""
        try:
            if result_df.empty or target_weight <= 0:
                return result_df
                
            max_iterations = 100  # Prevent infinite loops
            iteration = 0
            
            while iteration < max_iterations:
                packed_weight = result_df['Weight Packed (kg)'].sum()
                deviation = (target_weight - packed_weight) / target_weight if target_weight > 0 else 0

                if abs(deviation) <= 0.05:  # Within 5% tolerance
                    break
                    
                try:
                    if packed_weight > target_weight:
                        # Reduce packets from highest variation
                        if 'Variation (kg)' in result_df.columns:
                            idx = result_df['Variation (kg)'].idxmax()
                            if result_df.at[idx, 'Packets to Pack'] >= 2:
                                result_df.at[idx, 'Packets to Pack'] -= 2
                    elif deviation > 0:
                        # Add packets to lowest variation
                        if 'Variation (kg)' in result_df.columns:
                            idx = result_df['Variation (kg)'].idxmin()
                            result_df.at[idx, 'Packets to Pack'] += 2
                    else:
                        break

                    # Recalculate weights
                    result_df['Weight Packed (kg)'] = (
                        result_df['Variation (kg)'] * result_df['Packets to Pack']
                    )
                    iteration += 1
                except Exception as e:
                    logger.error(f"Error in adjustment iteration {iteration}: {str(e)}")
                    break

            return result_df
        except Exception as e:
            logger.error(f"Error adjusting packets: {str(e)}")
            return result_df

    def generate_combined_pdf(packing_summary, combined_total, combined_loose):
        """Generate PDF with improved error handling"""
        try:
            pdf = FPDF()
            pdf.add_page()

            # Header
            pdf.set_font("Arial", "B", 14)
            pdf.cell(200, 10, "Mithila Foods Packing Plan", ln=True, align="C")
            pdf.set_font("Arial", size=11)
            pdf.cell(200, 10, f"Date: {datetime.now().strftime('%d-%m-%Y')}", ln=True, align="C")
            pdf.ln(5)

            # Process each item block
            for item_block in packing_summary:
                try:
                    pdf.set_font("Arial", "B", 12)
                    item_name = str(item_block.get('item', 'Unknown'))[:50]  # Truncate long names
                    pdf.cell(200, 10, f"Item: {item_name}", ln=True)
                    
                    pdf.set_font("Arial", size=11)
                    target_weight = item_block.get('target_weight', 0)
                    packed_weight = item_block.get('packed_weight', 0)
                    loose_weight = item_block.get('loose_weight', 0)
                    
                    pdf.cell(200, 8, f"Target: {target_weight} kg | Packed: {packed_weight:.2f} kg | Loose: {loose_weight:.2f} kg", ln=True)

                    # Table headers
                    pdf.set_font("Arial", size=10)
                    pdf.cell(30, 8, "Variation", border=1)
                    pdf.cell(35, 8, "Pouch Size", border=1)
                    pdf.cell(45, 8, "ASIN", border=1)
                    pdf.cell(30, 8, "Packets", border=1)
                    pdf.cell(40, 8, "Packed (kg)", border=1)
                    pdf.ln()

                    # Table data
                    data = item_block.get('data', pd.DataFrame())
                    if not data.empty:
                        for _, row in data.iterrows():
                            try:
                                variation = str(row.get('Variation (kg)', 'N/A'))[:8]
                                pouch_size = str(row.get('Pouch Size', 'N/A'))[:12]
                                asin = str(row.get('ASIN', 'N/A'))[:15]
                                packets = str(int(row.get('Packets to Pack', 0)))
                                packed = f"{row.get('Weight Packed (kg)', 0):.2f}"
                                
                                pdf.cell(30, 8, variation, border=1)
                                pdf.cell(35, 8, pouch_size, border=1)
                                pdf.cell(45, 8, asin, border=1)
                                pdf.cell(30, 8, packets, border=1)
                                pdf.cell(40, 8, packed, border=1)
                                pdf.ln()
                            except Exception as e:
                                logger.error(f"Error adding row to PDF: {str(e)}")
                                continue
                    
                    pdf.ln(5)
                except Exception as e:
                    logger.error(f"Error processing item block: {str(e)}")
                    continue

            # Summary
            pdf.set_font("Arial", "B", 12)
            pdf.cell(200, 10, f"TOTAL PACKED: {combined_total:.2f} kg | TOTAL LOOSE: {combined_loose:.2f} kg", ln=True, align="C")
            
            # Return PDF as bytes
            try:
                pdf_output = pdf.output(dest="S")
                if isinstance(pdf_output, str):
                    return pdf_output.encode("latin1")
                else:
                    return pdf_output
            except Exception as e:
                logger.error(f"Error generating PDF output: {str(e)}")
                # Fallback
                return pdf.output(dest="S").encode("latin1", errors="ignore")
                
        except Exception as e:
            logger.error(f"Error generating PDF: {str(e)}")
            return None

    # Main logic
    if not os.path.exists(MANUAL_PLAN_FILE):
        st.error("❌ No manual packing plan uploaded via sidebar.")
        st.info("Please upload the 'latest_packing_plan.xlsx' file using the sidebar.")
        return

    try:
        df_full = process_uploaded_file(MANUAL_PLAN_FILE)
        if df_full is None:
            return
            
        if df_full.empty:
            st.warning("The uploaded file appears to be empty.")
            return

        # Extract parent items (non-numeric row labels)
        try:
            parent_items = []
            for label in df_full.get('Row Labels', []):
                label_str = str(label).strip()
                if label_str and not label_str.replace('.', '', 1).isnumeric():
                    parent_items.append(label_str)
            
            if not parent_items:
                st.warning("No parent items found in the data. Please check the file format.")
                return
                
        except Exception as e:
            st.error(f"Error extracting parent items: {str(e)}")
            return

        # Item selection
        selected_items = st.multiselect("Select Items to Pack:", parent_items)
        if not selected_items:
            st.info("Please select items to generate packing plan.")
            return

        packing_summary = []
        total_combined_weight = 0
        total_combined_loose = 0

        # Process each selected item
        for selected_item in selected_items:
            try:
                st.subheader(f"📦 {selected_item}")
                target_weight = st.number_input(
                    f"Enter weight to pack for {selected_item} (kg):", 
                    min_value=1, 
                    value=100, 
                    step=10,
                    key=f"weight_{selected_item}"
                )

                # Find parent item index
                try:
                    idx_parent = df_full[df_full['Row Labels'] == selected_item].index
                    if len(idx_parent) == 0:
                        st.warning(f"Could not find data for {selected_item}")
                        continue
                    idx_parent = idx_parent[0]
                except Exception as e:
                    st.error(f"Error finding parent item {selected_item}: {str(e)}")
                    continue

                # Extract variations
                variations = []
                try:
                    for i in range(idx_parent + 1, len(df_full)):
                        if i >= len(df_full):
                            break
                        label = str(df_full.at[i, 'Row Labels']).strip()
                        if not label.replace('.', '', 1).isdigit():
                            break
                        
                        try:
                            variation_data = {
                                'Variation (kg)': float(label),
                                'Contribution %': df_full.at[i, 'Contribution %'] or 0,
                                'Pouch Size': df_full.at[i, 'Pouch Size'] or "N/A",
                                'ASIN': df_full.at[i, 'ASIN'] or "N/A"
                            }
                            variations.append(variation_data)
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Could not process variation {label}: {str(e)}")
                            continue
                except Exception as e:
                    st.error(f"Error extracting variations for {selected_item}: {str(e)}")
                    continue

                if not variations:
                    st.warning(f"No variations found for {selected_item}")
                    continue

                # Calculate packets
                result = []
                for var in variations:
                    try:
                        contribution = var.get('Contribution %', 0)
                        variation_kg = var.get('Variation (kg)', 1)
                        
                        if contribution > 0 and variation_kg > 0:
                            packets = (contribution / 100) * target_weight / variation_kg
                            packets = round_to_nearest_2(packets)
                        else:
                            packets = 0
                            
                        weight_packed = packets * variation_kg
                        
                        result.append({
                            'Variation (kg)': variation_kg,
                            'Pouch Size': var.get('Pouch Size', 'N/A'),
                            'ASIN': var.get('ASIN', 'N/A'),
                            'Packets to Pack': packets,
                            'Weight Packed (kg)': weight_packed
                        })
                    except Exception as e:
                        logger.error(f"Error calculating packets for variation: {str(e)}")
                        continue

                if not result:
                    st.warning(f"Could not calculate packing plan for {selected_item}")
                    continue

                # Create result DataFrame and adjust
                result_df = pd.DataFrame(result)
                result_df = adjust_packets(result_df, target_weight)
                
                packed_weight = result_df['Weight Packed (kg)'].sum()
                loose_weight = max(0, target_weight - packed_weight)

                # Display results
                display_columns = ['Variation (kg)', 'Pouch Size', 'ASIN', 'Packets to Pack', 'Weight Packed (kg)']
                st.dataframe(result_df[display_columns])
                
                # Store for PDF generation
                packing_summary.append({
                    'item': selected_item,
                    'target_weight': target_weight,
                    'packed_weight': packed_weight,
                    'loose_weight': loose_weight,
                    'data': result_df
                })

                total_combined_weight += packed_weight
                total_combined_loose += loose_weight

            except Exception as e:
                logger.error(f"Error processing {selected_item}: {str(e)}")
                st.error(f"Error processing {selected_item}: {str(e)}")
                continue

        # Generate PDF if we have data
        if packing_summary:
            try:
                pdf_data = generate_combined_pdf(packing_summary, total_combined_weight, total_combined_loose)
                if pdf_data:
                    st.download_button(
                        "📄 Download Combined Packing Plan PDF", 
                        data=pdf_data, 
                        file_name="MithilaFoods_PackingPlan.pdf", 
                        mime="application/pdf"
                    )
                    
                    # Display summary
                    st.success(f"✅ Packing plan generated for {len(selected_items)} items")
                    st.info(f"📊 Total Packed: {total_combined_weight:.2f} kg | Total Loose: {total_combined_loose:.2f} kg")
                else:
                    st.error("Failed to generate PDF. Please try again.")
            except Exception as e:
                st.error(f"Error generating PDF: {str(e)}")
        else:
            st.warning("No valid packing data to generate PDF.")

    except Exception as e:
        logger.error(f"Unexpected error in manual packing plan: {str(e)}")
        st.error(f"An unexpected error occurred: {str(e)}")
