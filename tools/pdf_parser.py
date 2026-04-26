from __future__ import annotations

import re
from pathlib import Path


class PDFParseError(RuntimeError):
    """Raised when a PDF cannot be parsed into usable text."""


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract page-joined text from a text-based PDF."""
    path = _validate_pdf_path(pdf_path)
    fitz = _import_fitz()

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


def extract_paper_identity(pdf_path: str) -> dict:
    """Extract title/authors/abstract-like text from the first pages."""
    pages = extract_page_texts(pdf_path)
    first_text = pages[0]["text"] if pages else ""
    title, authors = _extract_title_and_authors(first_text)
    abstract = _extract_abstract(pages[:3])
    return {"title": title, "authors": authors, "abstract": abstract}


def extract_embedded_images(pdf_path: str, output_dir: str | Path) -> list[dict]:
    """Extract embedded PDF image objects and save useful ones as PNG files."""
    path = _validate_pdf_path(pdf_path)
    fitz = _import_fitz()
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    page_texts = {item["page"]: item.get("text", "") for item in extract_page_texts(str(path))}

    try:
        document = fitz.open(path)
    except Exception as exc:
        raise PDFParseError(f"Failed to open PDF: {path}") from exc

    images: list[dict] = []
    seen_xrefs: set[int] = set()
    try:
        for page_index in range(document.page_count):
            page_number = page_index + 1
            page = document.load_page(page_index)
            for image_index, image_info in enumerate(page.get_images(full=True), start=1):
                xref = int(image_info[0])
                if xref in seen_xrefs:
                    continue
                seen_xrefs.add(xref)
                width = int(image_info[2])
                height = int(image_info[3])
                if _is_tiny_or_logo_like(width, height):
                    continue

                try:
                    pixmap = fitz.Pixmap(document, xref)
                    if pixmap.n - pixmap.alpha > 3:
                        pixmap = fitz.Pixmap(fitz.csRGB, pixmap)
                    image_path = target_dir / f"figure_{page_number:03d}_{image_index:02d}.png"
                    pixmap.save(image_path)
                except Exception:
                    continue

                category, score = _classify_image_context(page_texts.get(page_number, ""))
                images.append(
                    {
                        "page": page_number,
                        "path": image_path,
                        "width": width,
                        "height": height,
                        "category": category,
                        "score": score + _image_size_score(width, height),
                    }
                )
    finally:
        document.close()

    return images


def select_key_images(images: list[dict], max_images: int = 4) -> list[dict]:
    """Select representative embedded paper images for markdown insertion."""
    if max_images <= 0:
        return []

    candidates = [item for item in images if int(item.get("score", 0)) > 0]
    candidates.sort(key=lambda item: (-int(item.get("score", 0)), int(item.get("page", 0))))

    selected: list[dict] = []
    seen_paths: set[Path] = set()
    for item in candidates:
        path = Path(item["path"])
        if path in seen_paths:
            continue
        seen_paths.add(path)
        selected.append(item)
        if len(selected) >= max_images:
            break

    return sorted(selected, key=lambda item: int(item.get("page", 0)))


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


def _extract_title_and_authors(first_page_text: str) -> tuple[str, str]:
    lines = _clean_lines(first_page_text)
    if not lines:
        return "", ""

    title_lines: list[str] = []
    for index, line in enumerate(lines[:8]):
        lower = line.lower()
        if lower.startswith(("abstract", "keywords", "introduction")):
            break
        if _looks_like_affiliation(line):
            break
        if index > 0 and _looks_like_author_name(line):
            break
        title_lines.append(line)
        if len(title_lines) >= 3:
            break

    title = " ".join(title_lines[:3]).strip()
    author_candidates = []
    for line in lines[len(title_lines) :]:
        lower = line.lower()
        if lower.startswith(("abstract", "keywords", "introduction")):
            break
        if "@" in line or _looks_like_affiliation(line):
            continue
        if _looks_like_author_name(line):
            author_candidates.append(line)
        if len(author_candidates) >= 8:
            break

    return title, " ".join(author_candidates).strip()


def _extract_abstract(pages: list[dict]) -> str:
    text = "\n".join(str(page.get("text", "")) for page in pages)
    compact = re.sub(r"\s+", " ", text).strip()
    match = re.search(
        r"\babstract\b[:.\s-]*(.*?)(?:\b(?:keywords?|index terms|1\s+introduction|introduction)\b)",
        compact,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()[:1200]
    return ""


def _clean_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _looks_like_affiliation(line: str) -> bool:
    lower = line.lower()
    return any(
        token in lower
        for token in (
            "university",
            "institute",
            "college",
            "department",
            "school of",
            "bytedance",
            "laboratory",
        )
    )


def _looks_like_author_name(line: str) -> bool:
    cleaned = re.sub(r"[*†‡§]", "", line).strip()
    if "," in cleaned:
        return False
    if not cleaned or any(char.isdigit() for char in cleaned):
        return False
    words = cleaned.replace("-", " ").split()
    if not 1 <= len(words) <= 4:
        return False
    return all(word[:1].isupper() for word in words if word[:1].isalpha())


def _is_tiny_or_logo_like(width: int, height: int) -> bool:
    if width < 160 or height < 120:
        return True
    area = width * height
    if area < 50_000:
        return True
    aspect = max(width / max(height, 1), height / max(width, 1))
    return aspect > 8


def _classify_image_context(text: str) -> tuple[str, int]:
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
    framework_score = sum(normalized.count(term) for term in framework_terms)
    result_score = sum(normalized.count(term) for term in result_terms)
    figure_bonus = len(re.findall(r"\b(fig\.?|figure|table)\s*\d+", normalized))

    if framework_score >= result_score and framework_score > 0:
        return "method", framework_score * 4 + figure_bonus * 2
    if result_score > 0:
        return "offline_metrics", result_score * 4 + figure_bonus * 2
    return "general", figure_bonus


def _image_size_score(width: int, height: int) -> int:
    area = width * height
    if area >= 1_000_000:
        return 4
    if area >= 400_000:
        return 2
    return 1


def _score_key_page(text: str) -> tuple[int, str]:
    category, score = _classify_image_context(text)
    if category == "method":
        return score, "模型框架或方法示意"
    if category == "offline_metrics":
        return score, "实验结果或指标对比"
    return score, "论文关键页"


def _dedupe_pages(pages: list[int]) -> list[int]:
    deduped = []
    seen = set()
    for page in pages:
        if page in seen:
            continue
        seen.add(page)
        deduped.append(page)
    return deduped
