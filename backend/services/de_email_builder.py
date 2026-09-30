"""Structured Data Engineering outreach email assembly and factual validation."""
from __future__ import annotations

import re
from html import escape

SIGNOFF_HTML = (
    '<p>Best regards,<br>\n'
    "Ankit Kumar Singh<br>\n"
    "+91 9451184789<br>\n"
    '<a href="https://www.linkedin.com/in/ankit-kumar-singh-37450422a/" '
    'style="color: #2563eb; text-decoration: none;">LinkedIn</a> | '
    '<a href="https://github.com/codexankitsingh" style="color: #2563eb; text-decoration: none;">GitHub</a></p>'
)

_SENDER_FIRST_NAMES = frozenset({"ankit"})

_BACKEND_HALLUCINATION = re.compile(
    r"\b(ledger\s+api|800\+?\s*tps|p99\s+latency|scalable\s+apis?)\b",
    re.IGNORECASE,
)

_VAGUE_MULTI_CLOUD = re.compile(
    r"\bmulti-?cloud\s+environments?\b",
    re.IGNORECASE,
)

_FALSE_PROD_REDSHIFT = re.compile(
    r"(redshift).{0,40}(rakuten|production|owned|built|ingestion)|"
    r"(rakuten|production|owned|built).{0,40}(redshift)",
    re.IGNORECASE | re.DOTALL,
)

_INVENTED_METRIC_PATTERNS = (
    re.compile(r"\b70\s*%\s*(?:mttr|reduction|faster)", re.IGNORECASE),
    re.compile(r"mttr\s*by\s*70", re.IGNORECASE),
    re.compile(r"reduced\s+mttr\s+by\s*70", re.IGNORECASE),
)

_SINGLE_PIPELINE_OWNERSHIP = re.compile(
    r"\bI\s+own\s+(?:a\s+)?(?:an?\s+)?\d",
    re.IGNORECASE,
)

_LEADING_GREETING_RE = re.compile(
    r"^(?:hi|hello|dear)\s+[a-z]+,?\s*",
    re.IGNORECASE,
)


def jd_prefers_aws(skills: str, jd_text: str = "") -> bool:
    blob = f"{skills} {jd_text}".lower()
    return any(
        token in blob
        for token in (
            "aws",
            "redshift",
            "glue",
            " emr",
            "kinesis",
            "amazon s3",
            " s3,",
        )
    )


def sanitize_opening_paragraph(text: str) -> str:
    """Opening must not duplicate the HTML greeting line."""
    t = (text or "").strip()
    t = _LEADING_GREETING_RE.sub("", t).strip()
    return t


def assemble_de_email(
    *,
    greeting_line: str,
    opening_paragraph: str,
    bullet_production: str,
    bullet_gcp_platform: str,
    bullet_research: str,
    resume_link: str,
    job_context_html: str = "",
) -> str:
    """Build HTML from validated sections — fixed narrative order."""
    opening = escape(sanitize_opening_paragraph(opening_paragraph))
    parts = [
        f"<p>{greeting_line}</p>",
        f"<p>{opening}</p>",
        "<p>Relevant background:</p>",
        '<ul style="margin-top: 0; padding-left: 20px;">',
        _wrap_li(bullet_production),
        _wrap_li(bullet_gcp_platform),
        _wrap_li(bullet_research),
        "</ul>",
    ]
    if job_context_html.strip():
        parts.append(job_context_html.strip())
    parts.append(
        f'<p>My resume is <a href="{resume_link}">here</a>. '
        "I'd welcome a brief conversation about fit for the role — "
        "happy to align on timing for a call or whatever the next step is on your side.</p>"
    )
    parts.append(SIGNOFF_HTML)
    return "\n\n".join(parts)


def _wrap_li(fragment: str) -> str:
    text = (fragment or "").strip()
    if not text:
        return "<li></li>"
    if text.lower().startswith("<li"):
        return text if text.lower().endswith("</li>") else f"{text}</li>"
    return f"<li>{text}</li>"


def validate_de_email_facts(
    body: str,
    recipient_name: str | None = None,
    *,
    company: str | None = None,
    role: str | None = None,
) -> list[str]:
    """Hard checks for known failure modes in DE outreach."""
    issues: list[str] = []
    plain = re.sub(r"<[^>]+>", " ", body or "")
    lowered = plain.lower()

    if re.search(r"\bhi\s+ankit\s*,", plain, re.IGNORECASE):
        issues.append(
            'Greeting says "Hi Ankit" — that is you, not the recruiter. '
            "Enter the hiring manager's first name in Recipient Name (or leave blank for Hi,)."
        )

    first = (recipient_name or "").strip().split()[0].lower() if recipient_name else ""
    if first in _SENDER_FIRST_NAMES:
        issues.append(
            "Recipient Name is your own first name — use the recruiter or hiring manager's name."
        )

    if _BACKEND_HALLUCINATION.search(plain):
        issues.append(
            "Remove backend/API claims (ledger API, 800 TPS, p99) — not on your Data Engineering profile."
        )

    if _VAGUE_MULTI_CLOUD.search(plain):
        issues.append('Replace vague "multi-cloud environments" with specific GCP production + StreamLake AWS project.')

    if _FALSE_PROD_REDSHIFT.search(plain):
        issues.append(
            "Do not claim production Redshift at Rakuten. Map GCP/AWS skills to the JD honestly (StreamLake uses S3/Kafka/Iceberg)."
        )

    for pat in _INVENTED_METRIC_PATTERNS:
        if pat.search(plain):
            issues.append('Do not invent "70% MTTR reduction" — use ~25–30 min triage down to minutes.')

    if _SINGLE_PIPELINE_OWNERSHIP.search(plain):
        issues.append(
            'Avoid "I own a [N] GB/day pipeline" — you own loyalty platform systems (100M+ tx/day) plus ELT.'
        )

    co = (company or "").strip().lower()
    if co and co not in ("the company", "company") and co not in lowered:
        issues.append(f"Opening should name the company ({company}).")

    if role and role.strip().lower() not in ("the position", "position"):
        role_l = role.strip().lower()
        if role_l[:12] not in lowered and "data engineer" not in lowered:
            issues.append(f"Opening should reference the job title ({role}).")

    research_markers = ("peer review", "peer-review", "under review")
    if not any(m in lowered for m in research_markers):
        issues.append("Research bullet must state the Auto-RCA work is under peer review.")

    if "364" not in plain:
        issues.append("Research section should reference 364 production Airflow failures.")

    compact = lowered.replace(",", "").replace(" ", "")
    if "100m" not in compact and "100million" not in compact:
        issues.append("Mention loyalty/points platform scale (100M+ transactions/day).")

    return issues
