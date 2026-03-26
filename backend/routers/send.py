"""Router: Email Sending & Gmail OAuth."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime

from database import get_db
from schemas import SendEmailRequest, SendEmailResponse
from models.job_application import JobApplication
from models.recipient import Recipient
from models.email_thread import EmailThread
from models.message import Message
from services.email_service import email_service
from services.scheduler_service import scheduler_service
from config import get_settings

router = APIRouter(prefix="/api", tags=["send"])


@router.post("/send-email", response_model=SendEmailResponse)
def send_email(request: SendEmailRequest, db: Session = Depends(get_db)):
    """Send an email and create tracking records."""
    try:
        # 1. Create JobApplication
        application = JobApplication(
            company=request.company,
            role=request.role,
            jd_text=request.jd_text or "",
            skills=request.skills,
            location=request.location,
        )
        db.add(application)
        db.flush()

        # 2. Create or find Recipient
        recipient = db.query(Recipient).filter(Recipient.email == request.recipient_email).first()
        if not recipient:
            recipient = Recipient(
                email=request.recipient_email,
                name=request.recipient_name,
                company=request.company,
            )
            db.add(recipient)
            db.flush()

        # 3. Send via Gmail API
        send_result = email_service.send_email(
            db=db,
            sender_account_id=request.sender_account_id,
            recipient_email=request.recipient_email,
            subject=request.email_subject,
            body=request.email_body,
        )

        # 4. Create EmailThread
        thread = EmailThread(
            application_id=application.id,
            recipient_id=recipient.id,
            sender_account_id=request.sender_account_id,
            gmail_thread_id=send_result.get("gmail_thread_id"),
            status="sent",
            follow_up_interval_days=request.follow_up_interval_days,
            max_follow_ups=request.max_follow_ups,
            last_activity_at=datetime.utcnow(),
        )
        db.add(thread)
        db.flush()

        # 5. Create Message record
        message = Message(
            thread_id=thread.id,
            gmail_message_id=send_result.get("gmail_message_id"),
            message_type="initial",
            subject=request.email_subject,
            content=request.email_body,
            sent_at=datetime.utcnow(),
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
def gmail_auth():
    """Initiate Gmail OAuth2 flow."""
    settings = get_settings()
    if not settings.google_client_id or settings.google_client_id == "your-google-client-id":
        raise HTTPException(
            status_code=400,
            detail="Google OAuth not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env"
        )

    try:
        auth_url = email_service.get_auth_url()
        return {"auth_url": auth_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate auth URL: {str(e)}")


@router.get("/auth/gmail/callback")
def gmail_callback(code: str, db: Session = Depends(get_db)):
    """Handle Gmail OAuth2 callback."""
    try:
        result = email_service.handle_oauth_callback(code, db)
        settings = get_settings()
        # Redirect to frontend settings page with success message
        return RedirectResponse(url=f"{settings.frontend_url}/settings?gmail_connected={result['email']}")
    except Exception as e:
        settings = get_settings()
        return RedirectResponse(url=f"{settings.frontend_url}/settings?gmail_error={str(e)}")
