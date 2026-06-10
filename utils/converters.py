"""File converters for LLMNotes - converts various formats to markdown"""

import os
import shutil
from datetime import datetime
import subprocess
import tempfile
import re

from config import NOTES_DIR, SOURCES_DIR, IMAGE_EXTENSIONS


def sanitize_filename(name):
    """Sanitize a string for use as a filename"""
    name = re.sub(r'[^\w\s-]', '', name)
    name = re.sub(r'[-\s]+', '-', name)
    return name.strip('-').lower() or 'untitled'


def generate_note_filename(title, ext='.md'):
    """Generate a dated filename for a note"""
    date_str = datetime.now().strftime('%Y%m%d')
    safe_title = sanitize_filename(title)[:50]
    return f"{date_str}_{safe_title}{ext}"


def convert_to_markdown(filepath, title=None):
    """
    Convert any supported file to markdown.
    Returns (md_content, note_filename, source_filename)
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found: {filepath}")

    ext = os.path.splitext(filepath)[1].lower()
    basename = os.path.basename(filepath)
    title = title or os.path.splitext(basename)[0]

    if ext == '.md':
        return _handle_md(filepath, title)
    elif ext == '.pdf':
        return _handle_pdf(filepath, title)
    elif ext in IMAGE_EXTENSIONS:
        return _handle_image(filepath, title)
    elif ext == '.txt':
        return _handle_txt(filepath, title)
    else:
        return _handle_other(filepath, title)


def _handle_md(filepath, title):
    """Already markdown - just copy and index"""
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    note_filename = generate_note_filename(title)
    source_dest = os.path.join(SOURCES_DIR, os.path.basename(filepath))

    # Copy source to sources dir
    shutil.copy2(filepath, source_dest)

    # Copy to notes dir
    note_path = os.path.join(NOTES_DIR, note_filename)
    shutil.copy2(filepath, note_path)

    return content, note_filename, os.path.basename(filepath)


def _handle_pdf(filepath, title):
    """Extract text from PDF using pdfminer"""
    from pdfminer.high_level import extract_text

    text = extract_text(filepath)
    content = f"# {title}\n\n> Extracted from PDF: {os.path.basename(filepath)}\n\n{text}"

    note_filename = generate_note_filename(title)
    source_dest = os.path.join(SOURCES_DIR, os.path.basename(filepath))
    shutil.copy2(filepath, source_dest)

    note_path = os.path.join(NOTES_DIR, note_filename)
    with open(note_path, 'w', encoding='utf-8') as f:
        f.write(content)

    return content, note_filename, os.path.basename(filepath)


def _handle_image(filepath, title):
    """Extract text from image using OCR (tesseract)"""
    try:
        from PIL import Image
        import pytesseract

        img = Image.open(filepath)
        text = pytesseract.image_to_string(img)
    except Exception as e:
        text = f"[OCR failed: {e}]\nPlease ensure tesseract is installed."

    content = f"# {title}\n\n> OCR extracted from: {os.path.basename(filepath)}\n\n{text}"

    note_filename = generate_note_filename(title)
    source_dest = os.path.join(SOURCES_DIR, os.path.basename(filepath))
    shutil.copy2(filepath, source_dest)

    note_path = os.path.join(NOTES_DIR, note_filename)
    with open(note_path, 'w', encoding='utf-8') as f:
        f.write(content)

    return content, note_filename, os.path.basename(filepath)


def _handle_txt(filepath, title):
    """Convert plain text to markdown"""
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        text = f.read()

    content = f"# {title}\n\n> Extracted from: {os.path.basename(filepath)}\n\n{text}"

    note_filename = generate_note_filename(title)
    source_dest = os.path.join(SOURCES_DIR, os.path.basename(filepath))
    shutil.copy2(filepath, source_dest)

    note_path = os.path.join(NOTES_DIR, note_filename)
    with open(note_path, 'w', encoding='utf-8') as f:
        f.write(content)

    return content, note_filename, os.path.basename(filepath)


def _handle_other(filepath, title):
    """Generic handler for other text-based files"""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            text = f.read()
    except:
        text = f"[Could not read file: {os.path.basename(filepath)}]"

    content = f"# {title}\n\n> Extracted from: {os.path.basename(filepath)}\n\n```\n{text}\n```"

    note_filename = generate_note_filename(title)
    source_dest = os.path.join(SOURCES_DIR, os.path.basename(filepath))
    shutil.copy2(filepath, source_dest)

    note_path = os.path.join(NOTES_DIR, note_filename)
    with open(note_path, 'w', encoding='utf-8') as f:
        f.write(content)

    return content, note_filename, os.path.basename(filepath)


def add_text_as_note(text, title):
    """Add raw pasted text as a note"""
    title = title or f"pasted-text-{datetime.now().strftime('%H%M%S')}"
    content = f"# {title}\n\n{text}"

    note_filename = generate_note_filename(title)

    note_path = os.path.join(NOTES_DIR, note_filename)
    with open(note_path, 'w', encoding='utf-8') as f:
        f.write(content)

    return content, note_filename, None


def chunk_text(text, chunk_size=1000, overlap=200):
    """Split text into overlapping chunks for RAG"""
    if not text:
        return []

    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + chunk_size, text_len)
        chunk = text[start:end]

        # Try to break at a natural boundary
        if end < text_len:
            # Find last sentence boundary or newline
            boundary = max(
                chunk.rfind('\n\n'),
                chunk.rfind('. '),
                chunk.rfind('?\n'),
                chunk.rfind('!\n')
            )
            if boundary > chunk_size // 2:
                end = start + boundary + 1
                chunk = text[start:end]

        chunks.append(chunk.strip())
        start = end - overlap if end < text_len else text_len

    return [c for c in chunks if c.strip()]