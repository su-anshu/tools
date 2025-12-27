import streamlit as st
import pandas as pd
import io
from reportlab.pdfgen import canvas
from reportlab.lib.colors import black
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from app.data_loader import load_nutrition_data
import os

# Font path validation
FONTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "fonts")
if not os.path.exists(FONTS_DIR):
    FONTS_DIR = "fonts"  # Fallback to relative path



class NutritionLabel:
    def __init__(self):
        # Small label dimensions: 45mm x 35mm at 300 DPI
        # Convert mm to points: 1mm = 2.834645669 points
        self.width_mm = 45
        self.height_mm = 33
        self.dpi = 400
        
        # Convert to points for ReportLab
        self.width = self.width_mm * 2.834645669
        self.height = self.height_mm * 2.834645669
        self.margin = 3
        
        # Register custom font
        self.setup_custom_font()
        
    def setup_custom_font(self):
        """Register custom font from fonts folder"""
        try:
            font_path = "fonts/Helvetica-Black.ttf"
            if os.path.exists(font_path):
                pdfmetrics.registerFont(TTFont("Helvetica-Black", font_path))
                self.has_custom_font = True
            else:
                self.has_custom_font = False
        except Exception as e:
            self.has_custom_font = False
        
    def format_value(self, value):
        """Format nutritional values"""
        if pd.isna(value) or value == 0:
            return "0"
        if value == int(value):
            return str(int(value))
        return f"{value:.1f}".rstrip('0').rstrip('.')
    
    def draw_centered_text(self, c, text, x, y):
        """Draw text centered at x position"""
        text_width = c.stringWidth(text, c._fontname, c._fontsize)
        c.drawString(x - text_width/2, y, text)
    
    def create_pdf(self, data):
        """Generate nutrition label PDF with 4 columns per row"""
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=(self.width, self.height))
        
        # Positions
        x_left = self.margin
        x_right = self.width - self.margin
        x_center = self.width / 2
        y = self.height - 10
        
        # Border removed for clean look
        # c.setStrokeColor(black)
        # c.setLineWidth(1)
        # c.rect(0, 0, self.width, self.height)
        
        # Title: "Nutritional Facts Per 100g (Approx Values)" - using custom font
        if self.has_custom_font:
            c.setFont("Helvetica-Black", 5)
        else:
            c.setFont("Helvetica-Bold", 6)
        title1 = "Nutritional Facts Per 100g (Approx Values)"
        self.draw_centered_text(c, title1, x_center, y)
        y -= 8
        
        # Serving size
        c.setFont("Helvetica-Bold", 6)
        serving_text = f"Serving size {data.get('Serving Size', '30g (~2 tbsp)')}"
        self.draw_centered_text(c, serving_text, x_center, y)
        y -= 6
        
        #serving-info
        c.setFont("Helvetica-Bold", 3.5)
        serving_info = f"Number of servings may vary based on pack size and intended use"
        self.draw_centered_text(c, serving_info, x_center, y)
        y -= 3

        # Thick horizontal line (restored - this is needed for nutrition layout)
        #c.setLineWidth(.5)
        #c.line(x_left, y, x_right, y)
        y -= 8
        
        # Energy Value - centered large text
        c.setFont("Helvetica-Bold", 7)
        energy_val = f"Energy Value - {self.format_value(data.get('Energy', 345))} Kcal"
        self.draw_centered_text(c, energy_val, x_center, y)
        y -= 8
        
        # Four columns layout - headers
        col_width = (self.width - 2 * self.margin) / 4
        col1_x = x_left + col_width * 0.5
        col2_x = x_left + col_width * 1.5
        col3_x = x_left + col_width * 2.5
        col4_x = x_left + col_width * 3.5
        
        # First row headers (4 columns)
        c.setFont("Helvetica-Bold", 4)
        self.draw_centered_text(c, "Total Fat", col1_x, y)
        self.draw_centered_text(c, "Saturated Fat", col2_x, y)
        self.draw_centered_text(c, "Trans Fat", col3_x, y)
        self.draw_centered_text(c, "Cholesterol", col4_x, y)
        y -= 7
        
        # First row values
        c.setFont("Helvetica-Bold", 6)
        total_fat = f"{self.format_value(data.get('Total Fat', 5))}g"
        sat_fat = f"{self.format_value(data.get('Saturated Fat', 10))}g"
        trans_fat = f"{self.format_value(data.get('Trans Fat', 0))}g"
        cholesterol = f"{self.format_value(data.get('Cholesterol', 0))}mg"
        
        self.draw_centered_text(c, total_fat, col1_x, y)
        self.draw_centered_text(c, sat_fat, col2_x, y)
        self.draw_centered_text(c, trans_fat, col3_x, y)
        self.draw_centered_text(c, cholesterol, col4_x, y)
        y -= 7
        
        # Second row headers (4 columns - All carb-related)
        c.setFont("Helvetica-Bold", 4)
        self.draw_centered_text(c, "Total Carbs", col1_x, y)
        self.draw_centered_text(c, "Dietary Fibers", col2_x, y)
        self.draw_centered_text(c, "Total Sugars", col3_x, y)
        self.draw_centered_text(c, "Added Sugars", col4_x, y)
        y -= 7
        
        # Second row values
        c.setFont("Helvetica-Bold", 6)
        carbs = f"{self.format_value(data.get('Total Carbohydrate', 5))}g"
        fiber = f"{self.format_value(data.get('Dietary Fiber', 10))}g"
        total_sugars = f"{self.format_value(data.get('Total Sugars', 8))}g"
        added_sugars = f"{self.format_value(data.get('Added Sugars', 2))}g"
        
        self.draw_centered_text(c, carbs, col1_x, y)
        self.draw_centered_text(c, fiber, col2_x, y)
        self.draw_centered_text(c, total_sugars, col3_x, y)
        self.draw_centered_text(c, added_sugars, col4_x, y)
        y -= 7
        
        # Third row headers (2 columns - Sodium and Protein)
        c.setFont("Helvetica-Bold", 4)
        self.draw_centered_text(c, "Sodium", col1_x, y)
        self.draw_centered_text(c, "Protein", col2_x, y)
        y -= 7
        
        # Third row values
        c.setFont("Helvetica-Bold", 6)
        sodium = f"{self.format_value(data.get('Sodium(mg)', 2))}mg"
        protein = f"{self.format_value(data.get('Protein', 5))}g"
        
        self.draw_centered_text(c, sodium, col1_x, y)
        self.draw_centered_text(c, protein, col2_x, y)
        y -= 7
        
        # Daily Value footnote - positioned below Sodium, spanning to Added Sugars column
        c.setFont("Helvetica", 4)
        footnote_lines = [
            "* The % Daily Value (DV) tells you how much a nutrient in a ",
            "                  serving of food contributes to a daily diet."
            
        ]
        
        # Start from Sodium position (col1_x) and span towards Added Sugars area
        footnote_start_x = col1_x - 10  # Align with Sodium column
        for line in footnote_lines:
            c.drawString(footnote_start_x, y, line)
            y -= 5
        
        c.showPage()
        c.save()
        return buffer.getvalue()
    
    def get_label_info(self):
        """Get label dimensions info"""
        return {
            "width_mm": self.width_mm,
            "height_mm": self.height_mm,
            "dpi": self.dpi
        }

def main():
    st.set_page_config(page_title="Nutrition Label Generator - Mithila Tools", layout="centered")
    
    st.title("🥗 Nutrition Label Generator (4 Column Layout)")
    st.markdown("Generate nutrition labels from MRP spreadsheet's nutritional data")
    st.info("📊 **Data Source:** MRP Spreadsheet → 'nutritional' sheet (GID: 1800176856)")
    
    # Load data from Google Sheets
    with st.spinner("Loading nutrition data..."):
        df = load_nutrition_data()
    
    if df is None:
        st.error("❌ Failed to load data from Google Sheets")
        st.info("Please check your internet connection and try again.")
        return
    
    if df.empty:
        st.warning("⚠️ No products found in the Google Sheets")
        return
    
    # Show data source info
    st.success(f"✅ Loaded {len(df)} products from MRP spreadsheet (nutritional sheet)")
    
    # Product selection
    products = df["Product"].dropna().unique()
    selected_product = st.selectbox("Choose Product", products)
    
    if selected_product:
        # Get product data
        row = df[df["Product"] == selected_product].iloc[0]
        
        # Show product info
        col1, col2 = st.columns(2)
        with col1:
            st.info(f"**Product:** {selected_product}")
            st.info(f"**Serving Size:** {row.get('Serving Size', 'N/A')}")
        with col2:
            st.info(f"**Energy:** {row.get('Energy', 'N/A')} Kcal")
            st.info(f"**Protein:** {row.get('Protein', 'N/A')}g")
        
        # Prepare data for PDF generation - ALL nutrients from Google Sheets
        data = {
            "Serving Size": str(row.get("Serving Size", "30g (~2 tbsp)")),
            "Energy": row.get("Energy", 345),
            "Total Fat": row.get("Total Fat", 5),
            "Saturated Fat": row.get("Saturated Fat", 10),
            "Trans Fat": row.get("Trans Fat", 0),
            "Cholesterol": row.get("Cholesterol", 0),
            "Sodium(mg)": row.get("Sodium(mg)", 2),
            "Total Carbohydrate": row.get("Total Carbohydrate", 5),
            "Dietary Fiber": row.get("Dietary Fiber", 10),
            "Total Sugars": row.get("Total Sugars", 8),
            "Added Sugars": row.get("Added Sugars", 2),
            "Protein": row.get("Protein", 5)
        }
        
        # Generate label
        generator = NutritionLabel()
        label_info = generator.get_label_info()
        
        # Show label specifications
        st.info(f"📏 **Label Size:** {label_info['width_mm']}mm × {label_info['height_mm']}mm at {label_info['dpi']} DPI")
        
        try:
            pdf_bytes = generator.create_pdf(data)
            
            if pdf_bytes is None:
                st.error("❌ Failed to generate PDF")
                return
            
            # Single PDF download button
            st.download_button(
                label="⬇️ Download PDF Label (4 Column Layout)",
                data=pdf_bytes,
                file_name=f"{selected_product.replace(' ', '_')}_label_4col_45x35mm.pdf",
                mime="application/pdf",
                use_container_width=True
            )
            
            st.success(f"✅ Small label (45mm × 35mm) with 4-column layout ready for: **{selected_product}**")
            
        except Exception as e:
            st.error(f"❌ Label generation failed: {e}")
            st.info("Please try again or contact support")
    
    # Refresh data button
    if st.button("🔄 Refresh Nutritional Data"):
        st.cache_data.clear()
        st.rerun()
    
    # Show data preview
    with st.expander("📊 View All Products Data"):
        st.dataframe(df, use_container_width=True)

if __name__ == "__main__":
    main()
