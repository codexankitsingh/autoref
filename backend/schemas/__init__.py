from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


# ── JD & Email Generation ──

class GenerateEmailRequest(BaseModel):
    jd_text: str
    recipient_email: str
    recipient_name: Optional[str] = None
    model: str = "gemini-2.5-flash-lite"
    target_role: str = "Backend/SDE"

class ParsedJD(BaseModel):
    company: Optional[str] = None
    role: Optional[str] = None
    skills: list[str] = []
    location: Optional[str] = None
    job_id: Optional[str] = None
    job_link: Optional[str] = None

class GenerateEmailResponse(BaseModel):
    parsed_jd: ParsedJD
    subject: str
    email_body: str

# ── Send Email ──

class SendEmailRequest(BaseModel):
    email_subject: str
    email_body: str
    recipient_email: str
    recipient_name: Optional[str] = None
    sender_account_id: int
    application_id: Optional[int] = None
    follow_up_interval_days: int = 3
    max_follow_ups: int = 3
    # Parsed JD fields (from generate step)
    company: Optional[str] = None
    role: Optional[str] = None
    jd_text: Optional[str] = None
    skills: Optional[str] = None
    location: Optional[str] = None
    job_id: Optional[str] = None
    job_link: Optional[str] = None

class SendEmailResponse(BaseModel):
    thread_id: int
    gmail_thread_id: Optional[str] = None
    status: str
    message: str

# ── Follow-ups ──

class ScheduleFollowupsRequest(BaseModel):
    thread_id: int
    interval_days: int = 3
    max_follow_ups: int = 3

class StopFollowupsRequest(BaseModel):
    thread_id: int

# ── Dashboard ──

class OutreachRecord(BaseModel):
    id: int
    company: Optional[str]
    role: Optional[str]
    recipient_email: str
    recipient_name: Optional[str]
    sender_email: str
    status: str
    follow_up_count: int
    last_activity_at: Optional[datetime]
    replied: bool
    interview_scheduled: bool
    created_at: datetime

    class Config:
        from_attributes = True

class DashboardResponse(BaseModel):
    records: list[OutreachRecord]
    total: int

# ── Status Update ──

class UpdateStatusRequest(BaseModel):
    thread_id: int
    status: str
    interview_scheduled: Optional[bool] = None
    replied: Optional[bool] = None

# ── Mail Accounts ──

class MailAccountResponse(BaseModel):
    id: int
    email: str
    is_active: bool

    class Config:
        from_attributes = True

# ── User Profile ──

class UserProfileRequest(BaseModel):
    name: str
    email: str
    profile_text: Optional[str] = None

class UserProfileResponse(BaseModel):
    id: int
    name: str
    email: str
    profile_text: Optional[str]

    class Config:
        from_attributes = True
