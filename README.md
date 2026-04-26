# DailyPaper

Local pipeline for converting a research paper PDF into a Xiaohongshu-style Chinese markdown note.

## Features

- Extracts full text from local text-based PDFs.
- Detects likely equation snippets before LLM extraction.
- Uses two LLM stages:
  - structured extraction JSON
  - Xiaohongshu-style markdown rewrite
- Preserves important formulas as markdown LaTeX.
- Inserts selected paper pages as images in markdown.
- Exports the final markdown note to PDF with a pure-Python renderer.
- Supports OpenAI, OpenAI-compatible gateways, LiteLLM, and OpenRouter through one `call_llm(prompt, input)` interface.

## Install

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt
```

### Windows CMD

```cmd
python -m venv .venv
.\.venv\Scripts\activate.bat
python -m pip install -U pip
pip install -r requirements.txt
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
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

pipeline:
  save_intermediate_json: true
  max_input_chars: 60000
  output_dir: outputs
  insert_key_pages: true
  key_pages_max: 5
  render_page_zoom: 2.0
  export_pdf: false

pdf:
  font_path: null
  font_name: null
```

Set the relevant API key.

### Windows PowerShell

```powershell
$env:OPENAI_API_KEY="your-key"
```

### Windows CMD

```cmd
set OPENAI_API_KEY=your-key
```

### macOS / Linux

```bash
export OPENAI_API_KEY="your-key"
```

For OpenAI-compatible third-party gateways such as aihubmix, keep `provider: openai` and set a custom base URL:

```yaml
provider: openai
model: gpt-4o-mini

api:
  openai_api_key_env: AIHUBMIX_API_KEY
  openai_base_url: https://api.aihubmix.com/v1
```

Set the gateway API key:

```powershell
# Windows PowerShell
$env:AIHUBMIX_API_KEY="your-key"
```

```cmd
:: Windows CMD
set AIHUBMIX_API_KEY=your-key
```

```bash
# macOS / Linux
export AIHUBMIX_API_KEY="your-key"
```

The API key environment variable name is configurable through `openai_api_key_env`.

For OpenRouter:

```yaml
provider: openrouter
model: openai/gpt-4o-mini

api:
  openrouter_api_key_env: OPENROUTER_API_KEY
  openrouter_base_url: https://openrouter.ai/api/v1
```

For LiteLLM:

```yaml
provider: litellm
model: gpt-4o-mini
```

## Run

### Windows PowerShell

```powershell
python pipeline.py --pdf .\papers\sample.pdf --config config.yaml
```

### Windows CMD

```cmd
python pipeline.py --pdf .\papers\sample.pdf --config config.yaml
```

### macOS / Linux

```bash
python pipeline.py --pdf ./papers/sample.pdf --config config.yaml
```

Outputs are saved to:

- `outputs/<pdf_name>.json`
- `outputs/<pdf_name>.md`
- `outputs/assets/<pdf_name>/page_001.png` and other selected page images

## Key Page Images

By default, the pipeline automatically inserts up to 5 selected paper pages into the markdown:

- title/authors page
- likely framework/model/method pages
- likely result/metric/table pages

Manually choose pages:

```powershell
python pipeline.py --pdf .\papers\sample.pdf --key-pages 1,3,7
```

Disable page images:

```powershell
python pipeline.py --pdf .\papers\sample.pdf --no-key-pages
```

## PDF Export

Generate markdown and PDF together:

```powershell
python pipeline.py --pdf .\papers\sample.pdf --export-pdf
```

Set a custom PDF output path:

```powershell
python pipeline.py --pdf .\papers\sample.pdf --export-pdf --pdf-output .\outputs\custom.pdf
```

You can also override the markdown path:

```powershell
# Windows PowerShell
python pipeline.py --pdf .\papers\sample.pdf --output .\outputs\custom.md
```

```cmd
:: Windows CMD
python pipeline.py --pdf .\papers\sample.pdf --output .\outputs\custom.md
```

```bash
# macOS / Linux
python pipeline.py --pdf ./papers/sample.pdf --output ./outputs/custom.md
```

## Notes

- OCR/scanned PDFs are out of scope for v1.
- Inserted paper pages are full-page screenshots, not cropped individual figures.
- PDF export keeps LaTeX formulas as readable text; it does not render MathJax in v1.
- If equations are not recoverable from the PDF text, the extraction stage is instructed to mark them as `未清晰提取` instead of inventing formulas.
- The final markdown validator prints warnings for suspicious LaTeX delimiters or missing sections.
