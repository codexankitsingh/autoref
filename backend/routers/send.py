"""Router: Email Sending & Gmail OAuth."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime
import uuid

from database import get_db
from schemas import SendEmailRequest, SendEmailResponse
from models.user import User
from models.job_application import JobApplication
from models.recipient import Recipient
from models.email_thread import EmailThread
from models.message import Message
from services.email_service import email_service
from services.scheduler_service import scheduler_service
from services.email_quality import finalize_generated_email, validate_outbound_email
from sqlalchemy import or_
from config import get_settings
from dependencies import get_approved_user

router = APIRouter(prefix="/api", tags=["send"])


@router.post("/send-email", response_model=SendEmailResponse)
def send_email(
    request: SendEmailRequest,
    current_user: User = Depends(get_approved_user),
    db: Session = Depends(get_db),
):
    """Send an email and create tracking records, scoped to current user."""
    try:
        subject, body = finalize_generated_email(
            request.email_subject,
            request.email_body,
            request.recipient_name,
        )
        issues = validate_outbound_email(subject, body)
        if issues:
            raise HTTPException(
                status_code=422,
                detail="Cannot send — fix these issues first: " + " ".join(issues),
            )

        target_role = request.target_role or current_user.default_target_role or "Data Engineering"

        # 1. Create JobApplication (scoped to user)
        application = JobApplication(
            user_id=current_user.id,
            company=request.company,
            role=request.role,
            jd_text=request.jd_text or "",
            skills=request.skills,
            location=request.location,
            target_role=target_role,
        )
        db.add(application)
        db.flush()

        # 2. Create or find Recipient (scoped to user)
        recipient = (
            db.query(Recipient)
            .filter(
                Recipient.email == request.recipient_email,
                or_(Recipient.user_id == current_user.id, Recipient.user_id.is_(None)),
            )
            .first()
        )
        if not recipient:
            recipient = Recipient(
                user_id=current_user.id,
                email=request.recipient_email,
                name=request.recipient_name,
                company=request.company,
            )
            db.add(recipient)
            db.flush()
        else:
            recipient.user_id = current_user.id
            if request.recipient_name:
                recipient.name = request.recipient_name
            if request.company:
                recipient.company = request.company
            db.flush()

        # 3. Generate Tracking ID (Phase 2)
        tracking_id = str(uuid.uuid4())

        # 4. Send via Gmail API
        send_result = email_service.send_email(
            db=db,
            sender_account_id=request.sender_account_id,
            recipient_email=request.recipient_email,
            subject=subject,
            body=body,
            tracking_id=tracking_id,
        )

        # 4. Create EmailThread (scoped to user)
        thread = EmailThread(
            user_id=current_user.id,
            application_id=application.id,
            recipient_id=recipient.id,
            sender_account_id=request.sender_account_id,
            gmail_thread_id=send_result.get("gmail_thread_id"),
            status="sent",
            follow_up_interval_days=request.follow_up_interval_days,
            max_follow_ups=request.max_follow_ups,
            target_role=target_role,
            last_activity_at=datetime.utcnow(),
        )
        db.add(thread)
        db.flush()

        # 6. Create Message record
        message = Message(
            thread_id=thread.id,
            gmail_message_id=send_result.get("gmail_message_id"),
            message_type="initial",
            subject=subject,
            content=body,
            sent_at=datetime.utcnow(),
            tracking_id=tracking_id,
        )
        db.add(message)
        db.commit()

        # 6. Auto-schedule follow-ups
        if request.max_follow_ups > 0:
            scheduler_service.schedule_follow_ups(
                thread_id=thread.id,
                interval_days=request.follow_up_interval_days,
                max_follow_ups=request.max_follow_ups,
            )

        return SendEmailResponse(
            thread_id=thread.id,
            gmail_thread_id=send_result.get("gmail_thread_id"),
            status="sent",
            message="Email sent successfully!",
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")


# ── Gmail OAuth Routes ──

@router.get("/auth/gmail")
def gmail_auth(current_user: User = Depends(get_approved_user)):
    """Initiate Gmail OAuth2 flow. Passes user_id in the OAuth state."""
    settings = get_settings()
    if not settings.google_client_id or settings.google_client_id == "your-google-client-id":
        raise HTTPException(
            status_code=400,
            detail="Google OAuth not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env"
        )

    try:
        auth_url = email_service.get_auth_url(state=str(current_user.id))
        return {"auth_url": auth_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate auth URL: {str(e)}")


@router.get("/auth/gmail/callback")
def gmail_callback(code: str, state: str = "", db: Session = Depends(get_db)):
    """Handle Gmail OAuth2 callback. Uses state param to identify the user."""
    try:
        user_id = int(state) if state else None
        result = email_service.handle_oauth_callback(code, db, user_id=user_id)
        settings = get_settings()
        return RedirectResponse(url=f"{settings.frontend_url}/settings?gmail_connected={result['email']}")
    except Exception as e:
        settings = get_settings()
        return RedirectResponse(url=f"{settings.frontend_url}/settings?gmail_error={str(e)}")

