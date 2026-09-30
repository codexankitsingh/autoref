"""Default resume/profile text when the user has not saved profile_text yet."""
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

ROLE_PROFILE_FILES: dict[str, str] = {
    "Data Engineering": "default_profile_data_engineering.txt",
}


def resolve_profile_text(profile_text: str | None, target_role: str) -> str:
    """Prefer saved profile; otherwise load role-specific default from backend/data/."""
    if profile_text and profile_text.strip():
        return profile_text.strip()

    filename = ROLE_PROFILE_FILES.get(target_role)
    if not filename:
        return ""

    path = _DATA_DIR / filename
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
