#!/usr/bin/env python3
"""
Default data generator for Mithila Tools
Creates default files when they're missing in deployment
"""

import os
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import logging

logger = logging.getLogger(__name__)

def create_default_barcode_pdf(file_path):
    """Create a default placeholder barcode PDF"""
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # Create a simple PDF with placeholder text
        c = canvas.Canvas(file_path, pagesize=letter)
        width, height = letter
        
        # Add placeholder content
        c.setFont("Helvetica", 12)
        c.drawString(100, height - 100, "MITHILA TOOLS - DEFAULT BARCODE PDF")
        c.drawString(100, height - 130, "Upload your actual master_fnsku.pdf via the sidebar")
        c.drawString(100, height - 160, "to enable barcode label generation.")
        
        # Add a simple rectangle as placeholder
        c.rect(100, height - 250, 200, 50)
        c.drawString(120, height - 225, "PLACEHOLDER BARCODE")
        
        c.save()
        logger.info(f"Created default barcode PDF: {file_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to create default barcode PDF: {e}")
        return False

def create_default_meta_file(file_path):
    """Create a default meta file"""
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w') as f:
            f.write("default_data|2025-01-01T00:00:00")
        logger.info(f"Created default meta file: {file_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to create default meta file: {e}")
        return False

def ensure_data_files():
    """Ensure all required data files exist"""
    from app.sidebar import BARCODE_PDF_PATH, META_FILE, DATA_DIR
    
    # Ensure data directory exists
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
    except:
        pass
    
    # Create default files if they don't exist
    if not os.path.exists(BARCODE_PDF_PATH):
        create_default_barcode_pdf(BARCODE_PDF_PATH)
    
    if not os.path.exists(META_FILE):
        create_default_meta_file(META_FILE)
