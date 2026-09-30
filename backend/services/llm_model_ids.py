"""OpenAI-compatible API model ID normalization (Groq vendor prefixes)."""


def normalize_openai_compatible_model(model: str, base_url: str) -> str:
    """
    Groq expects vendor-prefixed IDs like openai/gpt-oss-120b.
    UI values like openai:gpt-oss-120b become gpt-oss-120b after stripping — fix here.
    """
    m = (model or "").strip()
    if not m:
        return m
    if "groq.com" not in (base_url or "").lower():
        return m
    if "/" in m:
        return m
    if m.startswith("gpt-oss-"):
        return f"openai/{m}"
    return m
