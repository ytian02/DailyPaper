# Agent Guide

This repository contains a local Python pipeline that converts a research paper PDF into a Xiaohongshu-style Chinese markdown note.

## Project Shape

- `pipeline.py`: CLI entrypoint and orchestration.
- `tools/pdf_parser.py`: PDF text extraction with `pymupdf`.
- `tools/equation_extractor.py`: equation candidate heuristics and markdown LaTeX validation.
- `llm/llm_client.py`: provider abstraction for OpenAI, OpenAI-compatible base URLs, LiteLLM, and OpenRouter.
- `prompts/extract_prompt.md`: stage 1 structured extraction prompt.
- `prompts/summarize_prompt.md`: stage 2 Chinese markdown rewrite prompt.
- `config.yaml`: default provider/model/runtime settings.
- `outputs/`: generated markdown and JSON outputs; generated files are ignored by git.

## Run Commands

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the pipeline:

```bash
python pipeline.py --pdf path/to/paper.pdf --config config.yaml
```

Run syntax checks:

```bash
python -m py_compile pipeline.py tools/pdf_parser.py tools/equation_extractor.py llm/llm_client.py
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
- Do not invent formulas. If PDF text cannot recover an equation, preserve the `未清晰提取` behavior.
- Keep generated outputs out of git unless the user explicitly asks for sample artifacts.
- Prefer small, focused changes and update README examples when command behavior changes.
