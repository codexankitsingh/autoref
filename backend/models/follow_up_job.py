from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class FollowUpJob(Base):
    __tablename__ = "follow_up_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    thread_id = Column(Integer, ForeignKey("email_threads.id"), nullable=False)
    follow_up_number = Column(Integer, nullable=False)  # 1, 2, or 3
    scheduled_time = Column(DateTime, nullable=False)
    status = Column(String(20), default="pending")  # pending, sent, cancelled
    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    thread = relationship("EmailThread", back_populates="follow_up_jobs")
