import fitz
import re
from collections import defaultdict

def clean_text(text):
    """Remove unicode characters that cause encoding issues"""
    return text.encode('ascii', 'ignore').decode('ascii')

def analyze_pdf_structure():
    pdf_path = 'ship.pdf'
    
    print("=== PDF STRUCTURE ANALYSIS ===")
    
    with fitz.open(pdf_path) as doc:
        for page_num, page in enumerate(doc):
            if page_num == 0:  # Skip first page
                continue
                
            print(f'\n--- PAGE {page_num + 1} ---')
            text_lines = page.get_text().split('\n')
            
            # Look for table structure and quantities
            in_items_section = False
            
            for i, line in enumerate(text_lines):
                clean_line = clean_text(line)
                
                # Detect start of items section
                if 'Description' in line and 'Qty' in line:
                    in_items_section = True
                    print(f'Line {i:2d}: [HEADER] {clean_line}')
                    continue
                
                if in_items_section and clean_line.strip():
                    print(f'Line {i:2d}: {clean_line}')
                    
                    # Look for ASIN lines
                    if 'B0' in line and len(re.findall(r'B[0-9A-Z]{9}', line)) > 0:
                        asin = re.findall(r'B[0-9A-Z]{9}', line)[0]
                        print(f'  *** ASIN FOUND: {asin} ***')
                        
                        # Analyze next few lines to understand structure
                        for j in range(i+1, min(i+5, len(text_lines))):
                            next_line = clean_text(text_lines[j]).strip()
                            if next_line:
                                print(f'  Next Line {j:2d}: {next_line}')
                                
                                # Extract all numbers from this line
                                numbers = re.findall(r'\d+(?:\.\d+)?', next_line)
                                if numbers:
                                    print(f'    Numbers found: {numbers}')
                                    
                                    # Check if this line has the pattern: price qty price tax total
                                    if len(numbers) >= 5 and 'IGST' in next_line:
                                        print(f'    INVOICE LINE: price={numbers[0]}, qty={numbers[1]}, price={numbers[2]}, tax={numbers[3]}, total={numbers[4]}')
                                        potential_qty = int(float(numbers[1]))
                                        print(f'    EXTRACTED QTY: {potential_qty}')
                                        break
                
                # Stop when we hit totals
                if 'TOTAL' in line.upper():
                    print(f'Line {i:2d}: [END] {clean_line}')
                    break
            
            if page_num >= 5:  # Check first few pages only
                break

if __name__ == "__main__":
    analyze_pdf_structure()
