from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class EmailThread(Base):
    __tablename__ = "email_threads"

    id = Column(Integer, primary_key=True, autoincrement=True)
    application_id = Column(Integer, ForeignKey("job_applications.id"), nullable=False)
    recipient_id = Column(Integer, ForeignKey("recipients.id"), nullable=False)
    sender_account_id = Column(Integer, ForeignKey("mail_accounts.id"), nullable=False)
    gmail_thread_id = Column(String(255), nullable=True)  # Gmail thread ID
    status = Column(String(50), default="draft")
    # Statuses: draft, sent, follow_up_1, follow_up_2, follow_up_3, replied, interview_scheduled, closed
    follow_up_count = Column(Integer, default=0)
    follow_up_interval_days = Column(Integer, default=3)
    max_follow_ups = Column(Integer, default=3)
    last_activity_at = Column(DateTime, server_default=func.now())
    replied = Column(Integer, default=0)  # SQLite-friendly boolean
    interview_scheduled = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    application = relationship("JobApplication", back_populates="email_threads")
    recipient = relationship("Recipient", back_populates="email_threads")
    sender_account = relationship("MailAccount", back_populates="email_threads")
    messages = relationship("Message", back_populates="thread", cascade="all, delete-orphan")
    follow_up_jobs = relationship("FollowUpJob", back_populates="thread", cascade="all, delete-orphan")
    replies = relationship("Reply", back_populates="thread", cascade="all, delete-orphan")
