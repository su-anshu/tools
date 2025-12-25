# Mithila Tools Dashboard - Comprehensive Project Analysis

## Executive Summary

**Mithila Tools Dashboard** is a Streamlit-based web application designed for warehouse management, order processing, and label generation for Mithila Foods. The application provides a suite of tools for processing Amazon Easy Ship and Flipkart orders, generating packing plans, creating labels, and managing inventory.

---

## 1. Project Architecture

### 1.1 Technology Stack
- **Framework**: Streamlit (Python web framework)
- **Data Processing**: Pandas, NumPy
- **PDF Processing**: PyMuPDF (fitz), ReportLab, FPDF2
- **Image Processing**: Pillow (PIL)
- **Barcode Generation**: python-barcode, qrcode
- **Data Sources**: Google Sheets API (via CSV export), Excel files
- **UI Styling**: Custom CSS, Tailwind CSS (optional via streamlit-tailwind)

### 1.2 Project Structure
```
project_root/
├── streamlit_app.py          # Main entry point (deployment)
├── app/
│   ├── main.py               # Alternative entry point
│   ├── data_loader.py        # Google Sheets & data loading
│   ├── session_state.py      # Session management
│   ├── default_data.py       # Default file initialization
│   ├── pdf_utils.py          # PDF utilities
│   ├── sidebar.py            # Sidebar controls & admin
│   ├── components/           # Reusable UI components
│   │   ├── dashboard_header.py
│   │   ├── file_upload.py
│   │   ├── searchable_table.py
│   │   └── toast.py
│   ├── tools/                # Main application tools
│   │   ├── packing_plan.py           # Amazon packing plan
│   │   ├── flipkart_packing_plan.py  # Flipkart packing plan
│   │   ├── easy_ship_report.py       # Amazon Easy Ship report
│   │   ├── flipkart_report.py        # Flipkart report
│   │   ├── label_generator.py       # Barcode/FNSKU labels
│   │   ├── product_label_generator.py # Product labels
│   │   ├── manual_packing_plan.py    # Manual packing plan
│   │   ├── packed_unit_stock.py      # Stock management
│   │   └── label_components/         # Label sub-components
│   │       ├── ingredients.py
│   │       └── nutritional.py
│   └── utils/                # Utility functions
│       └── ui_components.py  # UI helper functions
├── data/                     # Data files directory
│   ├── master_fnsku.pdf
│   ├── master_meta.txt
│   └── master_sheet_url.txt
└── fonts/                    # Custom fonts for labels
```

---

## 2. Core Features & Tools

### 2.1 Amazon Easy Ship Tools

#### **Amazon Packing Plan** (`packing_plan.py`)
- **Purpose**: Process Amazon invoice PDFs and generate packing plans
- **Key Features**:
  - PDF invoice parsing and extraction
  - ASIN-based product matching with master data
  - Product splitting logic (handles weight variants)
  - Quantity highlighting in PDFs
  - Physical packing plan generation
  - Missing product detection
  - Label generation integration
- **Input**: PDF invoice files
- **Output**: 
  - Excel packing plan
  - Highlighted PDF invoices
  - Label PDFs (optional)

#### **Easy Ship Report** (`easy_ship_report.py`)
- **Purpose**: Generate reports from Easy Ship data
- **Features**: Process shipping data and generate formatted reports

### 2.2 Flipkart Tools

#### **Flipkart Packing Plan** (`flipkart_packing_plan.py`)
- **Purpose**: Similar to Amazon packing plan but for Flipkart orders
- **Features**: 
  - Flipkart-specific order processing
  - Product matching and validation
  - Packing plan generation

#### **Flipkart Report** (`flipkart_report.py`)
- **Purpose**: Generate reports from Flipkart order data
- **Features**: Process Flipkart Excel files and generate reports

### 2.3 Label Generation Tools

#### **Label Generator** (`label_generator.py`)
- **Purpose**: Generate barcode/FNSKU labels for products
- **Features**:
  - Barcode generation (Code128, EAN, etc.)
  - FNSKU label creation
  - Combined label PDFs
  - Vertical/horizontal layouts
  - Batch label generation

#### **Product Label Generator** (`product_label_generator.py`)
- **Purpose**: Generate product information labels
- **Features**:
  - Product name labels
  - Pair labels (two products per label)
  - Date inclusion
  - Custom formatting

### 2.4 Additional Tools

#### **Manual Packing Plan** (`manual_packing_plan.py`)
- **Purpose**: Create packing plans manually from Excel files
- **Features**: Manual data entry and plan generation

#### **Packed Unit Stock** (`packed_unit_stock.py`)
- **Purpose**: Track and manage packed unit stock
- **Features**: Stock processing and reporting

---

## 3. Data Management

### 3.1 Master Data Source
- **Primary**: Google Sheets (live data via CSV export)
- **Fallback**: Local Excel file (`data/temp_master.xlsx`)
- **URL Configuration**: Stored in `data/master_sheet_url.txt`
- **Default URL**: Hardcoded fallback URL in `data_loader.py`

### 3.2 Master Data Structure
Key fields expected in master data:
- `Name`: Product name
- `ASIN`: Amazon ASIN code
- `FNSKU`: Fulfillment Network SKU
- `Net Weight`: Product weight
- `Split Into`: Comma-separated split sizes (e.g., "0.35, 0.35")
- `Packet Size`, `Packet used`, `MRP`, `FSSAI`: Additional product info

### 3.3 Data Loading Strategy
1. **First Attempt**: Load from Google Sheets URL (if configured)
2. **Second Attempt**: Load from default Google Sheets URL
3. **Fallback**: Load from local Excel file
4. **Caching**: 5-minute TTL cache for performance

### 3.4 Nutritional Data
- Separate Google Sheet tab (GID: 1800176856)
- Used for nutritional label generation
- Loaded separately from main master data

---

## 4. Key Algorithms & Logic

### 4.1 Product Split Logic
**Documentation**: `SPLIT_LOGIC_DOCUMENTATION.md`

**Purpose**: Handle products that need to be split into multiple weight variants

**Process**:
1. Check if product has "Split Into" field
2. Parse comma-separated split sizes
3. For each split size, find matching variant in master data
4. Create physical rows for each split variant
5. Preserve original product name with weight for display
6. Use variant-specific FNSKU and properties

**Example**:
- Product: "Coconut Thekua" (0.7kg)
- Split Into: "0.35, 0.35"
- Result: Two physical items of 0.35kg each

### 4.2 PDF Processing
- **Library**: PyMuPDF (fitz)
- **Features**:
  - Text extraction from PDFs
  - Table detection and parsing
  - Quantity highlighting
  - PDF sorting by ASIN
  - Safe PDF context management

### 4.3 Order Processing Flow
1. Upload invoice PDF(s)
2. Extract order data (ASIN, quantities)
3. Match with master data by ASIN
4. Apply split logic if needed
5. Generate physical packing plan
6. Highlight large quantities in PDF
7. Generate labels (optional)
8. Export Excel and PDF files

---

## 5. User Interface

### 5.1 Navigation Structure
- **Sidebar Navigation**: Collapsible menu groups
  - Amazon Easy Ship (expandable)
    - Amazon Packing Plan
    - Easy Ship Report
  - Flipkart (expandable)
    - Flipkart Packing Plan
    - Report
  - Label Generator
  - Product Label Generator
  - Manual Plan
  - Packed Unit Stock

### 5.2 UI Components
- **Dashboard Header**: Connection status, product count
- **File Upload**: Multi-file PDF upload
- **Searchable Tables**: Interactive data tables
- **Status Badges**: Visual status indicators
- **Toast Notifications**: User feedback
- **Custom CSS**: Smooth animations and styling

### 5.3 Session State Management
- **SessionStateManager**: Centralized state management
- **Stored Data**:
  - Uploaded files
  - Processed data
  - Master DataFrame
  - Configuration values
  - Cached calculations

---

## 6. Configuration & Deployment

### 6.1 Entry Points
- **`streamlit_app.py`**: Main entry for Streamlit Cloud deployment
- **`app/main.py`**: Alternative entry point (sidebar disabled)

### 6.2 Environment Setup
- **Dependencies**: Listed in `requirements.txt`
- **Data Directory**: `data/` (auto-created if missing)
- **Fonts**: Custom Helvetica fonts in `fonts/` directory

### 6.3 Admin Features
- **Password**: `admin@2025#` (hardcoded in `sidebar.py`)
- **Admin Controls**: Currently disabled (`SHOW_ADMIN_CONTROLS = False`)
- **Features** (when enabled):
  - Master data upload
  - Barcode PDF upload
  - Google Sheets URL configuration

### 6.4 Default Data Initialization
- Creates placeholder files if missing
- Default barcode PDF
- Default meta file
- Ensures data directory exists

---

## 7. Error Handling & Validation

### 7.1 File Validation
- File type checking
- File size limits (50MB default)
- PDF structure validation

### 7.2 Data Validation
- Master data presence check
- ASIN matching validation
- Missing product detection
- FNSKU validation

### 7.3 Error Recovery
- Graceful fallbacks (Google Sheets → Local file)
- User-friendly error messages
- Detailed logging
- Try-catch blocks around critical operations

---

## 8. Performance Optimizations

### 8.1 Caching
- **Streamlit Cache**: `@st.cache_data(ttl=300)` for master data
- **Session State Cache**: Expensive calculations cached
- **5-minute TTL**: Balance between freshness and performance

### 8.2 PDF Processing
- Safe context managers for PDF handling
- Efficient text extraction
- Batch processing for multiple files

---

## 9. Dependencies Analysis

### 9.1 Core Dependencies
```
streamlit          # Web framework
pandas             # Data manipulation
openpyxl           # Excel file handling
requests           # HTTP requests (Google Sheets)
reportlab          # PDF generation
fpdf2              # PDF generation (alternative)
PyMuPDF            # PDF reading/manipulation
Pillow             # Image processing
python-barcode     # Barcode generation
qrcode             # QR code generation
pdf2image          # PDF to image conversion
fonttools          # Font handling
numpy              # Numerical operations
python-dateutil    # Date handling
streamlit-tailwind # Optional UI styling
```

### 9.2 Version Considerations
- No version pinning in requirements.txt
- Potential compatibility issues with future updates
- Recommendation: Pin major versions

---

## 10. Security Considerations

### 10.1 Current Security Status
- **Admin Password**: Hardcoded (security risk)
- **Google Sheets**: Public CSV export (no authentication)
- **File Uploads**: Basic validation only
- **Session State**: Client-side storage

### 10.2 Recommendations
- Use environment variables for sensitive data
- Implement proper authentication
- Add file upload size limits
- Sanitize user inputs
- Add rate limiting for API calls

---

## 11. Code Quality & Maintainability

### 11.1 Strengths
- **Modular Structure**: Well-organized into tools, components, utils
- **Reusable Components**: UI components and utilities
- **Documentation**: Split logic documented
- **Error Handling**: Comprehensive try-catch blocks
- **Logging**: Proper logging throughout

### 11.2 Areas for Improvement
- **Code Duplication**: Some logic duplicated between Amazon/Flipkart tools
- **Hardcoded Values**: URLs, passwords, file paths
- **Type Hints**: Limited type annotations
- **Testing**: No visible test files
- **Documentation**: Some functions lack docstrings

---

## 12. Feature Gaps & Potential Enhancements

### 12.1 Missing Features
- User authentication system
- Data export history
- Audit logging
- Real-time notifications
- Mobile responsiveness optimization
- API endpoints for external integration

### 12.2 Potential Enhancements
- Database integration (replace Google Sheets)
- Automated label printing
- Inventory tracking dashboard
- Order history and analytics
- Multi-warehouse support
- Batch processing improvements
- Export to multiple formats (CSV, JSON)

---

## 13. Deployment Considerations

### 13.1 Streamlit Cloud Deployment
- Entry point: `streamlit_app.py`
- Requirements: `requirements.txt`
- Data persistence: Files stored in `data/` directory
- Google Sheets: Requires public access or API credentials

### 13.2 Local Deployment
- Run: `streamlit run streamlit_app.py`
- Port: Default 8501
- Data directory: Must be writable

---

## 14. Testing Strategy (Recommended)

### 14.1 Unit Tests Needed
- Data loading functions
- PDF processing functions
- Split logic algorithm
- Label generation functions

### 14.2 Integration Tests Needed
- End-to-end packing plan generation
- Google Sheets integration
- File upload and processing
- Error handling scenarios

---

## 15. Conclusion

The **Mithila Tools Dashboard** is a comprehensive warehouse management solution with:
- ✅ Well-structured codebase
- ✅ Multiple integrated tools
- ✅ Google Sheets integration
- ✅ PDF processing capabilities
- ✅ Label generation features
- ⚠️ Security improvements needed
- ⚠️ Testing infrastructure missing
- ⚠️ Some code duplication

**Overall Assessment**: Production-ready with recommended security and testing enhancements.

---

## 16. Quick Reference

### Key Files
- **Entry Point**: `streamlit_app.py`
- **Main Logic**: `app/tools/` directory
- **Data Loading**: `app/data_loader.py`
- **UI Components**: `app/utils/ui_components.py`
- **Configuration**: `app/sidebar.py`

### Key Functions
- `load_master_data()`: Load master product data
- `packing_plan_tool()`: Amazon packing plan generator
- `flipkart_packing_plan_tool()`: Flipkart packing plan generator
- `label_generator_tool()`: Label generation
- `expandToPhysical()`: Split logic implementation (documented in SPLIT_LOGIC_DOCUMENTATION.md)

### Key Data Files
- Master data: Google Sheets or `data/temp_master.xlsx`
- Barcode PDF: `data/master_fnsku.pdf`
- Configuration: `data/master_sheet_url.txt`

