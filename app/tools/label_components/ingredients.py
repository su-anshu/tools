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



class IngredientsAllergenLabel:
    def __init__(self):
        # Label dimensions: 45mm x 25mm at 600 DPI
        # Convert mm to points: 1mm = 2.834645669 points
        self.width_mm = 45
        self.height_mm = 21
        self.dpi = 600
        
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
        
    def draw_centered_text(self, c, text, x, y):
        """Draw text centered at x position"""
        text_width = c.stringWidth(text, c._fontname, c._fontsize)
        c.drawString(x - text_width/2, y, text)
    
    def create_pdf(self, data):
        """Generate ingredients + allergen label PDF"""
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=(self.width, self.height))
        
        # Positions
        x_left = self.margin
        x_right = self.width - self.margin
        x_center = self.width / 2
        y = self.height - 8
        
        # Border removed for clean look
        # c.setStrokeColor(black)
        # c.setLineWidth(1)
        # c.rect(0, 0, self.width, self.height)
        
        # Title - Product Name (centered, bold)
        product_name = data.get('Product', 'Product Name')
        if self.has_custom_font:
            c.setFont("Helvetica-Black", 6.5)
        else:
            c.setFont("Helvetica-Bold", 8)
        self.draw_centered_text(c, product_name, x_center, y)
        y -= 8
        
        # Ingredients section
        ingredients_text = data.get('Ingredients', '')
        if ingredients_text:
            # Calculate available width (full canvas width)
            max_width = self.width - (2 * self.margin)
            
            # Calculate "Ingredients: " label width for first line
            ingredients_label_width = c.stringWidth("Ingredients: ", "Helvetica-Bold", 5)
            available_width_first_line = max_width - ingredients_label_width
            
            # Split ingredients text into lines
            words = ingredients_text.split()
            lines = []
            current_line = ""
            is_first_line = True
            
            for word in words:
                test_line = f"{current_line} {word}".strip()
                
                # Check width based on line type
                if is_first_line:
                    # First line - check with available space after "Ingredients: "
                    if c.stringWidth(test_line, "Helvetica", 5) <= available_width_first_line:
                        current_line = test_line
                    else:
                        if current_line:
                            lines.append(current_line)
                            is_first_line = False
                        current_line = word
                else:
                    # Continuation lines - use full width
                    if c.stringWidth(test_line, "Helvetica", 5) <= max_width:
                        current_line = test_line
                    else:
                        if current_line:
                            lines.append(current_line)
                        current_line = word
            
            if current_line:
                lines.append(current_line)
            
            # Draw ingredients lines
            for i, line in enumerate(lines):
                if i == 0:
                    # First line: "Ingredients:" in bold, then regular text
                    c.setFont("Helvetica-Bold", 5)
                    c.drawString(x_left, y, "Ingredients: ")
                    
                    # Rest of first line in regular font
                    c.setFont("Helvetica", 5)
                    c.drawString(x_left + ingredients_label_width, y, line)
                else:
                    # Continuation lines in regular font
                    c.setFont("Helvetica", 5)
                    c.drawString(x_left, y, line)
                y -= 5
            y -= 3  # Extra space after ingredients
        
        # Allergen Info section
        allergen_text = data.get('Allergen Info', '')
        if allergen_text:
            # Calculate available width (full canvas width)
            max_width = self.width - (2 * self.margin)
            
            # Calculate "Allergen Info: " label width for first line
            allergen_label_width = c.stringWidth("Allergen Info: ", "Helvetica-Bold", 5)
            available_width_first_line = max_width - allergen_label_width
            
            # Split allergen text into lines
            words = allergen_text.split()
            lines = []
            current_line = ""
            is_first_line = True
            
            for word in words:
                test_line = f"{current_line} {word}".strip()
                
                # Check width based on line type
                if is_first_line:
                    # First line - check with available space after "Allergen Info: "
                    if c.stringWidth(test_line, "Helvetica", 5) <= available_width_first_line:
                        current_line = test_line
                    else:
                        if current_line:
                            lines.append(current_line)
                            is_first_line = False
                        current_line = word
                else:
                    # Continuation lines - use full width
                    if c.stringWidth(test_line, "Helvetica", 5) <= max_width:
                        current_line = test_line
                    else:
                        if current_line:
                            lines.append(current_line)
                        current_line = word
            
            if current_line:
                lines.append(current_line)
            
            # Draw allergen info lines
            for i, line in enumerate(lines):
                if i == 0:
                    # First line: "Allergen Info:" in bold, then regular text
                    c.setFont("Helvetica-Bold", 5)
                    allergen_label_width = c.stringWidth("Allergen Info: ", "Helvetica-Bold", 5)
                    c.drawString(x_left, y, "Allergen Info: ")
                    
                    # Rest of first line in regular font
                    c.setFont("Helvetica", 5)
                    c.drawString(x_left + allergen_label_width, y, line)
                else:
                    # Continuation lines in regular font
                    c.setFont("Helvetica", 5)
                    c.drawString(x_left, y, line)
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
    st.set_page_config(page_title="Ingredients & Allergen Label Generator - Mithila Tools", layout="centered")
    
    st.title("📋 Ingredients & Allergen Label Generator")
    st.markdown("Generate ingredient and allergen labels from MRP spreadsheet's nutritional data")
    st.info("📊 **Data Source:** MRP Spreadsheet → 'nutritional' sheet")
    
    # Load data from Google Sheets
    with st.spinner("Loading product data..."):
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
            st.info(f"**Ingredients:** {str(row.get('Ingredients', 'N/A'))[:50]}...")
        with col2:
            st.info(f"**Label Size:** 45mm × 25mm")
            st.info(f"**Allergen Info:** {str(row.get('Allergen Info', 'N/A'))[:30]}...")
        
        # Prepare data for PDF generation
        data = {
            "Product": selected_product,
            "Ingredients": str(row.get("Ingredients", "")),
            "Allergen Info": str(row.get("Allergen Info", ""))
        }
        
        # Generate label
        generator = IngredientsAllergenLabel()
        label_info = generator.get_label_info()
        
        # Show label specifications
        st.info(f"📏 **Label Size:** {label_info['width_mm']}mm × {label_info['height_mm']}mm at {label_info['dpi']} DPI")
        
        try:
            pdf_bytes = generator.create_pdf(data)
            
            if pdf_bytes is None:
                st.error("❌ Failed to generate PDF")
                return
            
            # Download button
            st.download_button(
                label="⬇️ Download Ingredients & Allergen Label (PDF)",
                data=pdf_bytes,
                file_name=f"{selected_product.replace(' ', '_')}_ingredients_allergen_45x25mm.pdf",
                mime="application/pdf",
                use_container_width=True
            )
            
            st.success(f"✅ Ingredients & Allergen label (45mm × 25mm) ready for: **{selected_product}**")
            
        except Exception as e:
            st.error(f"❌ Label generation failed: {e}")
            st.info("Please try again or contact support")
    
    # Refresh data button
    if st.button("🔄 Refresh Nutritional Data"):
        st.cache_data.clear()
        st.rerun()
    
    # Show data preview
    with st.expander("📊 View All Products Data"):
        st.dataframe(df[['Product', 'Ingredients', 'Allergen Info']], use_container_width=True)

if __name__ == "__main__":
    main()
