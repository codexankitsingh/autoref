"""Unified LLM calls: Google Gemini with OpenAI-compatible fallback."""
from __future__ import annotations

import httpx
from google import genai

from config import get_settings

GEMINI_DENIED_MESSAGE = (
    "Google Gemini returned 403 PERMISSION_DENIED (your Google Cloud project is blocked or denied, "
    "not because the key starts with AQ.). AQ. keys are the new normal Auth keys from AI Studio — "
    "use them as GEMINI_API_KEY. Fix: create a new GCP project in AI Studio, enable billing if required, "
    "generate a fresh AQ. key, or contact Google AI support. Alternatively set OPENAI_API_KEY for fallback."
)


def gemini_key_kind(api_key: str) -> str:
    k = (api_key or "").strip()
    if k.startswith("AQ."):
        return "auth (AQ.)"
    if k.startswith("AIza"):
        return "legacy (AIza)"
    return "unknown"


class LLMConfigurationError(Exception):
    pass


class LLMAccessDeniedError(Exception):
    pass


def _is_gemini_denied(exc: Exception) -> bool:
    msg = str(exc)
    return "403" in msg and ("PERMISSION_DENIED" in msg or "denied access" in msg.lower())


def _is_rate_limited(exc: Exception) -> bool:
    msg = str(exc)
    return "429" in msg or "RESOURCE_EXHAUSTED" in msg


def _resolve_provider(model_name: str) -> str:
    settings = get_settings()
    if model_name.startswith("openai:") or model_name.startswith("gpt-"):
        return "openai"
    if settings.ai_provider == "openai":
        return "openai"
    if settings.ai_provider == "gemini":
        return "gemini"
    # auto
    if not (settings.gemini_api_key or "").strip() and (settings.openai_api_key or "").strip():
        return "openai"
    return "gemini"


def _openai_model_name(model_name: str) -> str:
    settings = get_settings()
    if model_name.startswith("openai:"):
        return model_name.split(":", 1)[1]
    if model_name.startswith("gpt-"):
        return model_name
    return settings.openai_model


def _call_openai(prompt: str, model_name: str) -> str:
    settings = get_settings()
    api_key = (settings.openai_api_key or "").strip()
    if not api_key:
        raise LLMConfigurationError(
            "OPENAI_API_KEY is not set. Add it to backend/.env to use OpenAI while Gemini is unavailable."
        )

    base = (settings.openai_base_url or "https://api.openai.com/v1").rstrip("/")
    model = _openai_model_name(model_name)
    url = f"{base}/chat/completions"

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.4,
    }

    with httpx.Client(timeout=120.0) as client:
        resp = client.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

    if resp.status_code == 401:
        raise LLMAccessDeniedError("OpenAI API key is invalid (401). Check OPENAI_API_KEY in .env.")
    if resp.status_code == 403:
        raise LLMAccessDeniedError("OpenAI API access denied (403). Check billing and model access.")
    if resp.status_code >= 400:
        raise LLMAccessDeniedError(f"OpenAI request failed ({resp.status_code}): {resp.text[:300]}")

    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as e:
        raise LLMAccessDeniedError(f"Unexpected OpenAI response shape: {e}") from e


_gemini_client: genai.Client | None = None
_cached_gemini_key: str | None = None


def _get_gemini_client() -> genai.Client:
    global _gemini_client, _cached_gemini_key
    settings = get_settings()
    key = (settings.gemini_api_key or "").strip()
    if not key or key == "your-gemini-api-key-here":
        raise LLMConfigurationError(
            "GEMINI_API_KEY is missing. Set it in backend/.env or use OPENAI_API_KEY with AI_PROVIDER=openai."
        )
    if _gemini_client is None or _cached_gemini_key != key:
        _gemini_client = genai.Client(api_key=key)
        _cached_gemini_key = key
    return _gemini_client


def _call_gemini_rest(prompt: str, model_name: str, api_key: str) -> str:
    """
    Native Gemini REST (recommended for AQ. Auth keys).
    See: https://ai.google.dev/gemini-api/docs/api-key
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(
            url,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            },
            json=payload,
        )
    if resp.status_code >= 400:
        raise LLMAccessDeniedError(
            f"Gemini REST error ({resp.status_code}): {resp.text[:400]}"
        )
    data = resp.json()
    try:
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts).strip()
    except (KeyError, IndexError, TypeError) as e:
        raise LLMAccessDeniedError(f"Unexpected Gemini REST response: {e}") from e


def _call_gemini(prompt: str, model_name: str) -> str:
    settings = get_settings()
    api_key = (settings.gemini_api_key or "").strip()
    try:
        client = _get_gemini_client()
        response = client.models.generate_content(model=model_name, contents=prompt)
        return response.text.strip()
    except Exception as sdk_error:
        # AQ. Auth keys: retry via native REST + x-goog-api-key (some SDK versions mis-route)
        if api_key.startswith("AQ."):
            print(f"Gemini SDK failed ({sdk_error}); retrying native REST for AQ. key...")
            return _call_gemini_rest(prompt, model_name, api_key)
        raise


def generate_text(prompt: str, model_name: str = "gemini-2.5-flash-lite", max_retries: int = 3) -> str:
    """
    Generate text using Gemini or OpenAI-compatible API.
    On Gemini 403 project denial, automatically tries OpenAI when OPENAI_API_KEY is set.
    """
    import time

    settings = get_settings()
    provider = _resolve_provider(model_name)
    gemini_model = model_name
    if model_name.startswith("openai:") or model_name.startswith("gpt-"):
        gemini_model = settings.openai_model  # unused for openai path

    if provider == "openai":
        return _call_openai(prompt, model_name)

    last_denied: Exception | None = None
    for attempt in range(max_retries):
        try:
            return _call_gemini(prompt, gemini_model)
        except Exception as e:
            if _is_gemini_denied(e):
                last_denied = e
                if (settings.openai_api_key or "").strip():
                    print("Gemini 403 — falling back to OpenAI-compatible API.")
                    return _call_openai(prompt, model_name)
                raise LLMAccessDeniedError(GEMINI_DENIED_MESSAGE) from e
            if _is_rate_limited(e) and attempt < max_retries - 1:
                wait_time = 8 * (2 ** attempt)
                print(f"Rate limited (attempt {attempt + 1}/{max_retries}). Waiting {wait_time}s...")
                time.sleep(wait_time)
                continue
            raise

    if last_denied:
        raise LLMAccessDeniedError(GEMINI_DENIED_MESSAGE) from last_denied
    raise RuntimeError("Max retries exceeded for LLM API")


def check_ai_connectivity() -> dict:
    """Lightweight probe for health endpoint / settings diagnostics."""
    settings = get_settings()
    key = (settings.gemini_api_key or "").strip()
    result = {
        "gemini_configured": bool(key),
        "gemini_key_kind": gemini_key_kind(key) if key else "none",
        "openai_configured": bool((settings.openai_api_key or "").strip()),
        "ai_provider": settings.ai_provider,
        "gemini_ok": False,
        "openai_ok": False,
        "message": "",
    }
    try:
        generate_text("Reply with exactly: ok", model_name="gemini-2.5-flash-lite", max_retries=1)
        result["gemini_ok"] = True
        result["message"] = "Gemini is reachable."
        return result
    except LLMAccessDeniedError as e:
        result["message"] = str(e)
    except Exception as e:
        result["message"] = f"Gemini error: {e}"

    if result["openai_configured"]:
        try:
            _call_openai("Reply with exactly: ok", f"openai:{settings.openai_model}")
            result["openai_ok"] = True
            result["message"] = "Gemini unavailable; OpenAI fallback is working."
        except Exception as e:
            result["message"] = f"Gemini failed and OpenAI fallback failed: {e}"
    return result
