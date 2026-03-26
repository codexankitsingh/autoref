from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    thread_id = Column(Integer, ForeignKey("email_threads.id"), nullable=False)
    gmail_message_id = Column(String(255), nullable=True)  # Gmail message ID
    message_type = Column(String(20), nullable=False)  # 'initial' or 'follow_up'
    subject = Column(String(500), nullable=True)
    content = Column(Text, nullable=False)
    sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    thread = relationship("EmailThread", back_populates="messages")
