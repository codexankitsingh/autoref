from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class JobApplication(Base):
    __tablename__ = "job_applications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company = Column(String(255), nullable=True)
    role = Column(String(255), nullable=True)
    jd_text = Column(Text, nullable=False)
    skills = Column(Text, nullable=True)  # JSON string of extracted skills
    location = Column(String(255), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    email_threads = relationship("EmailThread", back_populates="application", cascade="all, delete-orphan")
