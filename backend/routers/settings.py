"""Router: User Profile & Mail Account Management."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from schemas import UserProfileRequest, UserProfileResponse, MailAccountResponse
from models.user import User
from models.mail_account import MailAccount

router = APIRouter(prefix="/api", tags=["settings"])


# ── User Profile ──

@router.get("/profile", response_model=UserProfileResponse)
def get_profile(db: Session = Depends(get_db)):
    """Get user profile (single-user MVP)."""
    user = db.query(User).first()
    if not user:
        raise HTTPException(status_code=404, detail="No profile found. Please create one.")
    return user


@router.post("/profile", response_model=UserProfileResponse)
def create_or_update_profile(request: UserProfileRequest, db: Session = Depends(get_db)):
    """Create or update user profile."""
    user = db.query(User).first()
    if user:
        user.name = request.name
        user.email = request.email
        user.profile_text = request.profile_text
    else:
        user = User(
            name=request.name,
            email=request.email,
            profile_text=request.profile_text,
        )
        db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ── Mail Accounts ──

@router.get("/mail-accounts", response_model=list[MailAccountResponse])
def get_mail_accounts(db: Session = Depends(get_db)):
    """List connected mail accounts."""
    accounts = db.query(MailAccount).filter(MailAccount.is_active == 1).all()
    return [MailAccountResponse(id=a.id, email=a.email, is_active=bool(a.is_active)) for a in accounts]


@router.post("/mail-accounts")
def add_mail_account(email: str, db: Session = Depends(get_db)):
    """Add a mail account (placeholder — OAuth flow will handle this in Phase 3)."""
    user = db.query(User).first()
    if not user:
        raise HTTPException(status_code=400, detail="Create a user profile first")

    existing = db.query(MailAccount).filter(MailAccount.email == email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Account already exists")

    account = MailAccount(user_id=user.id, email=email, is_active=1)
    db.add(account)
    db.commit()
    db.refresh(account)
    return {"id": account.id, "email": account.email, "message": "Account added (OAuth pending)"}
