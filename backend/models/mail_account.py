from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class MailAccount(Base):
    __tablename__ = "mail_accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    email = Column(String(255), nullable=False, unique=True)
    oauth_token = Column(Text, nullable=True)  # Encrypted OAuth token JSON
    refresh_token = Column(Text, nullable=True)
    token_expiry = Column(DateTime, nullable=True)
    is_active = Column(Integer, default=1)  # SQLite-friendly boolean
    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="mail_accounts")
    email_threads = relationship("EmailThread", back_populates="sender_account")
