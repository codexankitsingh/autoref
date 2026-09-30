from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=True)  # Null for Google OAuth users
    profile_text = Column(Text, nullable=True)  # Pre-stored resume/profile for AI
    google_id = Column(String(255), nullable=True, unique=True)  # Google OAuth subject ID
    avatar_url = Column(String(512), nullable=True)  # Google profile picture
    is_active = Column(Integer, default=1)  # SQLite-friendly boolean
    is_approved = Column(Integer, default=0)  # Admin must approve before user can use the app
    is_admin = Column(Integer, default=0)  # Admin users can approve others
    default_target_role = Column(String(64), default="Data Engineering", nullable=False)
    default_follow_up_interval_days = Column(Integer, default=3, nullable=False)
    default_max_follow_ups = Column(Integer, default=3, nullable=False)
    default_ai_model = Column(String(64), default="gemini-2.5-flash-lite", nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    mail_accounts = relationship("MailAccount", back_populates="user", cascade="all, delete-orphan")
