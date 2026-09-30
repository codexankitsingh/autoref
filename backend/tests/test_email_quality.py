"""Tests for outbound email quality helpers."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.email_quality import (  # noqa: E402
    finalize_generated_email,
    has_placeholder_tokens,
    personalize_greeting,
    recipient_greeting,
    validate_outbound_email,
)


def test_recipient_greeting_with_name():
    assert recipient_greeting("Sarah Johnson") == "Hi Sarah,"


def test_recipient_greeting_without_name():
    assert recipient_greeting("") == "Hi,"
    assert recipient_greeting("Name") == "Hi,"


def test_personalize_greeting_replaces_hi_name():
    body = "<p>Hi Name,</p><p>Following up.</p>"
    assert personalize_greeting(body, "Raj") == "<p>Hi Raj,</p><p>Following up.</p>"


def test_has_placeholder_tokens_detects_brackets():
    assert has_placeholder_tokens("Hello [Company] team")
    assert not has_placeholder_tokens("<p>Hi Raj,</p><p>Thanks.</p>")


def test_validate_blocks_hi_there():
    issues = validate_outbound_email(
        "Referral",
        "<p>Hi there,</p><p>Quick note.</p>",
    )
    assert any("Hi there" in i for i in issues)


def test_finalize_strips_brackets_and_fixes_greeting():
    subject, body = finalize_generated_email(
        "Role at [Company]",
        "<p>Hi Name,</p><p>[Insert text]</p>",
        "Ankit",
    )
    assert "[" not in subject
    assert "Hi Ankit," in body
    assert "[" not in body
