from fastapi import APIRouter, Depends, Request, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
import base64
import json

from database import get_db
from models.mail_account import MailAccount
from services.email_service import email_service

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

@router.post("/gmail")
async def gmail_pubsub_webhook(request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Receives push notifications from Google Cloud Pub/Sub when an inbox changes.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    message = body.get("message", {})
    data_b64 = message.get("data")

    if not data_b64:
        # Pub/Sub expects a 200 OK even if the message is malformed, so it doesn't retry infinitely
        return {"status": "ok"}

    try:
        # Decode base64 payload
        data_json = base64.b64decode(data_b64).decode("utf-8")
        event = json.loads(data_json)
        email_address = event.get("emailAddress")
        history_id = event.get("historyId")
    except Exception as e:
        print(f"Error decoding Pub/Sub payload: {e}")
        return {"status": "ok"}

    if not email_address or not history_id:
        return {"status": "ok"}

    # Find the mail account
    account = db.query(MailAccount).filter(MailAccount.email == email_address).first()
    if not account:
        print(f"Received webhook for unknown email: {email_address}")
        return {"status": "ok"}

    # Delegate processing to background task to respond to Google quickly
    background_tasks.add_task(
        email_service.process_incoming_webhook,
        account_id=account.id,
        history_id=history_id
    )

    return {"status": "ok", "message": "Event received and processing"}

@router.post("/gmail/watch")
def setup_gmail_watch(account_id: int, topic_name: str, db: Session = Depends(get_db)):
    """
    Registers the Gmail Pub/Sub push notification watcher for a specific account.
    topic_name should look like: projects/[PROJECT_ID]/topics/[TOPIC_NAME]
    """
    account = db.query(MailAccount).filter(MailAccount.id == account_id).first()
    if not account or not account.oauth_token:
        raise HTTPException(status_code=404, detail="Mail account not found or not authenticated")

    try:
        service = email_service._get_gmail_service(account)
        request = {
            'labelIds': ['INBOX'],
            'topicName': topic_name
        }
        response = service.users().watch(userId='me', body=request).execute()
        return {"status": "success", "historyId": response.get("historyId")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
