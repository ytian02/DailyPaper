# DailyPaper

Local pipeline for converting a research paper PDF into a Xiaohongshu-style Chinese markdown note.

## Features

- Extracts full text from local text-based PDFs.
- Detects likely equation snippets before LLM extraction.
- Uses two LLM stages:
  - structured extraction JSON
  - Xiaohongshu-style markdown rewrite
- Preserves important formulas as markdown LaTeX.
- Supports OpenAI, OpenAI-compatible gateways, LiteLLM, and OpenRouter through one `call_llm(prompt, input)` interface.

## Install

```bash
pip install -r requirements.txt
```

## Configure

Edit `config.yaml`:

```yaml
provider: openai
model: gpt-4o-mini

api:
  openai_api_key_env: OPENAI_API_KEY
  openai_base_url: null
```

Set the relevant API key:

```bash
$env:OPENAI_API_KEY="your-key"
```

For OpenAI-compatible third-party gateways such as aihubmix, keep `provider: openai` and set a custom base URL:

```yaml
provider: openai
model: gpt-4o-mini

api:
  openai_api_key_env: AIHUBMIX_API_KEY
  openai_base_url: https://api.aihubmix.com/v1
```

```bash
$env:AIHUBMIX_API_KEY="your-key"
```

The API key environment variable name is configurable through `openai_api_key_env`.

For OpenRouter:

```yaml
provider: openrouter
model: openai/gpt-4o-mini
```

```bash
$env:OPENROUTER_API_KEY="your-key"
```

For LiteLLM:

```yaml
provider: litellm
model: gpt-4o-mini
```

## Run

```bash
python pipeline.py --pdf path/to/paper.pdf --config config.yaml
```

Outputs are saved to:

- `outputs/<pdf_name>.json`
- `outputs/<pdf_name>.md`

You can override the markdown path:

```bash
python pipeline.py --pdf path/to/paper.pdf --output outputs/custom.md
```

## Notes

- OCR/scanned PDFs are out of scope for v1.
- If equations are not recoverable from the PDF text, the extraction stage is instructed to mark them as `未清晰提取` instead of inventing formulas.
- The final markdown validator prints warnings for suspicious LaTeX delimiters or missing sections.
