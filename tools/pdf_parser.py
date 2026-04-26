from pathlib import Path
import re


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


def extract_page_texts(pdf_path: str) -> list[dict]:
    """Extract text per page for page-level scoring and selection."""
    path = _validate_pdf_path(pdf_path)
    fitz = _import_fitz()

    try:
        document = fitz.open(path)
    except Exception as exc:
        raise PDFParseError(f"Failed to open PDF: {path}") from exc

    try:
        pages = []
        for index, page in enumerate(document, start=1):
            pages.append(
                {
                    "page": index,
                    "text": page.get_text("text").strip(),
                }
            )
    finally:
        document.close()

    if not pages:
        raise PDFParseError(f"PDF has no pages: {path}")
    return pages


def select_key_pages(page_texts: list[dict], max_pages: int = 5) -> list[dict]:
    """Select title/framework/result pages using lightweight text heuristics."""
    if not page_texts or max_pages <= 0:
        return []

    selected: dict[int, dict] = {}
    first_page = page_texts[0]["page"]
    selected[first_page] = {"page": first_page, "caption": "标题与作者信息", "score": 999}

    scored = []
    for item in page_texts:
        page = int(item["page"])
        text = str(item.get("text", ""))
        score, caption = _score_key_page(text)
        if score > 0:
            scored.append({"page": page, "caption": caption, "score": score})

    scored.sort(key=lambda item: (-item["score"], item["page"]))
    for item in scored:
        if len(selected) >= max_pages:
            break
        selected.setdefault(item["page"], item)

    return [
        {"page": item["page"], "caption": item["caption"]}
        for item in sorted(selected.values(), key=lambda item: item["page"])
    ][:max_pages]


def render_pdf_pages(
    pdf_path: str,
    pages: list[int],
    output_dir: str | Path,
    zoom: float = 2.0,
) -> list[dict]:
    """Render 1-based PDF page numbers to PNG files."""
    path = _validate_pdf_path(pdf_path)
    fitz = _import_fitz()
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        document = fitz.open(path)
    except Exception as exc:
        raise PDFParseError(f"Failed to open PDF: {path}") from exc

    rendered = []
    try:
        page_count = document.page_count
        matrix = fitz.Matrix(float(zoom), float(zoom))
        for page_number in _dedupe_pages(pages):
            if page_number < 1 or page_number > page_count:
                raise PDFParseError(
                    f"Page {page_number} is out of range. PDF has {page_count} pages."
                )
            page = document.load_page(page_number - 1)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            image_path = target_dir / f"page_{page_number:03d}.png"
            pixmap.save(image_path)
            rendered.append({"page": page_number, "path": image_path})
    finally:
        document.close()

    return rendered


def _validate_pdf_path(pdf_path: str) -> Path:
    path = Path(pdf_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"PDF file does not exist: {path}")
    if not path.is_file():
        raise PDFParseError(f"PDF path is not a file: {path}")
    return path


def _import_fitz():
    try:
        import fitz
    except ImportError as exc:
        raise PDFParseError(
            "Missing dependency 'pymupdf'. Install dependencies with: pip install -r requirements.txt"
        ) from exc
    return fitz


def _score_key_page(text: str) -> tuple[int, str]:
    normalized = text.lower()
    framework_terms = [
        "framework",
        "architecture",
        "model",
        "method",
        "overview",
        "onetrans",
        "transformer",
        "feature interaction",
        "sequence modeling",
    ]
    result_terms = [
        "experiment",
        "result",
        "metric",
        "ablation",
        "auc",
        "gauc",
        "ctr",
        "online",
        "offline",
        "table",
    ]
    figure_bonus = len(re.findall(r"\b(fig\.?|figure|table)\s*\d+", normalized))
    framework_score = sum(normalized.count(term) for term in framework_terms)
    result_score = sum(normalized.count(term) for term in result_terms)
    score = framework_score * 3 + result_score * 3 + figure_bonus * 5

    if framework_score >= result_score:
        caption = "模型框架或方法示意"
    else:
        caption = "实验结果或指标对比"
    return score, caption


def _dedupe_pages(pages: list[int]) -> list[int]:
    deduped = []
    seen = set()
    for page in pages:
        if page in seen:
            continue
        seen.add(page)
        deduped.append(page)
    return deduped
