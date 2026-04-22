"""
Email Service — Gmail API integration.
Handles OAuth2 flow, email sending, and reply checking.
"""
import base64
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

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

    def get_auth_url(self) -> str:
        """Generate Gmail OAuth authorization URL."""
        flow = self.get_oauth_flow()
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        return auth_url

    def handle_oauth_callback(self, code: str, db: Session) -> dict:
        """Handle OAuth callback, exchange code for tokens, save account."""
        flow = self.get_oauth_flow()
        flow.fetch_token(code=code)
        credentials = flow.credentials

        # Get user email from Gmail API
        service = build("gmail", "v1", credentials=credentials)
        profile = service.users().getProfile(userId="me").execute()
        email_address = profile.get("emailAddress", "")

        # Find first user (single-user MVP)
        from models.user import User
        user = db.query(User).first()
        if not user:
            # Create a default user
            user = User(name="AutoRef User", email=email_address)
            db.add(user)
            db.flush()

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
        subject: str, body: str, thread_id: str = None
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


# Singleton
email_service = EmailService()
