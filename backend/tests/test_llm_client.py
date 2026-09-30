"""LLM client helpers."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.llm_model_ids import normalize_openai_compatible_model  # noqa: E402


def test_groq_model_gets_openai_prefix():
    assert (
        normalize_openai_compatible_model(
            "gpt-oss-120b",
            "https://api.groq.com/openai/v1",
        )
        == "openai/gpt-oss-120b"
    )


def test_groq_model_with_prefix_unchanged():
    assert (
        normalize_openai_compatible_model(
            "openai/gpt-oss-120b",
            "https://api.groq.com/openai/v1",
        )
        == "openai/gpt-oss-120b"
    )


def test_openai_com_api_unchanged():
    assert (
        normalize_openai_compatible_model(
            "gpt-4o-mini",
            "https://api.openai.com/v1",
        )
        == "gpt-4o-mini"
    )
