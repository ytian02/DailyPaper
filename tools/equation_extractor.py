from __future__ import annotations

import re


MATH_PATTERNS = [
    r"=",
    r"≤|>=|>=|<|>",
    r"∑|Σ|\\sum",
    r"∫|\\int",
    r"\barg\s*min\b|\bargmin\b|\barg\s*max\b|\bargmax\b",
    r"\blog\b|\bexp\b|\bsigmoid\b|\bsoftmax\b",
    r"\bloss\b|\bobjective\b|\blikelihood\b|\bgradient\b",
    r"\bmin\b|\bmax\b",
    r"\bL\s*\(|\bP\s*\(|\bp\s*\(",
    r"[αβγδθλμσφω]|[A-Za-z]_[A-Za-z0-9]|[A-Za-z]\^[A-Za-z0-9]",
    r"\([0-9]+\)\s*$",
]


def extract_equation_candidates(text: str, context_window: int = 1, max_candidates: int = 80) -> list[dict]:
    """Find likely equation snippets in extracted PDF text.

    These candidates are hints for the LLM, not authoritative equations.
    """
    lines = [line.strip() for line in text.splitlines()]
    compiled = [re.compile(pattern, re.IGNORECASE) for pattern in MATH_PATTERNS]
    candidates: list[dict] = []
    seen: set[str] = set()

    for index, line in enumerate(lines):
        if not line or len(line) < 3:
            continue

        score = _math_score(line, compiled)
        if score < 2:
            continue

        start = max(0, index - context_window)
        end = min(len(lines), index + context_window + 1)
        snippet = "\n".join(item for item in lines[start:end] if item).strip()
        normalized = re.sub(r"\s+", " ", snippet)
        if normalized in seen:
            continue
        seen.add(normalized)

        candidates.append(
            {
                "line_number": index + 1,
                "score": score,
                "snippet": snippet,
            }
        )
        if len(candidates) >= max_candidates:
            break

    return candidates


def validate_latex_blocks(markdown: str) -> list[str]:
    """Return lightweight warnings for suspicious markdown LaTeX syntax."""
    warnings: list[str] = []

    if markdown.count("$$") % 2 != 0:
        warnings.append("Unmatched block math delimiter '$$'.")

    inline_markdown = re.sub(r"\$\$.*?\$\$", "", markdown, flags=re.DOTALL)
    single_dollar_count = len(re.findall(r"(?<!\$)\$(?!\$)", inline_markdown))
    if single_dollar_count % 2 != 0:
        warnings.append("Unmatched inline math delimiter '$'.")

    for label, pattern in (
        ("block", r"\$\$(.*?)\$\$"),
        ("inline", r"(?<!\$)\$(?!\$)(.*?)(?<!\$)\$(?!\$)"),
    ):
        for match in re.finditer(pattern, markdown, flags=re.DOTALL):
            content = match.group(1).strip()
            if not content:
                warnings.append(f"Empty {label} math expression.")
                continue
            brace_warning = _brace_warning(content)
            if brace_warning:
                warnings.append(f"{label.title()} math may be malformed: {brace_warning}")

    return warnings


def _math_score(line: str, compiled_patterns: list[re.Pattern]) -> int:
    score = sum(1 for pattern in compiled_patterns if pattern.search(line))
    operator_count = len(re.findall(r"[=+\-*/^_<>]|≤|≥|∑|Σ|∫", line))
    if operator_count >= 3:
        score += 1
    if re.search(r"\([0-9]+\)\s*$", line):
        score += 1
    return score


def _brace_warning(content: str) -> str | None:
    balance = 0
    escaped = False
    for char in content:
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "{":
            balance += 1
        elif char == "}":
            balance -= 1
        if balance < 0:
            return "extra closing brace"
    if balance > 0:
        return "missing closing brace"
    return None
