"""DE outreach email assembly and light hallucination checks."""
from __future__ import annotations

import re

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
    r"\bmulti-?cloud\s+(?:etl|environments?)\b",
    re.IGNORECASE,
)

_FALSE_PROD_REDSHIFT = re.compile(
    r"(redshift).{0,40}(rakuten|production|owned|built|ingestion)|"
    r"(rakuten|production|owned|built).{0,40}(redshift)",
    re.IGNORECASE | re.DOTALL,
)

_TELEGRAPH_BULLET = re.compile(
    r"<li>\s*[A-Z][a-z]+\s+[a-z]+\s+[a-z]+\.\s*[A-Z]",
)


def jd_prefers_aws(skills: str, jd_text: str = "") -> bool:
    blob = f"{skills} {jd_text}".lower()
    return any(
        token in blob
        for token in ("aws", "redshift", "glue", " emr", "kinesis", "amazon s3", " s3,")
    )


def assemble_natural_email(
    *,
    greeting_line: str,
    body_html: str,
    resume_link: str,
    job_context_html: str = "",
) -> str:
    """Greeting + LLM body + optional job link block + resume CTA + signoff."""
    middle = (body_html or "").strip()
    # Strip duplicate greeting if model added one
    middle = re.sub(r"^<p>\s*(?:Hi|Hello|Dear)\s+[^<]*</p>\s*", "", middle, flags=re.I)

    parts = [f"<p>{greeting_line}</p>", middle]
    if job_context_html.strip():
        parts.append(job_context_html.strip())
    if resume_link not in middle:
        parts.append(
            f'<p>My resume is <a href="{resume_link}">here</a>. '
            "I'd welcome a brief conversation about fit for the role — "
            "happy to align on timing for a call or whatever the next step is on your side.</p>"
        )
    parts.append(SIGNOFF_HTML)
    return "\n\n".join(parts)


def validate_de_hallucinations(
    body: str,
    recipient_name: str | None = None,
) -> list[str]:
    """Only block clear factual / tone failures — not narrative style."""
    issues: list[str] = []
    plain = re.sub(r"<[^>]+>", " ", body or "")

    if re.search(r"\bhi\s+ankit\s*,", plain, re.IGNORECASE):
        issues.append('Do not greet yourself as "Hi Ankit" — use the recruiter\'s name.')

    first = (recipient_name or "").strip().split()[0].lower() if recipient_name else ""
    if first in _SENDER_FIRST_NAMES:
        issues.append("Recipient Name should be the hiring contact, not your own first name.")

    if _BACKEND_HALLUCINATION.search(plain):
        issues.append("Remove invented backend/API metrics (not on your DE profile).")

    if _VAGUE_MULTI_CLOUD.search(plain):
        issues.append('Avoid vague "multi-cloud ETL" — name GCP production and StreamLake/AWS project specifically.')

    if _FALSE_PROD_REDSHIFT.search(plain):
        issues.append("Do not claim you run Redshift in Rakuten production.")

    if _TELEGRAPH_BULLET.search(body or ""):
        issues.append("Write bullet points as full sentences, not telegram-style fragments.")

    return issues
