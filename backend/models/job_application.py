from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class JobApplication(Base):
    __tablename__ = "job_applications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    company = Column(String(255), nullable=True)
    role = Column(String(255), nullable=True)
    jd_text = Column(Text, nullable=False)
    skills = Column(Text, nullable=True)  # JSON string of extracted skills
    location = Column(String(255), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    user = relationship("User")
    email_threads = relationship("EmailThread", back_populates="application", cascade="all, delete-orphan")
