"""Default resume/profile text when the user has not saved profile_text yet."""
from pathlib import Path

from services.outreach_constants import TARGET_ROLE

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

DE_PROFILE_FILE = "default_profile_data_engineering.txt"

ROLE_PROFILE_FILES: dict[str, str] = {
    TARGET_ROLE: DE_PROFILE_FILE,
}


def resolve_profile_text(profile_text: str | None, target_role: str | None = None) -> str:
    """Prefer saved profile; otherwise load the Data Engineering resume template."""
    if profile_text and profile_text.strip():
        return profile_text.strip()

    path = _DATA_DIR / DE_PROFILE_FILE
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return ""


def list_profile_templates() -> dict[str, str]:
    """Return role -> filename for templates that exist on disk."""
    available: dict[str, str] = {}
    for role, filename in ROLE_PROFILE_FILES.items():
        if (_DATA_DIR / filename).is_file():
            available[role] = filename
    return available
