"""Model: ScrapedJob — Jobs discovered by the automated scraper."""
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class ScrapedJob(Base):
    __tablename__ = "scraped_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Job identity (dedup key = job_url_hash)
    job_url = Column(String(1024), nullable=True)
    job_url_hash = Column(String(64), index=True, unique=True, nullable=True)
    title = Column(String(500), nullable=True)
    company = Column(String(255), nullable=True)
    company_domain = Column(String(255), nullable=True)
    location = Column(String(500), nullable=True)
    description = Column(Text, nullable=True)
    source = Column(String(50), nullable=True)  # linkedin, indeed, glassdoor, manual

    # LLM scoring
    match_score = Column(Integer, nullable=True)  # 0-100
    match_reason = Column(Text, nullable=True)
    missing_skills = Column(Text, nullable=True)  # JSON array
    required_skills = Column(Text, nullable=True)  # JSON array (extracted by LLM)

    # Pipeline status
    # saved → pursued → email_sent → opened → replied → interview → offer → rejected → ghosted
    status = Column(String(50), default="saved")

    # Timestamps
    scraped_at = Column(DateTime, server_default=func.now())
    scored_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User")
