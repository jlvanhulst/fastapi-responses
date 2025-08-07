"""
PDF generation utilities for converting markdown responses to PDF with embedded files.
"""
import tempfile
import os
import re
import logging
from typing import List, Dict, Any, Optional
import markdown
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER
from reportlab.lib import colors
from openai import AsyncOpenAI
from html.parser import HTMLParser

logger = logging.getLogger(__name__)


class MarkdownHTMLParser(HTMLParser):
    """Custom HTML parser to convert HTML to ReportLab-friendly format."""

    def __init__(self):
        super().__init__()
        self.elements = []
        self.current_text = ""
        self.in_table = False
        self.table_data = []
        self.current_row = []
        self.in_row = False
        self.in_cell = False
        self.cell_text = ""
        self.formatting_stack = []
        self.heading_level = None

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)

        if tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            self.flush_text()
            self.heading_level = int(tag[1])
        elif tag == 'p':
            self.flush_text()
        elif tag == 'br':
            self.current_text += "<br/>"
        elif tag == 'strong' or tag == 'b':
            self.formatting_stack.append('b')
        elif tag == 'em' or tag == 'i':
            self.formatting_stack.append('i')
        elif tag == 'img':
            # Handle image references - look for file placeholders
            src = attrs_dict.get('src', '')
            alt = attrs_dict.get('alt', '')
            if 'attachment:' in src or '/chat/files/' in src:
                # This will be handled by file embedding logic
                self.current_text += f"[IMAGE: {alt}]"
            # Skip other images
        elif tag == 'table':
            self.flush_text()
            self.in_table = True
            self.table_data = []
        elif tag == 'tr':
            if self.in_table:
                self.in_row = True
                self.current_row = []
        elif tag in ['td', 'th']:
            if self.in_row:
                self.in_cell = True
                self.cell_text = ""
        elif tag == 'hr':
            self.flush_text()
            self.elements.append(('hr', None))

    def handle_endtag(self, tag):
        if tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            if self.heading_level:
                self.elements.append(('heading', {'level': self.heading_level, 'text': self.current_text.strip()}))
                self.current_text = ""
                self.heading_level = None
        elif tag == 'p':
            self.flush_text()
        elif tag == 'strong' or tag == 'b':
            if 'b' in self.formatting_stack:
                self.formatting_stack.remove('b')
        elif tag == 'em' or tag == 'i':
            if 'i' in self.formatting_stack:
                self.formatting_stack.remove('i')
        elif tag == 'table':
            if self.in_table:
                self.elements.append(('table', self.table_data))
                self.in_table = False
                self.table_data = []
        elif tag == 'tr':
            if self.in_row:
                self.table_data.append(self.current_row)
                self.current_row = []
                self.in_row = False
        elif tag in ['td', 'th']:
            if self.in_cell:
                self.current_row.append(self.cell_text.strip())
                self.cell_text = ""
                self.in_cell = False

    def handle_data(self, data):
        if self.in_cell:
            self.cell_text += data
        else:
            # Only add non-whitespace text or preserve single spaces
            if data.strip() or (data == ' ' and self.current_text and not self.current_text.endswith(' ')):
                formatted_text = data
                if 'b' in self.formatting_stack:
                    formatted_text = f"<b>{formatted_text}</b>"
                if 'i' in self.formatting_stack:
                    formatted_text = f"<i>{formatted_text}</i>"
                self.current_text += formatted_text

    def flush_text(self):
        if self.current_text.strip():
            self.elements.append(('text', self.current_text.strip()))
            self.current_text = ""

    def get_elements(self):
        self.flush_text()
        return self.elements


class PDFGenerator:
    """Handles conversion of markdown text with embedded files to PDF."""

    def __init__(self):
        self.styles = getSampleStyleSheet()
        self.setup_custom_styles()

    def setup_custom_styles(self):
        """Setup custom paragraph styles for better PDF formatting."""
        # Custom title style
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=20,
            spaceAfter=30,
            alignment=TA_CENTER
        ))

        # Custom heading styles
        self.styles.add(ParagraphStyle(
            name='CustomHeading2',
            parent=self.styles['Heading2'],
            fontSize=16,
            spaceBefore=20,
            spaceAfter=12
        ))

        self.styles.add(ParagraphStyle(
            name='CustomHeading3',
            parent=self.styles['Heading3'],
            fontSize=14,
            spaceBefore=16,
            spaceAfter=10
        ))

    async def download_openai_file(self, container_id: str, file_id: str) -> Optional[bytes]:
        """Download a file from OpenAI API and return its content as bytes."""
        try:
            client = AsyncOpenAI()
            response_content = await client.containers.files.content.retrieve(
                file_id=file_id,
                container_id=container_id,
            )
            return response_content.read()
        except Exception as e:
            logger.error(f"Error downloading file {container_id}/{file_id}: {e}")
            return None

    def clean_html_for_paragraph(self, html_text: str) -> str:
        """Clean HTML text to make it safe for ReportLab Paragraph."""
        if not html_text:
            return ""

        # Remove problematic image tags completely
        html_text = re.sub(r'<img[^>]*>', '[IMAGE]', html_text)

        # Remove table-related tags and replace with simple text
        html_text = re.sub(r'<table[^>]*>', '', html_text)
        html_text = re.sub(r'</table>', '', html_text)
        html_text = re.sub(r'<thead[^>]*>', '', html_text)
        html_text = re.sub(r'</thead>', '', html_text)
        html_text = re.sub(r'<tbody[^>]*>', '', html_text)
        html_text = re.sub(r'</tbody>', '', html_text)
        html_text = re.sub(r'<tr[^>]*>', '', html_text)
        html_text = re.sub(r'</tr>', '<br/>', html_text)
        html_text = re.sub(r'<th[^>]*>', '', html_text)
        html_text = re.sub(r'</th>', ' | ', html_text)
        html_text = re.sub(r'<td[^>]*>', '', html_text)
        html_text = re.sub(r'</td>', ' | ', html_text)

        # Remove horizontal rules and replace with simple dashes (avoid Unicode)
        html_text = re.sub(r'<hr[^>]*>', '------------------------', html_text)

        # Clean up basic formatting - keep only ReportLab-safe tags
        html_text = re.sub(r'<strong[^>]*>', '<b>', html_text)
        html_text = re.sub(r'</strong>', '</b>', html_text)
        html_text = re.sub(r'<em[^>]*>', '<i>', html_text)
        html_text = re.sub(r'</em>', '</i>', html_text)

        # Remove paragraph tags but keep content
        html_text = re.sub(r'<p[^>]*>', '', html_text)
        html_text = re.sub(r'</p>', '<br/>', html_text)

        # Remove any remaining attributes from supported tags
        html_text = re.sub(r'<([bi])[^>]*>', r'<\1>', html_text)

        # Fix unclosed tags by ensuring proper tag balance
        html_text = self.balance_html_tags(html_text)

        # Replace Unicode characters that might cause issues
        html_text = html_text.replace('\u2500', '-')  # Box drawing characters
        html_text = html_text.replace('\u2501', '-')
        html_text = html_text.replace('\u2502', '|')
        html_text = html_text.replace('\u2503', '|')

        # Clean up multiple line breaks
        html_text = re.sub(r'(<br/>)+', '<br/>', html_text)
        html_text = re.sub(r'^<br/>', '', html_text)
        html_text = re.sub(r'<br/>$', '', html_text)

        return html_text.strip()

    def balance_html_tags(self, html_text: str) -> str:
        """Ensure HTML tags are properly balanced for ReportLab."""
        # Track open tags
        open_tags = []

        # Find all tags
        tag_pattern = r'<(/?)([bi])([^>]*)>'

        def replace_tag(match):
            is_closing = bool(match.group(1))
            tag_name = match.group(2)

            if is_closing:
                # Closing tag
                if tag_name in open_tags:
                    open_tags.remove(tag_name)
                    return f'</{tag_name}>'
                else:
                    # Orphaned closing tag, remove it
                    return ''
            else:
                # Opening tag
                open_tags.append(tag_name)
                return f'<{tag_name}>'

        # Replace tags
        result = re.sub(tag_pattern, replace_tag, html_text)

        # Close any remaining open tags
        for tag in reversed(open_tags):
            result += f'</{tag}>'

        return result

    def parse_markdown_with_files(self, markdown_text: str, output_files: List[Dict] = None) -> tuple[List, List[Dict]]:
        """
        Parse markdown content and identify file references for embedding.
        Returns (parsed_elements, file_references).
        """
        file_references = []
        elements = []

        # Convert markdown to HTML first
        html_content = markdown.markdown(markdown_text, extensions=['tables', 'fenced_code'])
        logger.info(f"Original HTML content (first 1000 chars): {html_content[:1000]}")

        # Find ANY image references in HTML
        # Pattern: <img ... src="anything" ... />
        img_pattern = r'<img[^>]*src=["\']([^"\']+)["\'][^>]*>'

        def replace_image(match):
            # Extract the full src value
            src_value = match.group(1)  # e.g., "sandbox:/mnt/data/acme_corp_2024_revenue.png"

            # Extract just the filename from any path
            filename = os.path.basename(src_value)  # e.g., "acme_corp_2024_revenue.png"

            logger.info("=== FILE MATCHING ===")
            logger.info(f"Found image src: '{src_value}'")
            logger.info(f"Extracted filename: '{filename}'")

            # Find EXACT match in output_files
            matching_file = None
            if output_files:
                for i, output_file in enumerate(output_files):
                    file_name = output_file.get('filename', '')
                    logger.info(f"  Comparing: '{filename}' == '{file_name}'")

                    # SIMPLE EXACT MATCH
                    if file_name == filename:
                        logger.info("✓ EXACT MATCH FOUND!")
                        matching_file = output_file
                        break

            if matching_file:
                # Extract alt text from the original img tag if available
                alt_match = re.search(r'alt=["\']([^"\']*)["\']', match.group(0))
                alt_text = alt_match.group(1) if alt_match else filename

                file_references.append({
                    'type': 'image',
                    'file_info': matching_file,
                    'alt_text': alt_text,
                    'placeholder_id': f'FILE_PLACEHOLDER_{len(file_references)}'
                })
                logger.info(f"✓ Added file to references: {filename}")
                return f'[[IMAGE: {alt_text}]]'
            else:
                logger.warning(f"✗ No match found for: {filename}")
                logger.warning(f"  Available files: {[f.get('filename', '') for f in output_files]}")
                return match.group(0)  # Keep original if no match

        # Replace image references with simple pattern
        html_content = re.sub(img_pattern, replace_image, html_content)

        logger.info(f"HTML after replacing attachments (first 500 chars): {html_content[:500]}")

        # Simple approach: Split by major HTML elements and process each part
        # Split by tables first (they need special handling)
        table_parts = re.split(r'(<table.*?</table>)', html_content, flags=re.DOTALL)

        for part in table_parts:
            if part.strip():
                if part.startswith('<table'):
                    # This is a table - extract table data
                    table_data = self.extract_table_data(part)
                    if table_data:
                        elements.append(('table', table_data))
                else:
                    # Process non-table content by splitting on paragraphs and headings
                    text_elements = self.process_text_content(part)
                    elements.extend(text_elements)

        logger.info(f"Final elements: {len(elements)} - {[e[0] for e in elements[:5]]}")
        return elements, file_references

    def extract_table_data(self, table_html: str) -> List[List[str]]:
        """Extract table data from HTML table."""
        rows = []
        # Extract all table rows
        row_pattern = r'<tr[^>]*>(.*?)</tr>'
        row_matches = re.findall(row_pattern, table_html, re.DOTALL)

        for row_html in row_matches:
            cells = []
            # Extract all cells (th or td)
            cell_pattern = r'<t[hd][^>]*>(.*?)</t[hd]>'
            cell_matches = re.findall(cell_pattern, row_html, re.DOTALL)

            for cell_html in cell_matches:
                # Clean cell content
                cell_text = re.sub(r'<[^>]+>', '', cell_html).strip()
                cells.append(cell_text)

            if cells:
                rows.append(cells)

        return rows

    def process_text_content(self, html_content: str) -> List:
        """Process text content and return list of elements."""
        elements = []

        # Split by headings first
        heading_pattern = r'(<h[1-6][^>]*>.*?</h[1-6]>)'
        parts = re.split(heading_pattern, html_content, flags=re.DOTALL)

        for part in parts:
            if not part.strip():
                continue

            if re.match(r'<h([1-6])', part):
                # This is a heading
                level = int(re.search(r'<h([1-6])', part).group(1))
                text = re.sub(r'<h[1-6][^>]*>(.*?)</h[1-6]>', r'\1', part, flags=re.DOTALL)
                text = re.sub(r'<[^>]+>', '', text).strip()  # Clean any remaining tags
                if text:
                    elements.append(('heading', {'level': level, 'text': text}))
            else:
                # Regular content - clean and add as text
                clean_text = self.clean_html_for_paragraph(part)
                if clean_text.strip():
                    elements.append(('text', clean_text))

        return elements

    def elements_to_pdf_content(self, elements: List, file_references: List[Dict]) -> List:
        """Convert parsed elements to ReportLab content."""
        content = []

        for element_type, element_data in elements:
            if element_type == 'heading':
                level = element_data['level']
                text = element_data['text']

                if level == 1:
                    style = self.styles['CustomTitle']
                elif level == 2:
                    style = self.styles['CustomHeading2']
                elif level == 3:
                    style = self.styles['CustomHeading3']
                else:
                    style = self.styles['Heading4']

                content.append(Paragraph(text, style))
                content.append(Spacer(1, 12))

            elif element_type == 'text':
                # Handle file placeholders in text
                text = element_data

                # Check for file placeholders
                placeholder_pattern = r'\[\[IMAGE: ([^\]]+)\]\]'
                parts = re.split(placeholder_pattern, text)

                # Only process if we found placeholders
                if re.search(placeholder_pattern, text):
                    for i, part in enumerate(parts):
                        if i % 2 == 0:  # Regular text
                            if part.strip():
                                clean_part = self.clean_html_for_paragraph(part)
                                if clean_part.strip():
                                    content.append(Paragraph(clean_part, self.styles['Normal']))
                        else:  # Image placeholder
                            alt_text = part
                            # Find matching file reference
                            matching_ref = next((f for f in file_references if f['alt_text'] == alt_text), None)
                            if matching_ref and 'temp_path' in matching_ref:
                                content.append(self.create_image_element(matching_ref))
                            else:
                                content.append(Paragraph(f"[IMAGE: {alt_text}]", self.styles['Normal']))
                else:
                    # No placeholders found, process as regular text
                    clean_text = self.clean_html_for_paragraph(text)
                    if clean_text.strip():
                        content.append(Paragraph(clean_text, self.styles['Normal']))

                content.append(Spacer(1, 6))

            elif element_type == 'table':
                table_data = element_data
                if table_data:
                    content.append(self.create_table_element(table_data))
                    content.append(Spacer(1, 12))

            elif element_type == 'hr':
                content.append(Spacer(1, 12))
                content.append(Paragraph('_' * 50, self.styles['Normal']))
                content.append(Spacer(1, 12))

        return content

    def create_table_element(self, table_data: List[List[str]]) -> Table:
        """Create a ReportLab Table element from table data."""
        if not table_data:
            return None

        # Clean up table data
        clean_data = []
        for row in table_data:
            clean_row = []
            for cell in row:
                # Remove formatting and clean text
                clean_cell = re.sub(r'<[^>]+>', '', str(cell)).strip()
                clean_row.append(clean_cell)
            clean_data.append(clean_row)

        table = Table(clean_data)

        # Style the table
        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ])
        table.setStyle(style)

        return table

    def create_image_element(self, file_ref: Dict) -> Any:
        """Create a ReportLab Image element from a file reference."""
        try:
            img = Image(file_ref['temp_path'])

            # Scale image to fit page width (with margins)
            max_width = letter[0] - 2 * inch  # Page width minus margins
            max_height = letter[1] - 3 * inch  # Leave space for text

            # Get original dimensions
            img_width, img_height = img.imageWidth, img.imageHeight

            # Calculate scale factor
            width_scale = max_width / img_width
            height_scale = max_height / img_height
            scale = min(width_scale, height_scale, 1.0)  # Don't scale up

            img.drawWidth = img_width * scale
            img.drawHeight = img_height * scale

            return img
        except Exception as e:
            logger.error(f"Error creating image element: {e}")
            # Return a placeholder paragraph if image fails
            return Paragraph(f"[Image: {file_ref.get('alt_text', 'Chart/Graph')}]", self.styles['Normal'])

    async def generate_pdf(self, markdown_content: str, output_files: List[Dict] = None, title: str = "Report") -> bytes:
        """
        Generate PDF from markdown content and associated files.

        Args:
            markdown_content: The markdown text to convert
            output_files: List of file objects with container_id, file_id, etc.
            title: Title for the PDF document

        Returns:
            PDF content as bytes
        """
        try:
            # Log the input for debugging
            logger.info("=== PDF Generation Debug ===")
            logger.info(f"Markdown content (first 500 chars): {markdown_content[:500]}")
            logger.info(f"Number of output files: {len(output_files) if output_files else 0}")
            if output_files:
                for i, f in enumerate(output_files):
                    logger.info(f"Output file {i}: {f}")

            # Parse markdown content and identify file references
            elements, file_references = self.parse_markdown_with_files(markdown_content, output_files)

            # Download and prepare files
            await self.prepare_files(file_references)

            # Create PDF buffer
            buffer = BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=letter, title=title)

            # Build PDF content
            story = []

            # Add parsed content directly (no automatic title/header)
            pdf_content = self.elements_to_pdf_content(elements, file_references)
            story.extend(pdf_content)

            # Build PDF
            doc.build(story)

            # Clean up temporary files
            self.cleanup_temp_files(file_references)

            return buffer.getvalue()

        except Exception as e:
            logger.error(f"Error generating PDF: {e}")
            # Clean up any temporary files that might have been created
            if 'file_references' in locals():
                self.cleanup_temp_files(file_references)
            raise

    async def prepare_files(self, file_references: List[Dict]):
        """Download files and prepare them for embedding in PDF."""
        for file_ref in file_references:
            if 'file_info' in file_ref:
                file_info = file_ref['file_info']
                
                # Check if this is an embedded image with base64 data
                if file_info.get('type') == 'embedded_image' and file_info.get('base64_data'):
                    # Create temp file from base64 data
                    import base64
                    image_bytes = base64.b64decode(file_info['base64_data'])
                    
                    # Determine file extension
                    image_format = file_info.get('format', 'png')
                    suffix = f'.{image_format}'
                    
                    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                        temp_file.write(image_bytes)
                        file_ref['temp_path'] = temp_file.name
                        logger.info(f"Created temp file from base64 data: {temp_file.name}")
                else:
                    # Download file content from OpenAI
                    file_content = await self.download_openai_file(
                        file_info['container_id'],
                        file_info['file_id']
                    )

                    if file_content:
                        # Save to temporary file
                        suffix = '.png'  # Default to PNG for images
                        if file_info.get('filename'):
                            _, ext = os.path.splitext(file_info['filename'])
                            if ext:
                                suffix = ext

                        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                            temp_file.write(file_content)
                            file_ref['temp_path'] = temp_file.name

    def cleanup_temp_files(self, file_references: List[Dict]):
        """Clean up temporary files created during PDF generation."""
        for file_ref in file_references:
            if 'temp_path' in file_ref:
                try:
                    os.unlink(file_ref['temp_path'])
                except Exception as e:
                    logger.warning(f"Could not delete temp file {file_ref['temp_path']}: {e}")
