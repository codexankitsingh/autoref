"""Outbound email validation and greeting personalization."""
from __future__ import annotations

import re
from html import unescape

_PLACEHOLDER_GREETING_RE = re.compile(r"\bHi\s+Name\s*,", re.IGNORECASE)
_BRACKET_PLACEHOLDER_RE = re.compile(r"\[[^\]]+\]")
_CURLY_PLACEHOLDER_RE = re.compile(r"\{[^}]+\}")
_ANGLE_PLACEHOLDER_RE = re.compile(
    r"<\s*(?:insert|placeholder|company name|your name|recruiter name|hiring manager|date here)[^>]*>",
    re.IGNORECASE,
)
_EMPTY_HREF_RE = re.compile(r'href\s*=\s*["\']\s*["\']', re.IGNORECASE)


def recipient_first_name(recipient_name: str | None) -> str:
    name = (recipient_name or "").strip()
    if not name or name.lower() in {"name", "recruiter", "hiring manager", "there"}:
        return ""
    return name.split()[0]


def recipient_greeting(recipient_name: str | None) -> str:
    first = recipient_first_name(recipient_name)
    return f"Hi {first}," if first else "Hi,"


def personalize_greeting(html_body: str, recipient_name: str | None) -> str:
    greeting = recipient_greeting(recipient_name)
    text = _PLACEHOLDER_GREETING_RE.sub(greeting, html_body or "")
    if re.search(r"<p>\s*Hi\s*,", text, flags=re.IGNORECASE):
        text = re.sub(
            r"(<p>\s*)Hi\s*,",
            rf"\1{greeting.replace(',', ',')}" if greeting.endswith(",") else rf"\1{greeting}",
            text,
            count=1,
            flags=re.IGNORECASE,
        )
    return text


def strip_template_tokens(text: str) -> str:
    if not text:
        return ""
    text = _BRACKET_PLACEHOLDER_RE.sub("", text)
    text = _CURLY_PLACEHOLDER_RE.sub("", text)
    text = _ANGLE_PLACEHOLDER_RE.sub("", text)
    text = re.sub(r"  +", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text.strip()


def has_placeholder_tokens(text: str) -> bool:
    if not text or not text.strip():
        return True
    if _BRACKET_PLACEHOLDER_RE.search(text):
        return True
    if _CURLY_PLACEHOLDER_RE.search(text):
        return True
    if _ANGLE_PLACEHOLDER_RE.search(text):
        return True
    if _PLACEHOLDER_GREETING_RE.search(text):
        return True

    lowered = text.lower()
    banned_fragments = (
        "insert ",
        "your name here",
        "company name",
        "recruiter name",
        "hiring manager name",
        "[date",
        "placeholder",
        "tbd",
        "xxx",
        "lorem ipsum",
        "to be determined",
        "current role from profile",
        "current company",
        "specific capability from your profile",
    )
    return any(fragment in lowered for fragment in banned_fragments)


def validate_outbound_email(subject: str, body: str) -> list[str]:
    """Return human-readable issues; empty list means OK to send."""
    issues: list[str] = []

    if not (subject or "").strip():
        issues.append("Subject is empty.")
    if not (body or "").strip():
        issues.append("Email body is empty.")

    combined = f"{subject}\n{body}"
    if has_placeholder_tokens(combined):
        issues.append("Email still contains template placeholders (e.g. [Company], Hi Name, or unfilled bracket text).")

    if _EMPTY_HREF_RE.search(body or ""):
        issues.append("Email contains an empty link (href=\"\").")

    plain = unescape(re.sub(r"<[^>]+>", " ", body or ""))
    if re.search(r"\bHi\s+there\s*,", plain, re.IGNORECASE):
        issues.append('Greeting uses "Hi there," — use a real first name or "Hi,".')

    return issues


def finalize_generated_email(subject: str, body: str, recipient_name: str | None) -> tuple[str, str]:
    """Post-process AI output before preview/send."""
    subject = strip_template_tokens(subject or "")
    body = strip_template_tokens(body or "")
    body = personalize_greeting(body, recipient_name)
    return subject.strip(), body.strip()
