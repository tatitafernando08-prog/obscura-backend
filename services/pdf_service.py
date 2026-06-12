import fitz          # PyMuPDF — reads PDFs
import re

def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """
    Extract all text from a PDF given its raw bytes.
    Works with both text-based and some scanned PDFs.
    """
    try:
        # Open PDF from bytes (not a file path)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        full_text = ""

        for page_number in range(len(doc)):
            page = doc[page_number]
            page_text = page.get_text()

            # Add page marker so we know where each page starts
            full_text += f"\n[PAGE {page_number + 1}]\n"
            full_text += page_text

        doc.close()
        return full_text.strip()

    except Exception as e:
        raise ValueError(f"Failed to read PDF: {str(e)}")


def clean_text(text: str) -> str:
    """
    Clean extracted text — remove extra spaces, fix common PDF artifacts.
    """
    # Replace multiple spaces/newlines with single space
    text = re.sub(r'\s+', ' ', text)

    # Remove weird characters that come from PDF encoding
    text = re.sub(r'[^\x00-\x7F\u0080-\uFFFF]', '', text)

    # Remove very short lines (usually headers/footers/page numbers)
    lines = text.split('.')
    lines = [l.strip() for l in lines if len(l.strip()) > 20]
    text = '. '.join(lines)

    return text.strip()


def chunk_text(
    text: str,
    chunk_size: int = 400,
    overlap:    int = 80
) -> list[str]:
    """
    Split text into overlapping chunks.

    Why overlap? So that if an answer spans the boundary
    between two chunks, it's still captured in at least one.

    chunk_size: number of words per chunk
    overlap:    how many words to repeat between chunks
    """
    # Clean first
    text = clean_text(text)

    words = text.split(' ')
    chunks = []
    start = 0

    while start < len(words):
        end = start + chunk_size
        chunk_words = words[start:end]
        chunk = ' '.join(chunk_words).strip()

        # Only keep chunks with enough content
        if len(chunk) > 50:
            chunks.append(chunk)

        # Move forward by (chunk_size - overlap) so chunks overlap
        start += (chunk_size - overlap)

    return chunks


def get_pdf_page_count(pdf_bytes: bytes) -> int:
    """Returns number of pages in a PDF"""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    count = len(doc)
    doc.close()
    return count

import pytesseract
from PIL import Image
import fitz
import io
import os
from dotenv import load_dotenv

load_dotenv()

# Set Tesseract path
tesseract_path = os.getenv("TESSERACT_PATH")
if tesseract_path:
    pytesseract.pytesseract.tesseract_cmd = tesseract_path


def extract_text_with_ocr(pdf_bytes: bytes) -> str:
    """
    Extract text from scanned PDFs using OCR.
    Falls back to this when normal text extraction returns nothing.
    """
    doc  = fitz.open(stream=pdf_bytes, filetype="pdf")
    text = ""

    for page_num in range(len(doc)):
        page = doc[page_num]

        # Render page as image at 300 DPI
        mat  = fitz.Matrix(300 / 72, 300 / 72)
        pix  = page.get_pixmap(matrix=mat)
        img  = Image.open(io.BytesIO(pix.tobytes("png")))

        # Run OCR
        page_text = pytesseract.image_to_string(img)
        text += f"\n[PAGE {page_num + 1}]\n{page_text}"

    doc.close()
    return text.strip()


def smart_extract_text(pdf_bytes: bytes) -> str:
    """
    Try normal extraction first.
    If it returns less than 100 chars, use OCR instead.
    This handles both text-based and scanned PDFs automatically.
    """
    normal_text = extract_text_from_pdf(pdf_bytes)

    if len(normal_text.strip()) < 100:
        print("Low text detected — switching to OCR extraction")
        return extract_text_with_ocr(pdf_bytes)

    return normal_text