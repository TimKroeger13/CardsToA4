#!/usr/bin/env python3
"""
Card Printer PDF Generator
Creates a PDF with images arranged in a 3x3 grid per page
Each image is 6.3cm wide x 9cm high
Now supports batch file format with \newpage markers

Modified version with:
- 3mm safety margins between cards
- Black background
- White cutting lines on odd pages only
"""

import os
import sys
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import HexColor
from PIL import Image
import argparse
import io
from tqdm import tqdm

class CardPrinter:
    def __init__(self, output_filename="cards_output.pdf", optimize=True):
        """Initialize the card printer with output filename"""
        self.output_filename = output_filename
        self.optimize = optimize
        self.page_width, self.page_height = A4
        
        # Image dimensions in cm
        self.img_width = 6.3 * cm
        self.img_height = 9 * cm
        
        # Safety margin between cards (3mm = 0.3cm)
        self.margin = 0.3 * cm
        
        # Calculate positions for 3x3 grid with 3mm spacing
        # A4 width = 21cm, A4 height = 29.7cm
        # Total width needed: 3 cards * 6.3cm + 2 gaps * 0.3cm = 18.9cm + 0.6cm = 19.5cm
        # Total height needed: 3 cards * 9cm + 2 gaps * 0.3cm = 27cm + 0.6cm = 27.6cm
        # Left margin: (21 - 19.5) / 2 = 0.75cm
        # Top margin: (29.7 - 27.6) / 2 = 1.05cm
        
        left_margin = 0.75 * cm
        top_margin = 1.05 * cm
        
        # Position coordinates for 9 cards (3x3 grid) with 3mm spacing
        self.positions = [
            # Row 1 (top)
            (left_margin, self.page_height - top_margin - self.img_height),   # Top-left
            (left_margin + self.img_width + self.margin, self.page_height - top_margin - self.img_height),   # Top-middle
            (left_margin + 2 * (self.img_width + self.margin), self.page_height - top_margin - self.img_height),  # Top-right
            # Row 2 (middle)
            (left_margin, self.page_height - top_margin - 2 * self.img_height - self.margin),  # Middle-left
            (left_margin + self.img_width + self.margin, self.page_height - top_margin - 2 * self.img_height - self.margin),  # Middle-middle
            (left_margin + 2 * (self.img_width + self.margin), self.page_height - top_margin - 2 * self.img_height - self.margin), # Middle-right
            # Row 3 (bottom)
            (left_margin, self.page_height - top_margin - 3 * self.img_height - 2 * self.margin),  # Bottom-left
            (left_margin + self.img_width + self.margin, self.page_height - top_margin - 3 * self.img_height - 2 * self.margin),  # Bottom-middle
            (left_margin + 2 * (self.img_width + self.margin), self.page_height - top_margin - 3 * self.img_height - 2 * self.margin), # Bottom-right
        ]
        
        # Cutting line positions are the same as card positions
        # They will be drawn as rectangles overlaid on the cards to show exact cut lines
        self.cutting_positions = self.positions
        
        self.c = None
        self.current_page_images = []
        self.image_cache = {}
        self.page_count = 0
        
    def optimize_image(self, image_path):
        """Prepare image for PDF - convert format if needed but keep quality"""
        if image_path in self.image_cache:
            return self.image_cache[image_path]
        
        try:
            img = Image.open(image_path)
            
            if img.mode in ('RGBA', 'LA'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])
                img = background
            elif img.mode == 'P':
                img = img.convert('RGB')
            
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=95, optimize=True)
            buffer.seek(0)
            
            img_reader = ImageReader(buffer)
            self.image_cache[image_path] = img_reader
            
            return img_reader
            
        except Exception as e:
            print(f"Error preparing image {image_path}: {e}")
            return None
        
    def start_pdf(self):
        """Initialize the PDF canvas"""
        self.c = canvas.Canvas(self.output_filename, pagesize=A4)
        self.c.setPageCompression(1)
        
    def draw_background(self):
        """Draw black background for the entire page"""
        self.c.setFillColorRGB(0, 0, 0)
        self.c.rect(0, 0, self.page_width, self.page_height, fill=1, stroke=0)
        
    def draw_cutting_lines(self):
        """Draw cutting lines in color #0C0C0C"""
        cutting_color = HexColor('#FFFFFF')
        self.c.setStrokeColor(cutting_color)
        self.c.setLineWidth(10)  # Thin line here
        
        # Draw rectangles at original positions (without margin offset)
        for x, y in self.cutting_positions:
            self.c.rect(x, y, self.img_width, self.img_height, fill=0, stroke=1)
    
    def add_image(self, image_path):
        """Add an image to the current page buffer"""
        if not os.path.exists(image_path):
            print(f"Warning: Image not found: {image_path}")
            return False
            
        self.current_page_images.append(image_path)
        
        if len(self.current_page_images) == 9:
            self._create_page()
            self.current_page_images = []
        
        return True
    
    def create_page_with_images(self, image_paths):
        """Create a complete page with exactly the provided images"""
        if not self.c:
            self.start_pdf()
        
        self.page_count += 1
        
        # Draw black background
        self.draw_background()
        
        # Draw cutting lines only on odd pages (front pages)
        if self.page_count % 2 == 1:
            self.draw_cutting_lines()
        
        # Draw images
        for i, img_path in enumerate(image_paths):
            if i < 9 and img_path and i < len(self.positions):
                x, y = self.positions[i]
                try:
                    if self.optimize:
                        img_reader = self.optimize_image(img_path)
                        if img_reader:
                            self.c.drawImage(img_reader, x, y, 
                                           width=self.img_width, 
                                           height=self.img_height,
                                           preserveAspectRatio=True)
                    else:
                        self.c.drawImage(img_path, x, y, 
                                       width=self.img_width, 
                                       height=self.img_height,
                                       preserveAspectRatio=True)
                except Exception as e:
                    print(f"Error adding image {img_path}: {e}")
        
        self.c.showPage()
        
    def _create_page(self):
        """Create a page with the current images"""
        if not self.c:
            self.start_pdf()
        
        self.page_count += 1
        
        # Draw black background
        self.draw_background()
        
        # Draw cutting lines only on odd pages (front pages)
        if self.page_count % 2 == 1:
            self.draw_cutting_lines()
            
        for i, img_path in enumerate(self.current_page_images):
            if i < len(self.positions):
                x, y = self.positions[i]
                try:
                    if self.optimize:
                        img_reader = self.optimize_image(img_path)
                        if img_reader:
                            self.c.drawImage(img_reader, x, y, 
                                           width=self.img_width, 
                                           height=self.img_height,
                                           preserveAspectRatio=True)
                    else:
                        self.c.drawImage(img_path, x, y, 
                                       width=self.img_width, 
                                       height=self.img_height,
                                       preserveAspectRatio=True)
                except Exception as e:
                    print(f"Error adding image {img_path}: {e}")
        
        self.c.showPage()
        
    def finalize(self):
        """Finalize the PDF, handling any remaining images"""
        if self.current_page_images:
            while len(self.current_page_images) < 9:
                self.current_page_images.append(None)
            
            if self.c:
                self.page_count += 1
                
                # Draw black background
                self.draw_background()
                
                # Draw cutting lines only on odd pages
                if self.page_count % 2 == 1:
                    self.draw_cutting_lines()
                
                for i, img_path in enumerate(self.current_page_images):
                    if img_path and i < len(self.positions):
                        x, y = self.positions[i]
                        try:
                            if self.optimize:
                                img_reader = self.optimize_image(img_path)
                                if img_reader:
                                    self.c.drawImage(img_reader, x, y,
                                                   width=self.img_width,
                                                   height=self.img_height,
                                                   preserveAspectRatio=True)
                            else:
                                self.c.drawImage(img_path, x, y,
                                               width=self.img_width,
                                               height=self.img_height,
                                               preserveAspectRatio=True)
                        except Exception as e:
                            print(f"Error adding image {img_path}: {e}")
                
                self.c.showPage()
        
        if self.c:
            self.c.save()
            print(f"\n✓ PDF created successfully: {self.output_filename}")
            print(f"✓ Total pages: {self.page_count}")
            print(f"✓ Cutting lines on odd pages: {(self.page_count + 1) // 2}")
            self.image_cache.clear()

def get_images_dict(folder_path):
    """Get all images in folder as a dictionary with name as key"""
    folder = Path(folder_path)
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif'}
    images = []
    for ext in image_extensions:
        images.extend(folder.glob(f'*{ext}'))
        images.extend(folder.glob(f'*{ext.upper()}'))
    
    images = sorted(set(images))
    
    images_dict = {}
    for img in images:
        name_without_ext = img.stem
        full_name = img.name
        images_dict[name_without_ext.lower()] = img
        images_dict[full_name.lower()] = img
    
    return images_dict, sorted(images)

def find_image_match(card_name, images_dict, images_list):
    """Find image match for a card name, returns (image_path, match_type) or (None, error_msg)"""
    card_lower = card_name.lower()
    
    # Try exact match first
    if card_lower in images_dict:
        return (images_dict[card_lower], 'exact')
    
    # Try prefix match
    matches = [img for img in images_list if img.name.lower().startswith(card_lower)]
    
    if len(matches) == 1:
        return (matches[0], 'prefix')
    elif len(matches) > 1:
        return (None, f"ambiguous: {[m.name for m in matches]}")
    else:
        return (None, "not_found")

def parse_batch_file(batch_file_path, images_dict, images_list):
    """
    Parse batch file and validate all card references.
    Returns (pages, errors) where pages is list of card lists, errors is list of issues
    """
    pages = []
    errors = []
    current_page_cards = []
    
    with open(batch_file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    page_section = 0  # Track which section we're in
    
    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        
        # Skip empty lines and comments
        if not line or line.startswith('#'):
            continue
        
        # Handle newpage marker
        if line == r'\newpage':
            if current_page_cards:
                # Check if page has exactly 9 cards
                if len(current_page_cards) != 9:
                    errors.append(f"Line {line_num}: Page #{len(pages)+1} has {len(current_page_cards)} cards (should be exactly 9)")
                
                pages.append(current_page_cards)
                current_page_cards = []
                page_section += 1
            continue
        
        # Parse card names (comma-separated)
        card_names = [name.strip() for name in line.split(',') if name.strip()]
        
        for card_name in card_names:
            img_path, match_info = find_image_match(card_name, images_dict, images_list)
            
            if img_path:
                current_page_cards.append((str(img_path), card_name, match_info))
            else:
                if match_info == "not_found":
                    errors.append(f"Line {line_num}: Card '{card_name}' not found")
                elif match_info.startswith("ambiguous"):
                    matches_list = match_info.split(": ")[1]
                    errors.append(f"Line {line_num}: Card '{card_name}' is ambiguous - matches: {matches_list}")
    
    # Handle last page if exists
    if current_page_cards:
        if len(current_page_cards) != 9:
            errors.append(f"End of file: Final page #{len(pages)+1} has {len(current_page_cards)} cards (should be exactly 9)")
        pages.append(current_page_cards)
    
    return pages, errors

def batch_mode_with_pages(folder_path, batch_file, optimize=True):
    """Process batch file with \newpage markers"""
    images_dict, images_list = get_images_dict(folder_path)
    
    if not images_list:
        print(f"Error: No images found in {folder_path}")
        return
    
    print(f"Found {len(images_list)} images in folder")
    print(f"Parsing batch file: {batch_file}\n")
    
    # Parse and validate
    pages, errors = parse_batch_file(batch_file, images_dict, images_list)
    
    # Report validation results
    print("="*70)
    print("VALIDATION RESULTS")
    print("="*70)
    
    if errors:
        print(f"\n❌ Found {len(errors)} error(s):\n")
        for error in errors:
            print(f"  • {error}")
        print("\n" + "="*70)
        
        proceed = input("\nErrors found. Continue anyway? (y/n): ").strip().lower()
        if proceed != 'y':
            print("Aborted.")
            return
        print()
    else:
        print(f"\n✓ All validations passed!")
        print(f"✓ Total pages: {len(pages)}")
        print(f"✓ Total cards: {sum(len(p) for p in pages)}")
        print("="*70 + "\n")
    
    # Show summary of matches
    total_exact = sum(1 for page in pages for _, _, match_type in page if match_type == 'exact')
    total_prefix = sum(1 for page in pages for _, _, match_type in page if match_type == 'prefix')
    
    if total_prefix > 0:
        print(f"Match summary: {total_exact} exact matches, {total_prefix} prefix matches\n")
    
    # Create PDF with progress bar
    printer = CardPrinter(optimize=optimize)
    printer.start_pdf()
    
    print("Creating PDF with 3mm safety margins and cutting lines on odd pages...")
    for page_num, page_cards in enumerate(tqdm(pages, desc="Processing pages", unit="page"), 1):
        image_paths = [img_path for img_path, _, _ in page_cards]
        printer.create_page_with_images(image_paths)
    
    printer.finalize()

def interactive_mode(folder_path, optimize=True):
    """Interactive mode for selecting images by name"""
    images_dict, images_list = get_images_dict(folder_path)
    
    if not images_list:
        print(f"No images found in {folder_path}")
        return
    
    print(f"\nFound {len(images_list)} images in {folder_path}:")
    for img in images_list:
        print(f"  - {img.name}")
    
    printer = CardPrinter(optimize=optimize)
    printer.start_pdf()
    
    page_num = 1
    print("\n" + "="*60)
    print("INSTRUCTIONS:")
    print("- Enter card names (with or without extension)")
    print("- Separate multiple cards with spaces or commas")
    print("- You can enter partial names (e.g., 'dragon' matches 'red_dragon.png')")
    print("- Type 'list' to see all available cards")
    print("- Type 'done' or press Enter to finish")
    print("="*60)
    
    while True:
        print(f"\n--- Page {page_num} ---")
        print("Enter card names for this page (1-9 cards):")
        
        selection = input("> ").strip()
        
        if selection.lower() == 'done' or not selection:
            break
        
        if selection.lower() == 'list':
            print("\nAvailable cards:")
            for img in images_list:
                print(f"  - {img.name}")
            continue
        
        card_names = [name.strip() for name in selection.replace(',', ' ').split()]
        
        found_images = []
        for card_name in card_names:
            img_path, match_info = find_image_match(card_name, images_dict, images_list)
            
            if img_path:
                found_images.append(img_path)
                if match_info == 'exact':
                    print(f"  ✓ Found: {img_path.name}")
                else:
                    print(f"  ✓ Found: {img_path.name} (prefix match)")
            else:
                if match_info == "not_found":
                    print(f"  ✗ Not found: '{card_name}'")
                elif match_info.startswith("ambiguous"):
                    matches = [img for img in images_list if img.name.lower().startswith(card_name.lower())]
                    print(f"  ✗ Multiple matches for '{card_name}':")
                    for i, match in enumerate(matches, 1):
                        print(f"    {i}. {match.name}")
                    choice = input(f"    Select (1-{len(matches)}) or skip (s): ").strip()
                    if choice.isdigit() and 1 <= int(choice) <= len(matches):
                        found_images.append(matches[int(choice) - 1])
                        print(f"  ✓ Added: {matches[int(choice) - 1].name}")
        
        if found_images:
            for img in found_images[:9]:
                printer.add_image(str(img))
            
            if len(found_images) < 9:
                cont = input(f"Added {len(found_images)} cards. Add more to this page? (y/n): ")
                if cont.lower() != 'y':
                    while len(printer.current_page_images) < 9:
                        printer.current_page_images.append(None)
                    printer._create_page()
                    printer.current_page_images = []
                    page_num += 1
            else:
                page_num += 1
    
    printer.finalize()

def batch_mode(folder_path, image_list_file=None, optimize=True):
    """Batch mode - process all images or from a list file"""
    folder = Path(folder_path)
    images_dict, images_list = get_images_dict(folder_path)
    
    printer = CardPrinter(optimize=optimize)
    printer.start_pdf()
    
    if image_list_file:
        print(f"Reading card names from: {image_list_file}")
        with open(image_list_file, 'r') as f:
            for line_num, line in enumerate(f, 1):
                card_name = line.strip()
                if not card_name or card_name.startswith('#'):
                    continue
                
                img_path, match_info = find_image_match(card_name, images_dict, images_list)
                
                if img_path:
                    printer.add_image(str(img_path))
                    if match_info == 'exact':
                        print(f"  ✓ Line {line_num}: {img_path.name}")
                    else:
                        print(f"  ✓ Line {line_num}: {img_path.name} (partial match)")
                else:
                    if match_info == "not_found":
                        print(f"  ✗ Line {line_num}: Not found '{card_name}'")
                    elif match_info.startswith("ambiguous"):
                        matches = [img for img in images_list if img.name.lower().startswith(card_name.lower())]
                        print(f"  ✗ Line {line_num}: Multiple matches for '{card_name}'")
                        for match in matches:
                            print(f"      - {match.name}")
    else:
        print("Processing all images in alphabetical order...")
        for img_path in images_list:
            printer.add_image(str(img_path))
            print(f"  Added: {img_path.name}")
    
    printer.finalize()

def main():
    parser = argparse.ArgumentParser(
        description='Create PDF with images in 3x3 grid for card printing',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Interactive mode:
    python card_printer.py /path/to/cards
  
  Batch mode with \\newpage format:
    python card_printer.py -p cards_layout.txt /path/to/cards
  
  Batch mode with simple card list:
    python card_printer.py -l cards_to_print.txt /path/to/cards

Features:
  - 3mm safety margins between cards
  - Black background for forgiving cuts
  - Cutting lines (#0C0C0C) on odd pages only
  
Batch file with \\newpage format:
    #1
    1_F,2_F,3_F,4_F,6_F,7_F,9_F,10_F,12_F
    \\newpage
    Rücken2000.png,Rücken2000.png,Rücken2000.png,Rücken2000.png,Rücken2000.png,Rücken2000.png,Rücken2000.png,Rücken2000.png,Rücken2000.png
    \\newpage
        """
    )
    parser.add_argument('folder', nargs='?', default='.', 
                       help='Folder containing images (default: current directory)')
    parser.add_argument('-o', '--output', default='cards_output.pdf',
                       help='Output PDF filename (default: cards_output.pdf)')
    parser.add_argument('-b', '--batch', action='store_true',
                       help='Batch mode - process all images in folder')
    parser.add_argument('-l', '--list', metavar='FILE',
                       help='Text file with list of card names to process')
    parser.add_argument('-p', '--pages', metavar='FILE',
                       help='Text file with card names and \\newpage markers')
    parser.add_argument('--no-optimize', action='store_true',
                       help='Disable image optimization (may be slower)')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.folder):
        print(f"Error: Folder '{args.folder}' does not exist")
        sys.exit(1)
    
    optimize = not args.no_optimize
    
    if optimize:
        print("Image optimization: ENABLED (quality 95%)")
    else:
        print("Image optimization: DISABLED\n")
    
    print("Features enabled:")
    print("  ✓ 3mm safety margins between cards")
    print("  ✓ Black background")
    print("  ✓ Cutting lines (#0C0C0C) on odd pages only\n")
    
    os.chdir(args.folder)
    
    if args.pages:
        batch_mode_with_pages('.', args.pages, optimize)
    elif args.batch or args.list:
        batch_mode('.', args.list, optimize)
    else:
        interactive_mode('.', optimize)

if __name__ == '__main__':
    main()