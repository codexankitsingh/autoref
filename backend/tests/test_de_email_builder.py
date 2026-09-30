"""DE email builder tests."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.de_email_builder import (  # noqa: E402
    assemble_natural_email,
    jd_prefers_aws,
    validate_de_hallucinations,
)


def test_jd_prefers_aws():
    assert jd_prefers_aws("Airflow, AWS Redshift, Glue", "")


def test_validate_rejects_backend_hallucination():
    body = assemble_natural_email(
        greeting_line="Hi Sunil,",
        body_html="<p>ledger API 800 TPS p99 latency at Rakuten.</p>",
        resume_link="https://example.com/r",
    )
    issues = validate_de_hallucinations(body, "Sunil")
    assert any("backend/API" in i for i in issues)


def test_assemble_natural_email():
    html = assemble_natural_email(
        greeting_line="Hi Sunil,",
        body_html="<p>I am an Associate Data Engineer writing about Philips.</p>",
        resume_link="https://example.com/r",
    )
    assert "Hi Sunil," in html
    assert "Best regards" in html
    assert "resume is" in html
