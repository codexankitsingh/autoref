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
_UNICODE_DASH_RE = re.compile(r"[\u2010-\u2015\u2212]")

# Template section headers the model sometimes copies verbatim from prompts
_TEMPLATE_BULLET_LABELS = (
    "Production Scale & Pipeline Ownership",
    "ELT / Orchestration & Cloud Migration",
    "Streaming, Lakehouse, or Reliability Tooling",
    "API Design / System Architecture",
    "Performance & Scalability",
    "Problem Solving & CS Fundamentals",
)

_AI_CLICHE_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"<p>\s*Quick context on why I'?d be a strong fit:\s*</p>",
            re.IGNORECASE,
        ),
        "<p>A few things that line up with the role:</p>",
    ),
    (
        re.compile(r"I'?m reaching out regarding the", re.IGNORECASE),
        "I'm writing about the",
    ),
    (
        re.compile(r"directly aligns with your focus on", re.IGNORECASE),
        "lines up with what you're building around",
    ),
    (
        re.compile(
            r"I would be incredibly grateful if you'?d be open to referring me for a relevant position, "
            r"or connecting me with the appropriate hiring team\.?\s*",
            re.IGNORECASE,
        ),
        "I'd welcome a brief conversation about fit for the role — happy to align on timing for a call or the next step on your side. ",
    ),
    (
        re.compile(
            r"If you'?re open to it, I'?d appreciate a referral or an intro to the hiring manager[^<]*",
            re.IGNORECASE,
        ),
        "I'd welcome a brief conversation about fit for the role — happy to align on timing for a call or the next step on your side. ",
    ),
    (
        re.compile(
            r"I would welcome the opportunity to hop on a brief call to discuss further\.?\s*",
            re.IGNORECASE,
        ),
        "Happy to find time for a quick call if that's useful. ",
    ),
    (
        re.compile(r"\s*Looking forward to hearing from you!?\s*", re.IGNORECASE),
        " ",
    ),
)

_COMPANY_ACRONYMS = frozenset({"IBM", "SAP", "AWS", "GCP", "TCS", "HCL", "LTIM", "GE", "3M", "HP"})


def recipient_first_name(recipient_name: str | None) -> str:
    name = (recipient_name or "").strip()
    if not name or name.lower() in {"name", "recruiter", "hiring manager", "there"}:
        return ""
    return name.split()[0]


def recipient_greeting(recipient_name: str | None) -> str:
    first = recipient_first_name(recipient_name)
    return f"Hi {first}," if first else "Hi,"


def normalize_company_display(company: str | None) -> str:
    """Proper-noun style company name when JD/parser returns lowercase."""
    raw = (company or "").strip()
    if not raw:
        return raw
    if raw != raw.lower():
        return raw
    words = raw.split()
    out: list[str] = []
    for w in words:
        upper = w.upper()
        if upper in _COMPANY_ACRONYMS:
            out.append(upper)
        elif len(w) <= 3 and w.isalpha():
            out.append(w.upper())
        else:
            out.append(w.capitalize())
    return " ".join(out)


def clean_job_title(role: str | None) -> str:
    """Fix common JD parse glitches (truncated location suffixes)."""
    title = (role or "").strip()
    if not title:
        return title
    # e.g. "Senior Data Engineer - I" from truncated "India"
    if re.search(r"\s-\sI$", title) and "india" not in title.lower():
        title = re.sub(r"\s-\sI$", " - India", title)
    title = re.sub(r"\s+", " ", title)
    return title.strip()


def normalize_jd_fields(parsed: dict) -> dict:
    out = dict(parsed)
    if out.get("company"):
        out["company"] = normalize_company_display(out["company"])
    if out.get("role"):
        out["role"] = clean_job_title(out["role"])
    return out


def _normalize_typography(text: str) -> str:
    if not text:
        return text
    text = _UNICODE_DASH_RE.sub("-", text)
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    return text


def _strip_template_bullet_labels(html: str) -> str:
    for label in _TEMPLATE_BULLET_LABELS:
        html = re.sub(
            rf"<b>\s*{re.escape(label)}\s*:\s*</b>\s*",
            "",
            html,
            flags=re.IGNORECASE,
        )
    return html


def _fix_sender_title_for_role(html: str, target_role: str | None = None) -> str:
    replacements = (
        (r"\ba Backend Engineer\b", "an Associate Data Engineer"),
        (r"\bBackend Engineer\b", "Associate Data Engineer"),
        (r"\bSDE Intern\b", "Associate Data Engineer"),
        (r"\bSoftware Engineer Intern\b", "Associate Data Engineer"),
    )
    for pattern, repl in replacements:
        html = re.sub(pattern, repl, html, flags=re.IGNORECASE)
    return html


def _apply_company_casing(html: str, company: str | None) -> str:
    canonical = normalize_company_display(company)
    if not canonical:
        return html
    lowered = canonical.lower()
    html = re.sub(rf"\bat {re.escape(lowered)}\b", f"at {canonical}", html, flags=re.IGNORECASE)
    html = re.sub(rf"\b{re.escape(lowered)}\b", canonical, html, flags=re.IGNORECASE)
    return html


def polish_human_voice(
    html: str,
    *,
    target_role: str | None = None,
    company: str | None = None,
) -> str:
    text = _normalize_typography(html or "")
    text = _strip_template_bullet_labels(text)
    text = _fix_sender_title_for_role(text, target_role)
    text = _apply_company_casing(text, company)
    for pattern, repl in _AI_CLICHE_REPLACEMENTS:
        text = pattern.sub(repl, text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"  +", " ", text)
    return text.strip()


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


def has_ai_cliche_markers(text: str) -> bool:
    lowered = (text or "").lower()
    markers = (
        "quick context on why i'd be a strong fit",
        "incredibly grateful",
        "hop on a brief call",
        "looking forward to hearing from you!",
        "production scale & pipeline ownership",
        "streaming, lakehouse, or reliability tooling",
        "i'm reaching out regarding the",
        "directly aligns with your focus on",
    )
    return any(m in lowered for m in markers)


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

    if has_ai_cliche_markers(combined):
        issues.append(
            "Email still reads like a generic AI template (e.g. 'Quick context on why I'd be a strong fit'). "
            "Regenerate or edit for a natural tone."
        )

    return issues


def finalize_generated_email(
    subject: str,
    body: str,
    recipient_name: str | None,
    *,
    target_role: str | None = None,
    company: str | None = None,
) -> tuple[str, str]:
    """Post-process AI output before preview/send."""
    subject = strip_template_tokens(subject or "")
    body = strip_template_tokens(body or "")
    body = personalize_greeting(body, recipient_name)
    subject = _normalize_typography(subject)
    body = polish_human_voice(body, target_role=target_role, company=company)
    if company:
        subject = _apply_company_casing(subject, company)
    return subject.strip(), body.strip()
