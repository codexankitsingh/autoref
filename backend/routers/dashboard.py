"""Router: Dashboard & Status Management."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from typing import Optional

from database import get_db
from schemas import OutreachRecord, DashboardResponse, UpdateStatusRequest
from models.user import User
from models.email_thread import EmailThread
from models.job_application import JobApplication
from models.recipient import Recipient
from models.mail_account import MailAccount
from dependencies import get_approved_user

router = APIRouter(prefix="/api", tags=["dashboard"])

VALID_STATUSES = [
    "draft", "sent", "follow_up_1", "follow_up_2", "follow_up_3",
    "replied", "interview_scheduled", "closed",
]


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    current_user: User = Depends(get_approved_user),
    db: Session = Depends(get_db),
):
    """Get outreach records for the current user's dashboard."""
    query = (
        db.query(EmailThread)
        .filter(EmailThread.user_id == current_user.id)
        .options(
            joinedload(EmailThread.application),
            joinedload(EmailThread.recipient),
            joinedload(EmailThread.sender_account),
            joinedload(EmailThread.messages),
        )
        .order_by(EmailThread.last_activity_at.desc())
    )

    if status:
        query = query.filter(EmailThread.status == status)

    if search:
        query = query.join(JobApplication).filter(
            (JobApplication.company.ilike(f"%{search}%")) |
            (JobApplication.role.ilike(f"%{search}%"))
        )

    threads = query.all()

    records = []
    for t in threads:
        total_opens = sum(m.open_count for m in t.messages if m.open_count)
        last_opened = max((m.last_opened_at for m in t.messages if m.last_opened_at), default=None)
        total_clicks = sum(m.click_count for m in t.messages if m.click_count)
        last_clicked = max((m.last_clicked_at for m in t.messages if m.last_clicked_at), default=None)

        records.append(OutreachRecord(
            id=t.id,
            company=t.application.company if t.application else None,
            role=t.application.role if t.application else None,
            recipient_email=t.recipient.email if t.recipient else "",
            recipient_name=t.recipient.name if t.recipient else None,
            sender_email=t.sender_account.email if t.sender_account else "",
            status=t.status,
            follow_up_count=t.follow_up_count,
            last_activity_at=t.last_activity_at,
            replied=bool(t.replied),
            interview_scheduled=bool(t.interview_scheduled),
            created_at=t.created_at,
            open_count=total_opens,
            last_opened_at=last_opened,
            click_count=total_clicks,
            last_clicked_at=last_clicked,
        ))

    return DashboardResponse(records=records, total=len(records))


@router.post("/update-status")
def update_status(
    request: UpdateStatusRequest,
    current_user: User = Depends(get_approved_user),
    db: Session = Depends(get_db),
):
    """Manually update thread status (only if owned by current user)."""
    thread = db.query(EmailThread).filter(
        EmailThread.id == request.thread_id,
        EmailThread.user_id == current_user.id,
    ).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    if request.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Valid: {VALID_STATUSES}")

    thread.status = request.status

    if request.replied is not None:
        thread.replied = int(request.replied)
    if request.interview_scheduled is not None:
        thread.interview_scheduled = int(request.interview_scheduled)

    db.commit()
    return {"message": "Status updated", "thread_id": request.thread_id, "status": request.status}


@router.get("/dashboard/stats")
def get_dashboard_stats(
    current_user: User = Depends(get_approved_user),
    db: Session = Depends(get_db),
):
    """Get summary statistics for the current user's dashboard."""
    base = db.query(EmailThread).filter(EmailThread.user_id == current_user.id)
    total = base.count()
    sent = base.filter(EmailThread.status != "draft").count()
    replied = base.filter(EmailThread.replied == 1).count()
    interviews = base.filter(EmailThread.interview_scheduled == 1).count()
    return {
        "total": total,
        "sent": sent,
        "replied": replied,
        "interviews": interviews,
    }


@router.get("/dashboard/analytics")
def get_dashboard_analytics(
    current_user: User = Depends(get_approved_user),
    db: Session = Depends(get_db),
):
    """Get conversion funnel and weekly outreach volume for charts."""
    from models.message import Message
    from models.scraped_job import ScrapedJob
    from sqlalchemy import func as sql_func, case, extract

    # ── Conversion Funnel ──
    base = db.query(EmailThread).filter(EmailThread.user_id == current_user.id)

    total_threads = base.count()
    emails_sent = base.filter(EmailThread.status != "draft").count()

    # Clicks: threads that have at least one message with click_count > 0
    threads_with_clicks = (
        base.join(Message)
        .filter(Message.click_count > 0)
        .distinct()
        .count()
    )

    replies = base.filter(EmailThread.replied == 1).count()
    interviews = base.filter(EmailThread.interview_scheduled == 1).count()

    # Scraped jobs count (if table exists and has user_id)
    try:
        scraped_count = db.query(ScrapedJob).count()
    except Exception:
        scraped_count = 0

    funnel = [
        {"stage": "Jobs Scraped", "count": scraped_count},
        {"stage": "Emails Sent", "count": emails_sent},
        {"stage": "Clicked", "count": threads_with_clicks},
        {"stage": "Replied", "count": replies},
        {"stage": "Interviews", "count": interviews},
    ]

    # ── Weekly Outreach Volume (last 12 weeks) ──
    try:
        # PostgreSQL-compatible: use date_trunc
        weekly_data = (
            db.query(
                sql_func.date_trunc('week', EmailThread.created_at).label("week"),
                sql_func.count(EmailThread.id).label("sent"),
                sql_func.sum(case((EmailThread.replied == 1, 1), else_=0)).label("replies"),
            )
            .filter(
                EmailThread.user_id == current_user.id,
                EmailThread.status != "draft",
            )
            .group_by(sql_func.date_trunc('week', EmailThread.created_at))
            .order_by(sql_func.date_trunc('week', EmailThread.created_at))
            .limit(12)
            .all()
        )
        weekly = [
            {
                "week": row.week.strftime("%b %d") if row.week else "Unknown",
                "sent": row.sent,
                "replies": int(row.replies) if row.replies else 0,
            }
            for row in weekly_data
        ]
    except Exception:
        weekly = []

    return {"funnel": funnel, "weekly": weekly}


@router.delete("/thread/{thread_id}")
def delete_thread(
    thread_id: int,
    current_user: User = Depends(get_approved_user),
    db: Session = Depends(get_db),
):
    """Delete an outreach thread (only if owned by current user)."""
    thread = db.query(EmailThread).filter(
        EmailThread.id == thread_id,
        EmailThread.user_id == current_user.id,
    ).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    db.delete(thread)
    db.commit()
    return {"message": "Thread deleted", "thread_id": thread_id}


from pydantic import BaseModel

class SyncSheetsRequest(BaseModel):
    account_id: int
    spreadsheet_id: Optional[str] = None

@router.post("/dashboard/sync-sheets")
def sync_to_sheets(
    request: SyncSheetsRequest,
    current_user: User = Depends(get_approved_user),
    db: Session = Depends(get_db),
):
    """Sync all outreach records to a Google Sheet."""
    from services.sheets_service import sheets_service
    try:
        new_sheet_id = sheets_service.export_dashboard(
            db=db,
            account_id=request.account_id,
            spreadsheet_id=request.spreadsheet_id
        )
        return {
            "message": "Synced to Google Sheets successfully",
            "spreadsheet_id": new_sheet_id,
            "url": f"https://docs.google.com/spreadsheets/d/{new_sheet_id}/edit"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to sync to sheets: {str(e)}")
