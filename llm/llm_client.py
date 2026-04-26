from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml


class LLMConfigError(RuntimeError):
    """Raised when LLM configuration is missing or invalid."""


def load_config(config_path: str = "config.yaml") -> dict[str, Any]:
    path = Path(config_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Config file does not exist: {path}")

    with path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}

    if not isinstance(config, dict):
        raise LLMConfigError("Config must be a YAML mapping.")

    provider = config.get("provider")
    model = config.get("model")
    if not provider:
        raise LLMConfigError("Config is missing required field: provider")
    if not model:
        raise LLMConfigError("Config is missing required field: model")

    config.setdefault("temperature", 0.2)
    config.setdefault("max_tokens", 4096)
    config.setdefault("api", {})
    config.setdefault("pipeline", {})
    return config


def call_llm(prompt: str, input: str | dict, config: dict[str, Any] | None = None) -> str:
    """Call the configured LLM provider with a unified prompt/input interface."""
    if config is None:
        config = load_config()

    provider = str(config.get("provider", "")).lower()
    if provider == "openai":
        return _call_openai(prompt, input, config)
    if provider == "litellm":
        return _call_litellm(prompt, input, config)
    if provider == "openrouter":
        return _call_openrouter(prompt, input, config)

    raise LLMConfigError(
        f"Unsupported provider '{provider}'. Expected one of: openai, litellm, openrouter."
    )


def _call_openai(prompt: str, input_payload: str | dict, config: dict[str, Any]) -> str:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise LLMConfigError(
            "Missing dependency 'openai'. Install dependencies with: pip install -r requirements.txt"
        ) from exc

    api_key = _read_env_key(config, "openai_api_key_env", "OPENAI_API_KEY")
    base_url = _read_optional_api_value(config, "openai_base_url")
    client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
    return _openai_chat_completion(client, prompt, input_payload, config)


def _call_openrouter(prompt: str, input_payload: str | dict, config: dict[str, Any]) -> str:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise LLMConfigError(
            "Missing dependency 'openai'. Install dependencies with: pip install -r requirements.txt"
        ) from exc

    api_config = config.get("api", {})
    api_key = _read_env_key(config, "openrouter_api_key_env", "OPENROUTER_API_KEY")
    base_url = api_config.get("openrouter_base_url", "https://openrouter.ai/api/v1")
    client = OpenAI(api_key=api_key, base_url=base_url)
    return _openai_chat_completion(client, prompt, input_payload, config)


def _call_litellm(prompt: str, input_payload: str | dict, config: dict[str, Any]) -> str:
    try:
        from litellm import completion
    except ImportError as exc:
        raise LLMConfigError(
            "Missing dependency 'litellm'. Install dependencies with: pip install -r requirements.txt"
        ) from exc

    response = completion(
        model=config["model"],
        messages=_messages(prompt, input_payload),
        temperature=float(config.get("temperature", 0.2)),
        max_tokens=int(config.get("max_tokens", 4096)),
    )
    return response.choices[0].message.content or ""


def _openai_chat_completion(client: Any, prompt: str, input_payload: str | dict, config: dict[str, Any]) -> str:
    response = client.chat.completions.create(
        model=config["model"],
        messages=_messages(prompt, input_payload),
        temperature=float(config.get("temperature", 0.2)),
        max_tokens=int(config.get("max_tokens", 4096)),
    )
    return response.choices[0].message.content or ""


def _messages(prompt: str, input_payload: str | dict) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": prompt},
        {"role": "user", "content": _serialize_input(input_payload)},
    ]


def _serialize_input(input_payload: str | dict) -> str:
    if isinstance(input_payload, str):
        return input_payload
    return json.dumps(input_payload, ensure_ascii=False, indent=2)


def _read_env_key(config: dict[str, Any], env_config_name: str, default_env_name: str) -> str:
    api_config = config.get("api", {})
    env_name = api_config.get(env_config_name, default_env_name)
    api_key = os.getenv(env_name)
    if not api_key:
        raise LLMConfigError(f"Missing API key. Set environment variable: {env_name}")
    return api_key


def _read_optional_api_value(config: dict[str, Any], name: str) -> str | None:
    value = config.get("api", {}).get(name)
    if value is None:
        return None
    value = str(value).strip()
    return value or None
