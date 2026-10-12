"""Minimal client for any OpenAI-compatible chat endpoint.

Works unchanged with Ollama (default), Groq, OpenRouter, Gemini's
OpenAI-compat endpoint, etc. Configure with LLM_BASE_URL / LLM_MODEL / LLM_API_KEY.
"""

import os

import httpx


class LLMError(RuntimeError):
    pass


def chat(messages: list[dict[str, str]], client: httpx.Client | None = None) -> str:
    base_url = os.environ.get("LLM_BASE_URL", "http://host.docker.internal:11434/v1").rstrip("/")
    model = os.environ.get("LLM_MODEL", "qwen2.5-coder:7b")
    api_key = os.environ.get("LLM_API_KEY")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    owns_client = client is None
    client = client or httpx.Client(timeout=120)
    try:
        resp = client.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json={"model": model, "messages": messages, "temperature": 0.1},
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except httpx.HTTPError as e:
        raise LLMError(f"LLM request to {base_url} failed: {e}") from e
    except (KeyError, IndexError, ValueError) as e:
        raise LLMError(f"unexpected LLM response shape: {e}") from e
    finally:
        if owns_client:
            client.close()
