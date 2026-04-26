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

```powershell
# Windows PowerShell
$env:OPENROUTER_API_KEY="your-key"
```

```cmd
:: Windows CMD
set OPENROUTER_API_KEY=your-key
```

```bash
# macOS / Linux
export OPENROUTER_API_KEY="your-key"
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

You can override the markdown path:

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
- If equations are not recoverable from the PDF text, the extraction stage is instructed to mark them as `未清晰提取` instead of inventing formulas.
- The final markdown validator prints warnings for suspicious LaTeX delimiters or missing sections.
