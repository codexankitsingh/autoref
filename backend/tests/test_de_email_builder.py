"""DE structured email builder tests."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.de_email_builder import (  # noqa: E402
    assemble_de_email,
    jd_prefers_aws,
    sanitize_opening_paragraph,
    validate_de_email_facts,
)


def test_jd_prefers_aws():
    assert jd_prefers_aws("Airflow, AWS Redshift, Glue", "")


def test_sanitize_strips_leading_hi():
    assert sanitize_opening_paragraph("Hi Sunil, I am Ankit.").startswith("I am Ankit")


def test_validate_rejects_backend_hallucination():
    body = assemble_de_email(
        greeting_line="Hi Sunil,",
        opening_paragraph="Associate DE at Philips Senior Data Engineer role at Philips with 100M+ tx/day.",
        bullet_production="<b>Production at Rakuten:</b> Scale 100M+.",
        bullet_gcp_platform="<b>ETL:</b> BigQuery.",
        bullet_research="<b>Peer-review research:</b> 364 failures under peer review.",
        resume_link="https://example.com/r",
    )
    body_bad = body.replace("BigQuery", "ledger API 800 TPS p99 latency")
    issues = validate_de_email_facts(body_bad, "Sunil", company="Philips", role="Senior Data Engineer")
    assert any("backend/API" in i for i in issues)


def test_validate_rejects_recipient_ankit():
    issues = validate_de_email_facts("<p>Hi,</p>", "Ankit Kumar Singh")
    assert any("own first name" in i for i in issues)


def test_assemble_includes_three_bullets():
    html = assemble_de_email(
        greeting_line="Hi,",
        opening_paragraph="Writing about Senior Data Engineer at Philips — 100M+ tx/day.",
        bullet_production="<b>Production at Rakuten:</b> Points platform.",
        bullet_gcp_platform="<b>ETL and data platform:</b> BigQuery.",
        bullet_research="<b>Peer-review research:</b> 364 failures; under peer review.",
        resume_link="https://example.com/r",
    )
    assert html.count("<li>") == 3
