"""DE structured email builder tests."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.de_email_builder import (  # noqa: E402
    assemble_de_email,
    validate_de_email_facts,
)


def test_validate_rejects_redshift_mashup():
    body = assemble_de_email(
        greeting_line="Hi Sunil,",
        opening_paragraph="Test opening with 100M+ transactions/day at Rakuten.",
        bullet_production="<b>Production at Rakuten:</b> Scale.",
        bullet_gcp_platform="<b>GCP:</b> Dataproc and Redshift together.",
        bullet_research="<b>Peer-review research:</b> 364 failures under peer review.",
        resume_link="https://example.com/r",
    )
    issues = validate_de_email_facts(body, "Sunil")
    assert any("Redshift" in i for i in issues)


def test_validate_rejects_hi_ankit_self_greeting():
    body = "<p>Hi Ankit,</p><p>100M+ tx/day. Peer review under review 364.</p>"
    issues = validate_de_email_facts(body, "Sunil")
    assert any("Hi Ankit" in i for i in issues)


def test_assemble_includes_three_bullets():
    html = assemble_de_email(
        greeting_line="Hi,",
        opening_paragraph="Associate DE — 100M+ tx/day.",
        bullet_production="<b>Production at Rakuten:</b> Points platform.",
        bullet_gcp_platform="<b>GCP data platform:</b> BigQuery.",
        bullet_research="<b>Peer-review research:</b> 364 failures; under peer review.",
        resume_link="https://example.com/r",
    )
    assert html.count("<li>") == 3
    assert "Peer-review research" in html
