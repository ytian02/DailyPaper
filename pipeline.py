from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from llm.llm_client import call_llm, load_config
from tools.equation_extractor import extract_equation_candidates, validate_latex_blocks
from tools.md_to_pdf import markdown_to_pdf
from tools.pdf_parser import (
    extract_embedded_images,
    extract_paper_identity,
    extract_page_texts,
    extract_text_from_pdf,
    render_pdf_pages,
    select_key_images,
    select_key_pages,
)


REQUIRED_JSON_KEYS = {
    "problem": "",
    "method": "",
    "innovation": [],
    "equations": [],
    "offline_metrics": "未提及",
    "online_metrics": "未提及",
}

REQUIRED_MARKDOWN_SECTIONS = [
    "# 简短介绍",
    "## 研究问题",
    "## 方法创新",
    "## 方法细节",
    "## 离线指标",
    "## 线上指标",
]

BASE_DIR = Path(__file__).resolve().parent


def main() -> int:
    args = parse_args()

    try:
        config = load_config(args.config)
        pdf_path = Path(args.pdf).expanduser().resolve()
        output_dir = Path(
            args.output_dir or config.get("pipeline", {}).get("output_dir", "outputs")
        ).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        print(f"Parsing PDF: {pdf_path}")
        paper_text = extract_text_from_pdf(str(pdf_path))
        paper_text = _truncate_text_if_needed(paper_text, config)

        with_equations = _with_equations(args, config)
        if with_equations:
            print("Extracting equation candidates...")
            equation_candidates = extract_equation_candidates(paper_text)
        else:
            print("Skipping equation extraction by default. Use --with-equations to enable it.")
            equation_candidates = []

        print("Running LLM stage 1: structured extraction...")
        extract_prompt = _read_prompt("prompts/extract_prompt.md")
        extraction_input = {
            "paper_text": paper_text,
            "equation_candidates": equation_candidates,
            "extract_equations": with_equations,
        }
        raw_json = call_llm(extract_prompt, extraction_input, config)
        structured = normalize_extraction(parse_json_response(raw_json))
        if not with_equations:
            structured["equations"] = []

        if config.get("pipeline", {}).get("save_intermediate_json", True):
            json_path = output_dir / f"{pdf_path.stem}.json"
            json_path.write_text(
                json.dumps(structured, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"Saved structured JSON: {json_path}")

        print("Running LLM stage 2: Xiaohongshu markdown rewrite...")
        summarize_prompt = _read_prompt("prompts/summarize_prompt.md")
        markdown = call_llm(
            summarize_prompt,
            {
                "structured_paper": structured,
                "show_equations": with_equations and _show_equations(args, config),
            },
            config,
        ).strip()

        md_path = Path(args.output).expanduser().resolve() if args.output else output_dir / f"{pdf_path.stem}.md"
        if _should_insert_key_assets(args, config):
            print("Extracting and inserting key paper assets...")
            markdown = insert_key_assets(markdown, pdf_path, md_path, output_dir, config)

        if _should_insert_key_pages(args, config):
            print("Selecting and rendering key paper pages...")
            markdown = append_key_pages_section(markdown, pdf_path, md_path, output_dir, args, config)

        section_warnings = validate_markdown_sections(markdown)
        latex_warnings = validate_latex_blocks(markdown) if with_equations else []
        for warning in section_warnings + latex_warnings:
            print(f"Warning: {warning}", file=sys.stderr)

        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(markdown + "\n", encoding="utf-8")
        print(f"Saved markdown: {md_path}")

        if args.export_pdf or config.get("pipeline", {}).get("export_pdf", False):
            pdf_output = (
                Path(args.pdf_output).expanduser().resolve()
                if args.pdf_output
                else output_dir / f"{pdf_path.stem}.pdf"
            )
            print("Rendering markdown PDF...")
            markdown_to_pdf(
                markdown,
                pdf_output,
                base_dir=md_path.parent,
                pdf_config=config.get("pdf", {}),
            )
            print(f"Saved PDF: {pdf_output}")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a research paper PDF into a Xiaohongshu-style markdown note."
    )
    parser.add_argument("--pdf", required=True, help="Local path to the research paper PDF.")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml.")
    parser.add_argument("--output", help="Optional explicit markdown output path.")
    parser.add_argument("--output-dir", help="Optional output directory override.")
    parser.add_argument("--key-pages", help="Comma-separated 1-based PDF pages to render, e.g. 1,3,7.")
    parser.add_argument("--no-key-pages", action="store_true", help="Disable key paper page images in markdown.")
    parser.add_argument("--no-key-assets", action="store_true", help="Disable extracted title/abstract/images in markdown.")
    parser.add_argument("--with-equations", action="store_true", help="Enable equation extraction and LaTeX display.")
    parser.add_argument("--export-pdf", action="store_true", help="Render the final markdown to PDF.")
    parser.add_argument("--pdf-output", help="Optional explicit PDF output path.")
    return parser.parse_args()


def parse_json_response(response: str) -> dict[str, Any]:
    cleaned = response.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    json_text = _extract_json_object(cleaned)
    parsed = _loads_json_with_latex_repair(json_text)

    if not isinstance(parsed, dict):
        raise ValueError("Stage 1 JSON must be an object.")
    return parsed


def _extract_json_object(text: str) -> str:
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise ValueError("Stage 1 response did not contain valid JSON.")
        return match.group(0)


def _loads_json_with_latex_repair(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as first_error:
        repaired = _escape_invalid_json_backslashes(text)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError as second_error:
            raise ValueError(
                "Stage 1 response was not valid JSON. This is often caused by "
                "unescaped LaTeX backslashes; update the prompt/model output or inspect the raw LLM response."
            ) from second_error


def _escape_invalid_json_backslashes(text: str) -> str:
    """Escape backslashes that are invalid in JSON strings, common in raw LaTeX."""
    return re.sub(r'\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})', r"\\\\", text)


def normalize_extraction(data: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(REQUIRED_JSON_KEYS)
    normalized.update(data)

    if not isinstance(normalized["innovation"], list):
        normalized["innovation"] = [str(normalized["innovation"])]

    if not isinstance(normalized["equations"], list):
        normalized["equations"] = []

    equations = []
    for item in normalized["equations"]:
        if not isinstance(item, dict):
            continue
        equations.append(
            {
                "description": str(item.get("description", "")).strip(),
                "latex": str(item.get("latex", "")).strip(),
            }
        )
    normalized["equations"] = equations

    for key in ("problem", "method", "offline_metrics", "online_metrics"):
        value = normalized.get(key)
        normalized[key] = str(value).strip() if value else REQUIRED_JSON_KEYS[key]

    return normalized


def validate_markdown_sections(markdown: str) -> list[str]:
    warnings = []
    for section in REQUIRED_MARKDOWN_SECTIONS:
        if section not in markdown:
            warnings.append(f"Missing markdown section: {section}")
    return warnings


def append_key_pages_section(
    markdown: str,
    pdf_path: Path,
    md_path: Path,
    output_dir: Path,
    args: argparse.Namespace,
    config: dict[str, Any],
) -> str:
    selected_pages = _resolve_key_pages(pdf_path, args, config)
    if not selected_pages:
        return markdown

    asset_dir = output_dir / "assets" / _safe_path_name(pdf_path.stem)
    page_numbers = [int(item["page"]) for item in selected_pages]
    rendered_pages = render_pdf_pages(
        str(pdf_path),
        page_numbers,
        asset_dir,
        zoom=float(config.get("pipeline", {}).get("render_page_zoom", 2.0)),
    )
    rendered_by_page = {item["page"]: Path(item["path"]) for item in rendered_pages}

    lines = ["", "## 论文关键图页", ""]
    for item in selected_pages:
        page_number = int(item["page"])
        image_path = rendered_by_page.get(page_number)
        if not image_path:
            continue
        relative_image_path = _markdown_relative_path(image_path, md_path.parent)
        caption = str(item.get("caption") or "论文关键页")
        alt = f"论文第 {page_number} 页：{caption}"
        lines.append(f"![{alt}]({relative_image_path})")
        lines.append("")

    return markdown.rstrip() + "\n" + "\n".join(lines).rstrip()


def insert_key_assets(
    markdown: str,
    pdf_path: Path,
    md_path: Path,
    output_dir: Path,
    config: dict[str, Any],
) -> str:
    asset_dir = output_dir / "assets" / _safe_path_name(pdf_path.stem)
    identity = extract_paper_identity(str(pdf_path))
    images = extract_embedded_images(str(pdf_path), asset_dir / "images")
    selected_images = select_key_images(
        images,
        max_images=int(config.get("pipeline", {}).get("key_images_max", 4)),
    )

    result = markdown
    intro_lines = _identity_markdown(identity)
    if intro_lines:
        result = _insert_after_heading(result, "# 简短介绍", intro_lines)

    method_images = [
        _image_markdown(item, md_path.parent, "模型图")
        for item in selected_images
        if item.get("category") == "method"
    ]
    result_images = [
        _image_markdown(item, md_path.parent, "实验结果图")
        for item in selected_images
        if item.get("category") == "offline_metrics"
    ]
    general_images = [
        _image_markdown(item, md_path.parent, "论文图")
        for item in selected_images
        if item.get("category") == "general"
    ]

    if method_images:
        result = _insert_after_heading(result, "## 方法细节", method_images)
    if result_images:
        result = _insert_after_heading(result, "## 离线指标", result_images)
    elif general_images:
        result = _insert_after_heading(result, "## 方法细节", general_images[:1])

    return result


def _resolve_key_pages(pdf_path: Path, args: argparse.Namespace, config: dict[str, Any]) -> list[dict]:
    if args.key_pages:
        return [
            {"page": page, "caption": "用户指定关键页"}
            for page in _parse_key_pages(args.key_pages)
        ]

    page_texts = extract_page_texts(str(pdf_path))
    max_pages = int(config.get("pipeline", {}).get("key_pages_max", 5))
    return select_key_pages(page_texts, max_pages=max_pages)


def _parse_key_pages(value: str) -> list[int]:
    pages = []
    seen = set()
    for raw in value.split(","):
        raw = raw.strip()
        if not raw:
            continue
        if not raw.isdigit():
            raise ValueError(f"Invalid --key-pages value '{raw}'. Expected comma-separated page numbers.")
        page = int(raw)
        if page < 1:
            raise ValueError("--key-pages must use 1-based positive page numbers.")
        if page not in seen:
            seen.add(page)
            pages.append(page)
    if not pages:
        raise ValueError("--key-pages did not contain any valid pages.")
    return pages


def _should_insert_key_pages(args: argparse.Namespace, config: dict[str, Any]) -> bool:
    if args.no_key_pages:
        return False
    if args.key_pages:
        return True
    return bool(config.get("pipeline", {}).get("insert_key_pages", False))


def _should_insert_key_assets(args: argparse.Namespace, config: dict[str, Any]) -> bool:
    if args.no_key_assets:
        return False
    return bool(config.get("pipeline", {}).get("insert_key_assets", True))


def _with_equations(args: argparse.Namespace, config: dict[str, Any]) -> bool:
    return bool(args.with_equations or config.get("pipeline", {}).get("extract_equations", False))


def _show_equations(args: argparse.Namespace, config: dict[str, Any]) -> bool:
    return bool(args.with_equations or config.get("pipeline", {}).get("show_equations", False))


def _identity_markdown(identity: dict) -> list[str]:
    lines = []
    title = str(identity.get("title") or "").strip()
    authors = str(identity.get("authors") or "").strip()
    abstract = str(identity.get("abstract") or "").strip()

    if title:
        lines.append(f"**论文标题**：{title}")
    if authors:
        lines.append(f"**作者信息**：{authors}")
    if abstract:
        lines.append(f"**摘要速览**：{abstract}")
    return lines


def _image_markdown(item: dict, md_base_dir: Path, label: str) -> str:
    page = int(item.get("page", 0))
    image_path = Path(item["path"])
    relative_image_path = _markdown_relative_path(image_path, md_base_dir)
    return f"![{label}｜论文第 {page} 页]({relative_image_path})"


def _insert_after_heading(markdown: str, heading: str, inserted_lines: list[str]) -> str:
    if not inserted_lines or heading not in markdown:
        return markdown

    lines = markdown.splitlines()
    output = []
    inserted = False
    for index, line in enumerate(lines):
        output.append(line)
        if not inserted and line.strip() == heading:
            output.append("")
            output.extend(inserted_lines)
            if index + 1 < len(lines) and lines[index + 1].strip():
                output.append("")
            inserted = True
    return "\n".join(output)


def _markdown_relative_path(path: Path, base_dir: Path) -> str:
    relative = os.path.relpath(path.resolve(), base_dir.resolve())
    return relative.replace(os.sep, "/")


def _safe_path_name(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return safe or "paper"


def _read_prompt(path: str) -> str:
    prompt_path = (BASE_DIR / path).resolve()
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file does not exist: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8")


def _truncate_text_if_needed(text: str, config: dict[str, Any]) -> str:
    max_chars = int(config.get("pipeline", {}).get("max_input_chars", 60000))
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    print(
        f"Warning: extracted text is {len(text)} chars; truncating to {max_chars} chars.",
        file=sys.stderr,
    )
    return text[:max_chars]


if __name__ == "__main__":
    raise SystemExit(main())
