"""
Email Service — Gmail API integration.
Handles OAuth2 flow, email sending, and reply checking.
"""
import os
import base64
import json
import re
import urllib.parse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# Prevent "Scope has changed" errors from Google OAuth
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from sqlalchemy.orm import Session
from config import get_settings
from models.mail_account import MailAccount


# Gmail & Sheets API scopes
SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/spreadsheets",
]


class EmailService:
    """Handles Gmail OAuth and email sending."""

    def __init__(self):
        self.settings = get_settings()

    def get_oauth_flow(self) -> Flow:
        """Create OAuth2 flow for Gmail."""
        client_config = {
            "web": {
                "client_id": self.settings.google_client_id,
                "client_secret": self.settings.google_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [self.settings.google_redirect_uri],
            }
        }
        flow = Flow.from_client_config(client_config, scopes=SCOPES)
        flow.redirect_uri = self.settings.google_redirect_uri
        return flow

    def get_auth_url(self, state: str = "") -> str:
        """Generate Gmail OAuth authorization URL with optional state."""
        flow = self.get_oauth_flow()
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            state=state,
        )
        return auth_url

    def handle_oauth_callback(self, code: str, db: Session, user_id: int = None) -> dict:
        """Handle OAuth callback, exchange code for tokens, save account."""
        flow = self.get_oauth_flow()
        flow.fetch_token(code=code)
        credentials = flow.credentials

        # Get user email from Gmail API
        service = build("gmail", "v1", credentials=credentials)
        profile = service.users().getProfile(userId="me").execute()
        email_address = profile.get("emailAddress", "")

        # Find the user who initiated the OAuth flow
        from models.user import User
        user = None
        if user_id:
            user = db.query(User).filter(User.id == user_id).first()
        if not user:
            # Fallback: try to match by email
            user = db.query(User).filter(User.email == email_address).first()
        if not user:
            # Last resort: first user (for backward compatibility)
            user = db.query(User).first()
        if not user:
            raise ValueError("No user found. Please register first.")

        # Save or update mail account
        account = db.query(MailAccount).filter(MailAccount.email == email_address).first()
        token_data = json.dumps({
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": list(credentials.scopes or []),
        })

        if account:
            account.oauth_token = token_data
            account.refresh_token = credentials.refresh_token
            account.token_expiry = credentials.expiry
            account.is_active = 1
        else:
            account = MailAccount(
                user_id=user.id,
                email=email_address,
                oauth_token=token_data,
                refresh_token=credentials.refresh_token,
                token_expiry=credentials.expiry,
                is_active=1,
            )
            db.add(account)

        db.commit()
        db.refresh(account)

        return {
            "email": email_address,
            "account_id": account.id,
            "message": "Gmail account connected successfully!",
        }

    def _get_gmail_service(self, account: MailAccount):
        """Build Gmail service from stored credentials."""
        if not account.oauth_token:
            raise ValueError(f"No OAuth token for account {account.email}")

        token_data = json.loads(account.oauth_token)
        credentials = Credentials(
            token=token_data.get("token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=token_data.get("client_id", self.settings.google_client_id),
            client_secret=token_data.get("client_secret", self.settings.google_client_secret),
            scopes=token_data.get("scopes", SCOPES),
        )
        return build("gmail", "v1", credentials=credentials)

    def send_email(
        self, db: Session, sender_account_id: int, recipient_email: str,
        subject: str, body: str, thread_id: str = None, tracking_id: str = None
    ) -> dict:
        """
        Send an email via Gmail API.
        Returns: {"gmail_thread_id": str, "gmail_message_id": str}
        """
        account = db.query(MailAccount).filter(MailAccount.id == sender_account_id).first()
        if not account:
            raise ValueError(f"Sender account {sender_account_id} not found")

        if not account.oauth_token:
            # Fallback: no OAuth configured yet, return stub
            return {
                "gmail_thread_id": f"stub_thread_{datetime.utcnow().timestamp()}",
                "gmail_message_id": f"stub_msg_{datetime.utcnow().timestamp()}",
            }

        service = self._get_gmail_service(account)

        # Build email message
        message = MIMEMultipart()
        message["to"] = recipient_email
        message["from"] = account.email
        message["subject"] = subject
        
        # Link Click Tracking (Phase 2 Upgrade)
        # Only wraps resume/document links with tracking redirects.
        # Social links (LinkedIn, GitHub) in the signature are excluded because
        # email security scanners pre-fetch ALL links, inflating click counts.
        SKIP_DOMAINS = ["linkedin.com", "github.com", "twitter.com", "x.com"]
        if tracking_id:
            def replace_href(match):
                original_url = match.group(1)
                # Ignore mailto links or anchor links
                if original_url.startswith("mailto:") or original_url.startswith("#"):
                    return match.group(0)
                # Skip social profile links (scanners pre-fetch these)
                if any(domain in original_url.lower() for domain in SKIP_DOMAINS):
                    return match.group(0)
                encoded_url = urllib.parse.quote(original_url, safe='')
                tracking_url = f"https://autoref-zz6o.onrender.com/api/track/click/{tracking_id}?url={encoded_url}"
                return f'href="{tracking_url}"'
            
            # Match href="URL" or href='URL'
            body = re.sub(r'href=["\'](.*?)["\']', replace_href, body)
            
        msg_body = MIMEText(body, "html")
        message.attach(msg_body)

        # Encode
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        gmail_body = {"raw": raw}

        # If replying in a thread
        if thread_id:
            gmail_body["threadId"] = thread_id

        # Send
        sent = service.users().messages().send(userId="me", body=gmail_body).execute()

        return {
            "gmail_thread_id": sent.get("threadId", ""),
            "gmail_message_id": sent.get("id", ""),
        }

    def check_replies(self, db: Session, gmail_thread_id: str, sender_account_id: int) -> list[dict]:
        """
        Check for new replies in a Gmail thread.
        Returns list of reply messages.
        """
        account = db.query(MailAccount).filter(MailAccount.id == sender_account_id).first()
        if not account or not account.oauth_token:
            return []

        try:
            service = self._get_gmail_service(account)
            thread = service.users().threads().get(userId="me", id=gmail_thread_id).execute()
            messages = thread.get("messages", [])

            replies = []
            # Get our own email to filter out our sent messages
            our_email = account.email.lower()

            for msg in messages[1:]:  # Skip first message (our sent email)
                headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
                from_addr = headers.get("From", "").lower()

                # ONLY detect replies from OTHER people.
                # Do NOT use INBOX label — our own follow-ups in the same thread
                # can have INBOX label and would be falsely counted as replies.
                is_from_other = our_email not in from_addr

                if is_from_other:
                    from_addr_display = headers.get("From", "")
                    
                    # Extract body
                    body = ""
                    payload = msg.get("payload", {})
                    if "body" in payload and payload["body"].get("data"):
                        body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8")
                    elif "parts" in payload:
                        for part in payload["parts"]:
                            if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                                body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
                                break

                    replies.append({
                        "gmail_message_id": msg.get("id"),
                        "from": from_addr_display,
                        "content": body,
                        "received_at": headers.get("Date"),
                    })

            return replies
        except Exception as e:
            print(f"Error checking replies: {e}")
            return []

    def process_incoming_webhook(self, account_id: int, history_id: int):
        """
        Background worker that fetches changed messages based on Pub/Sub historyId,
        checks if they belong to active AutoRef threads, uses Gemini to categorize them,
        and halts follow-ups if appropriate.
        """
        from database import SessionLocal
        from models.email_thread import EmailThread
        from services.scheduler_service import scheduler_service
        from services.ai_service import ai_service
        
        db = SessionLocal()
        try:
            account = db.query(MailAccount).filter(MailAccount.id == account_id).first()
            if not account or not account.oauth_token:
                return

            service = self._get_gmail_service(account)
            
            # Fetch history since the given historyId
            # Note: For robust implementations, we should store the last known historyId 
            # and request everything since then. For simplicity here, we use the provided historyId.
            history_response = service.users().history().list(
                userId="me", 
                startHistoryId=max(1, int(history_id) - 1000) # Give a small buffer
            ).execute()

            changes = history_response.get("history", [])
            for record in changes:
                # Look for newly added messages
                if "messagesAdded" in record:
                    for msg_added in record["messagesAdded"]:
                        msg_info = msg_added.get("message", {})
                        gmail_msg_id = msg_info.get("id")
                        gmail_thread_id = msg_info.get("threadId")

                        # Does this thread exist in our DB?
                        thread = db.query(EmailThread).filter(EmailThread.gmail_thread_id == gmail_thread_id).first()
                        if not thread:
                            continue # Not an AutoRef thread

                        # We found a new message in an AutoRef thread. 
                        # Check if it's actually a reply from the other person.
                        new_replies = self.check_replies(db, gmail_thread_id, account_id)
                        
                        if new_replies:
                            # Take the latest reply content
                            latest_reply = new_replies[-1]
                            reply_text = latest_reply["content"]
                            
                            print(f"🔔 Received reply for thread {thread.id}. Categorizing intent...")
                            
                            # AI Categorization
                            intent = ai_service.categorize_reply(reply_text)
                            print(f"🤖 Categorized as: {intent}")
                            
                            thread.replied = True
                            if intent == "interview_requested":
                                thread.status = "interview_scheduled"
                            elif intent == "referral_provided":
                                thread.status = "replied" # Custom state if needed, sticking to core states
                            elif intent == "rejected":
                                thread.status = "rejected"
                            else:
                                thread.status = "replied"
                                
                            db.commit()

                            # Auto-Ghost: Cancel any pending automated follow-ups instantly
                            scheduler_service.cancel_follow_ups(thread.id)
                            
        except Exception as e:
            print(f"Webhook processing error: {e}")
        finally:
            db.close()

# Singleton
email_service = EmailService()
