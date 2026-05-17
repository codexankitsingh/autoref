"""Router: User Profile & Mail Account Management."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from schemas import UserProfileRequest, UserProfileResponse, MailAccountResponse
from models.user import User
from models.mail_account import MailAccount
from dependencies import get_approved_user

router = APIRouter(prefix="/api", tags=["settings"])


# ── User Profile ──

@router.get("/profile", response_model=UserProfileResponse)
def get_profile(current_user: User = Depends(get_approved_user)):
    """Get the current user's profile."""
    return current_user


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
