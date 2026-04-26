from pathlib import Path


class PDFParseError(RuntimeError):
    """Raised when a PDF cannot be parsed into usable text."""


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract page-joined text from a text-based PDF."""
    path = Path(pdf_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"PDF file does not exist: {path}")
    if not path.is_file():
        raise PDFParseError(f"PDF path is not a file: {path}")

    try:
        import fitz
    except ImportError as exc:
        raise PDFParseError(
            "Missing dependency 'pymupdf'. Install dependencies with: pip install -r requirements.txt"
        ) from exc

    try:
        document = fitz.open(path)
    except Exception as exc:
        raise PDFParseError(f"Failed to open PDF: {path}") from exc

    try:
        pages: list[str] = []
        for index, page in enumerate(document, start=1):
            page_text = page.get_text("text").strip()
            if page_text:
                pages.append(f"[Page {index}]\n{page_text}")
    finally:
        document.close()

    text = "\n\n".join(pages).strip()
    if not text:
        raise PDFParseError(
            "No text was extracted from the PDF. OCR/scanned PDFs are not supported in v1."
        )
    return text
