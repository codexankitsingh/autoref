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

# Not in Ankit's DE profile — common LLM hallucinations for "multi-cloud"
_BANNED_STACK_TERMS = re.compile(
    r"\b(redshift|snowflake|databricks|azure\s*synapse)\b",
    re.IGNORECASE,
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

_GCP_AND_REDSHIFT = re.compile(r"dataproc|bigquery|gcs", re.IGNORECASE)


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
    opening = escape((opening_paragraph or "").strip())
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


def validate_de_email_facts(body: str, recipient_name: str | None = None) -> list[str]:
    """Hard checks for known failure modes in DE outreach."""
    issues: list[str] = []
    plain = re.sub(r"<[^>]+>", " ", body or "")
    lowered = plain.lower()

    if _BANNED_STACK_TERMS.search(plain):
        issues.append(
            "Email mentions Redshift/Snowflake/Databricks — not in your profile. "
            "Use GCP (BigQuery, Dataproc, GCS) or AWS StreamLake (S3, Kafka, Iceberg) separately, never mashed together."
        )

    if _GCP_AND_REDSHIFT.search(plain) and re.search(r"\bredshift\b", plain, re.I):
        issues.append("Email mixes GCP production stack with AWS Redshift — reads incoherent. Pick one narrative.")

    for pat in _INVENTED_METRIC_PATTERNS:
        if pat.search(plain):
            issues.append('Do not invent "70% MTTR reduction" — profile cites ~25–30 min triage down to minutes on reruns.')

    if _SINGLE_PIPELINE_OWNERSHIP.search(plain):
        issues.append(
            'Avoid "I own a [N] GB/day pipeline" — you own production systems on the loyalty platform (100M+ tx/day) plus ELT; say platform/pipeline ownership, not one pipe.'
        )

    if re.search(r"\bhi\s+ankit\s*,", plain, re.IGNORECASE):
        first = (recipient_name or "").strip().split()[0].lower() if recipient_name else ""
        if first != "ankit":
            issues.append('Greeting must be to the recruiter/hiring manager, not "Hi Ankit," (that addresses yourself).')

    research_markers = ("peer review", "peer-review", "under review")
    if not any(m in lowered for m in research_markers):
        issues.append(
            "Research bullet must state the Auto-RCA work is under peer review (not published yet)."
        )
    if "364" not in plain and "364" not in (body or ""):
        issues.append("Research section should reference 364 production Airflow failures (from your profile).")

    compact = lowered.replace(",", "").replace(" ", "")
    if "100m" not in compact and "100million" not in compact:
        issues.append(
            "Mention loyalty/points platform scale (100M+ transactions/day), not only GB/day ingestion."
        )

    return issues
