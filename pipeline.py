from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from llm.llm_client import call_llm, load_config
from tools.equation_extractor import extract_equation_candidates, validate_latex_blocks
from tools.pdf_parser import extract_text_from_pdf


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

        print("Extracting equation candidates...")
        equation_candidates = extract_equation_candidates(paper_text)

        print("Running LLM stage 1: structured extraction...")
        extract_prompt = _read_prompt("prompts/extract_prompt.md")
        extraction_input = {
            "paper_text": paper_text,
            "equation_candidates": equation_candidates,
        }
        raw_json = call_llm(extract_prompt, extraction_input, config)
        structured = normalize_extraction(parse_json_response(raw_json))

        if config.get("pipeline", {}).get("save_intermediate_json", True):
            json_path = output_dir / f"{pdf_path.stem}.json"
            json_path.write_text(
                json.dumps(structured, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"Saved structured JSON: {json_path}")

        print("Running LLM stage 2: Xiaohongshu markdown rewrite...")
        summarize_prompt = _read_prompt("prompts/summarize_prompt.md")
        markdown = call_llm(summarize_prompt, structured, config).strip()

        section_warnings = validate_markdown_sections(markdown)
        latex_warnings = validate_latex_blocks(markdown)
        for warning in section_warnings + latex_warnings:
            print(f"Warning: {warning}", file=sys.stderr)

        md_path = Path(args.output).expanduser().resolve() if args.output else output_dir / f"{pdf_path.stem}.md"
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(markdown + "\n", encoding="utf-8")
        print(f"Saved markdown: {md_path}")
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
