"""
Sheets Service — Google Sheets API integration.
Synchronizes outreach records to a Google Spreadsheet.
"""
import json
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from sqlalchemy.orm import Session

from config import get_settings
from models.mail_account import MailAccount


class SheetsService:
    """Handles Google Sheets API interactions."""

    def __init__(self):
        self.settings = get_settings()

    def _get_sheets_service(self, db: Session, account_id: int):
        """Build Google Sheets service from stored credentials."""
        account = db.query(MailAccount).filter(MailAccount.id == account_id).first()
        if not account or not account.oauth_token:
            raise ValueError(f"Sender account {account_id} not connected or missing OAuth token.")

        token_data = json.loads(account.oauth_token)
        credentials = Credentials(
            token=token_data.get("token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=token_data.get("client_id", self.settings.google_client_id),
            client_secret=token_data.get("client_secret", self.settings.google_client_secret),
            scopes=token_data.get("scopes", []),
        )
        return build("sheets", "v4", credentials=credentials)

    def export_dashboard(self, db: Session, account_id: int, spreadsheet_id: str = None) -> str:
        """
        Exports all dashboard records to a Google Sheet.
        If spreadsheet_id is not provided, it creates a new one.
        Returns the spreadsheet ID.
        """
        service = self._get_sheets_service(db, account_id)

        # 1. Fetch data directly
        from models.email_thread import EmailThread
        from sqlalchemy.orm import joinedload
        
        threads = db.query(EmailThread).options(
            joinedload(EmailThread.application),
            joinedload(EmailThread.recipient),
            joinedload(EmailThread.sender_account),
        ).order_by(EmailThread.last_activity_at.desc()).all()

        # 2. Format rows
        headers = ["Date", "Company", "Role", "Recipient Name", "Recipient Email", "Sender Email", "Status", "Follow Ups", "Replied", "Interview Scheduled"]
        values = [headers]
        for t in threads:
            created_str = t.created_at.strftime("%Y-%m-%d %H:%M:%S") if t.created_at else ""
            company = t.application.company if t.application else ""
            role = t.application.role if t.application else ""
            rec_name = t.recipient.name if t.recipient else ""
            rec_email = t.recipient.email if t.recipient else ""
            send_email = t.sender_account.email if t.sender_account else ""
            
            values.append([
                created_str,
                company,
                role,
                rec_name,
                rec_email,
                send_email,
                t.status or "",
                str(t.follow_up_count),
                "Yes" if t.replied else "No",
                "Yes" if t.interview_scheduled else "No",
            ])

        body = {"values": values}

        # 3. Create or update
        if not spreadsheet_id:
            spreadsheet = {
                "properties": {
                    "title": "AutoRef Outreach Tracker"
                }
            }
            spreadsheet = service.spreadsheets().create(body=spreadsheet, fields="spreadsheetId").execute()
            spreadsheet_id = spreadsheet.get("spreadsheetId")

        # Clear existing
        service.spreadsheets().values().clear(
            spreadsheetId=spreadsheet_id,
            range="Sheet1",
            body={}
        ).execute()

        # Insert new data
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range="Sheet1!A1",
            valueInputOption="RAW",
            body=body
        ).execute()

        # Bold headers
        requests = [{
            "repeatCell": {
                "range": {
                    "sheetId": 0,
                    "startRowIndex": 0,
                    "endRowIndex": 1
                },
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {"bold": True}
                    }
                },
                "fields": "userEnteredFormat.textFormat.bold"
            }
        }]
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": requests}
        ).execute()

        return spreadsheet_id


# Singleton
sheets_service = SheetsService()
