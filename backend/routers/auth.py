"""Router: Authentication — Register, Login, Google OAuth, Admin Approval."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from database import get_db
from config import get_settings
from models.user import User
from schemas import (
    RegisterRequest, LoginRequest, TokenResponse, AuthUserResponse,
    GoogleLoginRequest, ApproveUserRequest,
)
from dependencies import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token,
    get_current_user, get_admin_user,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _build_token_response(user: User) -> TokenResponse:
    """Helper to build a consistent token response."""
    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user=AuthUserResponse(
            id=user.id,
            name=user.name,
            email=user.email,
            avatar_url=user.avatar_url,
            is_approved=bool(user.is_approved),
            is_admin=bool(user.is_admin),
        ),
    )


# ── Register ──

@router.post("/register", response_model=TokenResponse)
def register(request: RegisterRequest, db: Session = Depends(get_db)):
    """Register a new account with email/password."""
    if len(request.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    existing = db.query(User).filter(User.email == request.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    settings = get_settings()

    # First user ever OR matching admin_email → auto-approve as admin
    user_count = db.query(User).count()
    is_first_user = user_count == 0
    is_admin_email = settings.admin_email and request.email.lower() == settings.admin_email.lower()

    user = User(
        name=request.name,
        email=request.email,
        password_hash=hash_password(request.password),
        is_approved=1 if (is_first_user or is_admin_email) else 0,
        is_admin=1 if (is_first_user or is_admin_email) else 0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return _build_token_response(user)


# ── Login ──

@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """Login with email/password."""
    user = db.query(User).filter(User.email == request.email).first()
    if not user or not user.password_hash:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated")

    return _build_token_response(user)


# ── Google Login ──

@router.post("/google", response_model=TokenResponse)
def google_login(request: GoogleLoginRequest, db: Session = Depends(get_db)):
    """Login or register with a Google ID token (from Sign In with Google button)."""
    settings = get_settings()

    if not settings.google_client_id:
        raise HTTPException(status_code=400, detail="Google OAuth not configured on the server")

    try:
        # Verify the Google ID token
        idinfo = id_token.verify_oauth2_token(
            request.credential,
            google_requests.Request(),
            settings.google_client_id,
        )
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid Google token")

    google_id = idinfo["sub"]
    email = idinfo.get("email", "")
    name = idinfo.get("name", email.split("@")[0])
    avatar_url = idinfo.get("picture")

    # Check if user already exists (by google_id OR email)
    user = db.query(User).filter(
        (User.google_id == google_id) | (User.email == email)
    ).first()

    if user:
        # Link Google account if not already linked
        if not user.google_id:
            user.google_id = google_id
        if avatar_url and not user.avatar_url:
            user.avatar_url = avatar_url
        db.commit()
    else:
        # New user via Google
        user_count = db.query(User).count()
        is_first_user = user_count == 0
        is_admin_email = settings.admin_email and email.lower() == settings.admin_email.lower()

        user = User(
            name=name,
            email=email,
            google_id=google_id,
            avatar_url=avatar_url,
            is_approved=1 if (is_first_user or is_admin_email) else 0,
            is_admin=1 if (is_first_user or is_admin_email) else 0,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated")

    return _build_token_response(user)


# ── Refresh Token ──

@router.post("/refresh", response_model=TokenResponse)
def refresh_token(refresh_token: str, db: Session = Depends(get_db)):
    """Get a new access token using a refresh token."""
    try:
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = int(payload["sub"])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")

    return _build_token_response(user)


# ── Current User ──

@router.get("/me", response_model=AuthUserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Get the currently authenticated user's profile."""
    return AuthUserResponse(
        id=current_user.id,
        name=current_user.name,
        email=current_user.email,
        avatar_url=current_user.avatar_url,
        is_approved=bool(current_user.is_approved),
        is_admin=bool(current_user.is_admin),
    )


# ── Admin: User Approval ──

@router.get("/pending-users")
def get_pending_users(
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Admin: list all users pending approval."""
    pending = db.query(User).filter(User.is_approved == 0).all()
    return [
        {
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "avatar_url": u.avatar_url,
            "created_at": str(u.created_at),
        }
        for u in pending
    ]


@router.post("/approve-user")
def approve_user(
    request: ApproveUserRequest,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Admin: approve or reject a user."""
    user = db.query(User).filter(User.id == request.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_approved = 1 if request.approved else 0
    db.commit()
    action = "approved" if request.approved else "rejected"
    return {"message": f"User {user.email} {action}", "user_id": user.id}
