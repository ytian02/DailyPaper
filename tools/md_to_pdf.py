from __future__ import annotations

import html
import re
import sys
from pathlib import Path
from typing import Any


class MarkdownPDFError(RuntimeError):
    """Raised when markdown cannot be rendered to PDF."""


def markdown_to_pdf(
    markdown: str,
    output_path: str | Path,
    base_dir: str | Path,
    pdf_config: dict[str, Any] | None = None,
) -> Path:
    """Render a small markdown subset to PDF with ReportLab."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import Image, Paragraph, Preformatted, SimpleDocTemplate, Spacer
    except ImportError as exc:
        raise MarkdownPDFError(
            "Missing dependency 'reportlab'. Install dependencies with: pip install -r requirements.txt"
        ) from exc

    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    base = Path(base_dir).expanduser().resolve()
    config = pdf_config or {}

    font_name = _register_font(config, pdfmetrics, UnicodeCIDFont, TTFont)
    styles = _build_styles(font_name, colors, TA_LEFT, getSampleStyleSheet, ParagraphStyle)
    story = _markdown_to_story(markdown, base, styles, Image, Paragraph, Preformatted, Spacer, inch)

    document = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        rightMargin=0.65 * inch,
        leftMargin=0.65 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.65 * inch,
    )
    document.build(story)
    return output


def _register_font(config, pdfmetrics, UnicodeCIDFont, TTFont) -> str:
    font_path = config.get("font_path")
    font_name = config.get("font_name") or "DailyPaperFont"

    if font_path:
        path = Path(font_path).expanduser().resolve()
        if not path.exists():
            raise MarkdownPDFError(f"Configured PDF font does not exist: {path}")
        pdfmetrics.registerFont(TTFont(font_name, str(path)))
        return font_name

    try:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        return "STSong-Light"
    except Exception:
        print(
            "Warning: Chinese PDF font was not configured and STSong-Light is unavailable; "
            "Chinese text may not render correctly.",
            file=sys.stderr,
        )
        return "Helvetica"


def _build_styles(font_name, colors, TA_LEFT, getSampleStyleSheet, ParagraphStyle) -> dict[str, Any]:
    base = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle(
            "DailyPaperH1",
            parent=base["Heading1"],
            fontName=font_name,
            fontSize=20,
            leading=26,
            spaceAfter=12,
        ),
        "h2": ParagraphStyle(
            "DailyPaperH2",
            parent=base["Heading2"],
            fontName=font_name,
            fontSize=15,
            leading=20,
            spaceBefore=10,
            spaceAfter=8,
        ),
        "body": ParagraphStyle(
            "DailyPaperBody",
            parent=base["BodyText"],
            fontName=font_name,
            fontSize=10.5,
            leading=16,
            alignment=TA_LEFT,
            spaceAfter=7,
        ),
        "bullet": ParagraphStyle(
            "DailyPaperBullet",
            parent=base["BodyText"],
            fontName=font_name,
            fontSize=10.5,
            leading=16,
            leftIndent=16,
            firstLineIndent=-10,
            spaceAfter=5,
        ),
        "code": ParagraphStyle(
            "DailyPaperCode",
            parent=base["Code"],
            fontName=font_name,
            fontSize=9,
            leading=13,
            borderColor=colors.lightgrey,
            borderWidth=0.5,
            borderPadding=6,
            backColor=colors.whitesmoke,
            spaceBefore=6,
            spaceAfter=8,
        ),
        "caption": ParagraphStyle(
            "DailyPaperCaption",
            parent=base["BodyText"],
            fontName=font_name,
            fontSize=9,
            leading=13,
            textColor=colors.grey,
            alignment=TA_LEFT,
            spaceAfter=8,
        ),
    }


def _markdown_to_story(markdown, base_dir, styles, Image, Paragraph, Preformatted, Spacer, inch):
    story = []
    lines = markdown.splitlines()
    index = 0
    in_code = False
    code_lines: list[str] = []
    in_math = False
    math_lines: list[str] = []

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_code:
                story.append(Preformatted("\n".join(code_lines), styles["code"]))
                code_lines = []
                in_code = False
            else:
                in_code = True
            index += 1
            continue

        if in_code:
            code_lines.append(line)
            index += 1
            continue

        if stripped == "$$":
            if in_math:
                story.append(Preformatted("\n".join(math_lines), styles["code"]))
                math_lines = []
                in_math = False
            else:
                in_math = True
            index += 1
            continue

        if in_math:
            math_lines.append(line)
            index += 1
            continue

        image_match = re.match(r"!\[(.*?)\]\((.*?)\)", stripped)
        if image_match:
            alt_text = image_match.group(1).strip()
            image_ref = image_match.group(2).strip()
            image_path = (base_dir / image_ref).resolve()
            if image_path.exists():
                story.append(_fit_image(str(image_path), Image, inch))
                if alt_text:
                    story.append(Paragraph(_inline_markup(alt_text), styles["caption"]))
            else:
                story.append(
                    Paragraph(
                        _inline_markup(f"[Missing image: {image_ref}]"),
                        styles["caption"],
                    )
                )
            index += 1
            continue

        if not stripped:
            story.append(Spacer(1, 0.08 * inch))
            index += 1
            continue

        if stripped.startswith("# "):
            story.append(Paragraph(_inline_markup(stripped[2:].strip()), styles["h1"]))
        elif stripped.startswith("## "):
            story.append(Paragraph(_inline_markup(stripped[3:].strip()), styles["h2"]))
        elif stripped.startswith(("- ", "* ")):
            story.append(Paragraph("• " + _inline_markup(stripped[2:].strip()), styles["bullet"]))
        else:
            paragraph_lines = [stripped]
            while index + 1 < len(lines) and _is_paragraph_continuation(lines[index + 1]):
                index += 1
                paragraph_lines.append(lines[index].strip())
            story.append(Paragraph(_inline_markup(" ".join(paragraph_lines)), styles["body"]))
        index += 1

    if code_lines:
        story.append(Preformatted("\n".join(code_lines), styles["code"]))
    if math_lines:
        story.append(Preformatted("\n".join(math_lines), styles["code"]))
    return story


def _is_paragraph_continuation(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    return not (
        stripped.startswith("#")
        or stripped.startswith("!")
        or stripped.startswith("```")
        or stripped == "$$"
        or stripped.startswith(("- ", "* "))
    )


def _inline_markup(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<font name='Courier'>\1</font>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", escaped)
    return escaped


def _fit_image(path: str, Image, inch):
    image = Image(path)
    max_width = 6.8 * inch
    max_height = 8.6 * inch
    width, height = image.drawWidth, image.drawHeight
    scale = min(max_width / width, max_height / height, 1.0)
    image.drawWidth = width * scale
    image.drawHeight = height * scale
    return image
