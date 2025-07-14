import fitz
import re
from collections import defaultdict

def analyze_ship_pdf():
    # Read the ship.pdf file
    pdf_path = 'ship.pdf'
    asin_qty_data = defaultdict(int)

    # Pattern matching (same as in your code)
    asin_pattern = re.compile(r'\b(B[0-9A-Z]{9})\b')
    qty_pattern = re.compile(r'\bQty\b.*?(\d+)')
    price_qty_pattern = re.compile(r'₹[\d,.]+\s+(\d+)\s+₹[\d,.]+')

    print('Starting PDF text extraction...')

    # Test highlighting first
    print('\n=== TESTING HIGHLIGHT FUNCTION ===')
    
    try:
        with open(pdf_path, 'rb') as f:
            pdf_bytes = f.read()
        
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            in_table = False
            highlights_found = []
            
            for page_num, page in enumerate(doc):
                print(f'\nPage {page_num + 1}:')
                text_blocks = page.get_text("blocks")
                print(f'  Total blocks: {len(text_blocks)}')
                
                for block_idx, block in enumerate(text_blocks):
                    if len(block) < 5:
                        continue
                    x0, y0, x1, y1, text = block[:5]
                    
                    # Check for table headers
                    if "Description" in text and "Qty" in text:
                        in_table = True
                        print(f'  Block {block_idx}: TABLE HEADER FOUND - {text.strip()}')
                        continue

                    if in_table:
                        # Skip blocks that don't contain digits
                        if not any(char.isdigit() for char in text):
                            continue
                        # Skip header rows
                        if "Qty" in text or "Unit Price" in text or "Total" in text:
                            continue

                        # Look for quantities greater than 1
                        values = text.split()
                        for val in values:
                            if val.isdigit() and int(val) > 1:
                                highlights_found.append({
                                    'page': page_num + 1,
                                    'block': block_idx,
                                    'text': text.strip(),
                                    'value': int(val),
                                    'coords': (x0, y0, x1, y1)
                                })
                                print(f'  Block {block_idx}: HIGHLIGHT CANDIDATE (qty>{val}) - {text.strip()}')
                                break

                    # Exit table when we see TOTAL
                    if "TOTAL" in text:
                        in_table = False
                        print(f'  Block {block_idx}: TABLE END - {text.strip()}')
            
            print(f'\nHighlight candidates found: {len(highlights_found)}')
            for h in highlights_found:
                print(f"  Page {h['page']}: qty={h['value']} in '{h['text']}'")
                
    except Exception as e:
        print(f'Highlight test failed: {e}')

    print('\n=== TESTING ASIN EXTRACTION ===')
    
    with fitz.open(pdf_path) as doc:
        # Extract text from all pages and show page structure
        for page_num, page in enumerate(doc):
            print(f'\n=== PAGE {page_num + 1} ===')
            
            # Get text as lines
            text_lines = page.get_text().split('\n')
            print(f'Total lines: {len(text_lines)}')
            
            # Look for table structure
            table_started = False
            for i, line in enumerate(text_lines):
                if "Description" in line and "Qty" in line:
                    table_started = True
                    print(f'Line {i:2d} [TABLE START]: {line}')
                elif table_started and line.strip():
                    print(f'Line {i:2d}: {line}')
            
            # Look for ASIN patterns
            found_asins = []
            for i, line in enumerate(text_lines):
                asin_match = asin_pattern.search(line)
                if asin_match:
                    asin = asin_match.group(1)
                    found_asins.append((i, asin, line))
                    print(f'FOUND ASIN at line {i}: {asin} in: {line}')
                    
                    # Look for quantity in next few lines
                    qty = 1
                    for j in range(i, min(i + 4, len(text_lines))):
                        # Check qty pattern
                        match = qty_pattern.search(text_lines[j])
                        if match:
                            qty = int(match.group(1))
                            print(f'  Found qty {qty} at line {j}: {text_lines[j]}')
                            break
                        # Try price-qty pattern
                        match = price_qty_pattern.search(text_lines[j])
                        if match:
                            qty = int(match.group(1))
                            print(f'  Found qty {qty} (price pattern) at line {j}: {text_lines[j].encode("ascii", "ignore").decode("ascii")}')
                            break
                        # Try simple digit patterns
                        digits = re.findall(r'\b(\d+)\b', text_lines[j])
                        if digits:
                            print(f'  Line {j} contains digits: {digits} - {text_lines[j].encode("ascii", "ignore").decode("ascii")}')
                    
                    asin_qty_data[asin] += qty
            
            if not found_asins:
                print('No ASINs found on this page')
            
            if page_num >= 3:  # Only check first few pages
                break

    print(f'\n=== FINAL RESULTS ===')
    print(f'Total ASINs found: {len(asin_qty_data)}')
    for asin, qty in asin_qty_data.items():
        print(f'{asin}: {qty}')
    
    return asin_qty_data

if __name__ == "__main__":
    analyze_ship_pdf()
