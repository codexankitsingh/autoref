"""Router: User Profile & Mail Account Management."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from schemas import UserProfileRequest, UserProfileResponse, MailAccountResponse
from models.user import User
from models.mail_account import MailAccount
from dependencies import get_approved_user
from services.profile_defaults import resolve_profile_text, list_profile_templates
from services.outreach_constants import normalize_target_role
from services.llm_client import check_ai_connectivity

router = APIRouter(prefix="/api", tags=["settings"])


# ── User Profile ──

@router.get("/profile", response_model=UserProfileResponse)
def get_profile(current_user: User = Depends(get_approved_user)):
    """Get the current user's profile."""
    return current_user


@router.get("/ai-health")
def get_ai_health(current_user: User = Depends(get_approved_user)):
    """Check Gemini / OpenAI connectivity for diagnostics."""
    return check_ai_connectivity()


@router.get("/profile/templates")
def get_profile_templates(current_user: User = Depends(get_approved_user)):
    """List roles that have a built-in resume template on the server."""
    return {"templates": list(list_profile_templates().keys())}


@router.get("/profile/template/{role_slug}")
def get_profile_template(role_slug: str, current_user: User = Depends(get_approved_user)):
    """
    Fetch default profile text for a role. role_slug examples: data-engineering
    """
    slug_to_role = {
        "data-engineering": "Data Engineering",
    }
    target_role = slug_to_role.get(role_slug.replace("_", "-").lower())
    if not target_role:
        raise HTTPException(status_code=404, detail="Unknown profile template")

    text = resolve_profile_text(None, target_role)
    if not text:
        raise HTTPException(status_code=404, detail="Template file missing on server")
    return {"target_role": target_role, "profile_text": text}


@router.post("/profile", response_model=UserProfileResponse)
def create_or_update_profile(
    request: UserProfileRequest,
    current_user: User = Depends(get_approved_user),
    db: Session = Depends(get_db),
):
    """Update current user's profile."""
    current_user.name = request.name
    current_user.email = request.email
    current_user.profile_text = request.profile_text
    current_user.default_target_role = normalize_target_role(request.default_target_role)
    if request.default_follow_up_interval_days is not None:
        current_user.default_follow_up_interval_days = request.default_follow_up_interval_days
    if request.default_max_follow_ups is not None:
        current_user.default_max_follow_ups = request.default_max_follow_ups
    if request.default_ai_model is not None:
        current_user.default_ai_model = request.default_ai_model
    db.commit()
    db.refresh(current_user)
    return current_user


# ── Mail Accounts ──

@router.get("/mail-accounts", response_model=list[MailAccountResponse])
def get_mail_accounts(
    current_user: User = Depends(get_approved_user),
    db: Session = Depends(get_db),
):
    """List connected mail accounts for the current user."""
    accounts = db.query(MailAccount).filter(
        MailAccount.user_id == current_user.id,
        MailAccount.is_active == 1,
    ).all()
    return [MailAccountResponse(id=a.id, email=a.email, is_active=bool(a.is_active)) for a in accounts]


@router.post("/mail-accounts")
def add_mail_account(
    email: str,
    current_user: User = Depends(get_approved_user),
    db: Session = Depends(get_db),
):
    """Add a mail account for the current user."""
    existing = db.query(MailAccount).filter(MailAccount.email == email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Account already exists")

    account = MailAccount(user_id=current_user.id, email=email, is_active=1)
    db.add(account)
    db.commit()
    db.refresh(account)
    return {"id": account.id, "email": account.email, "message": "Account added (OAuth pending)"}
