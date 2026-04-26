# Agent Guide

This repository contains a local Python pipeline that converts a research paper PDF into a Xiaohongshu-style Chinese markdown note.

## Project Shape

- `pipeline.py`: CLI entrypoint and orchestration.
- `tools/pdf_parser.py`: PDF text extraction, identity extraction, embedded image extraction, vector figure crop rendering, key-page selection, and page PNG rendering with `pymupdf`.
- `tools/equation_extractor.py`: equation candidate heuristics and markdown LaTeX validation.
- `tools/md_to_pdf.py`: pure-Python markdown-to-PDF rendering with ReportLab.
- `llm/llm_client.py`: provider abstraction for OpenAI, OpenAI-compatible base URLs, LiteLLM, and OpenRouter.
- `prompts/extract_prompt.md`: stage 1 structured extraction prompt.
- `prompts/summarize_prompt.md`: stage 2 Chinese markdown rewrite prompt.
- `config.yaml`: default provider/model/runtime settings.
- `outputs/`: generated markdown, PDF, JSON, and page assets; generated files are ignored by git.

## Run Commands

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the pipeline:

```bash
python pipeline.py --pdf path/to/paper.pdf --config config.yaml
```

Run with manual key pages:

```bash
python pipeline.py --pdf path/to/paper.pdf --key-pages 1,3,7
```

Run with equations enabled:

```bash
python pipeline.py --pdf path/to/paper.pdf --with-equations
```

Run with PDF export:

```bash
python pipeline.py --pdf path/to/paper.pdf --export-pdf
```

Run syntax checks:

```bash
python -m py_compile pipeline.py tools/pdf_parser.py tools/equation_extractor.py tools/md_to_pdf.py llm/llm_client.py
```

## LLM Configuration

Do not hardcode models or API keys. Use `config.yaml`.

For official OpenAI:

```yaml
provider: openai
model: gpt-4o-mini
api:
  openai_api_key_env: OPENAI_API_KEY
  openai_base_url: null
```

For OpenAI-compatible gateways such as aihubmix:

```yaml
provider: openai
model: gpt-4o-mini
api:
  openai_api_key_env: AIHUBMIX_API_KEY
  openai_base_url: https://api.aihubmix.com/v1
```

For OpenRouter, use `provider: openrouter`; do not reuse `openai_base_url`.

## Implementation Notes

- Keep the public LLM interface as `call_llm(prompt, input, config)`.
- Preserve the two-stage LLM design:
  - stage 1: paper text plus equation hints to structured JSON
  - stage 2: structured JSON to markdown
- Keep the six original markdown sections compatible.
- Default key assets should be inserted near related sections, not appended as full pages.
- Prefer embedded PDF images for model/framework/result figures, then fall back to vector-compatible page-region crops.
- Store embedded images in `outputs/assets/<pdf_stem>/images/` and vector crops in `outputs/assets/<pdf_stem>/crops/`.
- Full-page screenshots are only a fallback through `--key-pages`.
- PDF export is pure Python and keeps LaTeX formulas as readable text in v1.
- Equations are disabled by default. Only extract/show formulas when config enables them or `--with-equations` is passed.
- Do not invent formulas. If enabled and PDF text cannot recover an equation, preserve the `未清晰提取` behavior.
- Keep generated outputs out of git unless the user explicitly asks for sample artifacts.
- Prefer small, focused changes and update README examples when command behavior changes.
