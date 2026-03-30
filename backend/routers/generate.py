"""Router: Email Generation from JD."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from schemas import GenerateEmailRequest, GenerateEmailResponse, ParsedJD
from services.ai_service import ai_service
from models.user import User

router = APIRouter(prefix="/api", tags=["generate"])


@router.post("/generate-email", response_model=GenerateEmailResponse)
def generate_email(request: GenerateEmailRequest, db: Session = Depends(get_db)):
    """
    Parse a JD and generate a tailored referral email.
    """
    try:
        # Parse JD
        parsed = ai_service.parse_jd(request.jd_text, model_name=request.model)
        parsed_jd = ParsedJD(**parsed)

        # Get user profile (single-user MVP: use first user or env config)
        user = db.query(User).first()
        user_profile = user.profile_text if user else ""

        # Generate email
        email_data = ai_service.generate_email(
            jd_data=parsed,
            user_profile=user_profile,
            model_name=request.model,
        )

        return GenerateEmailResponse(
            parsed_jd=parsed_jd,
            subject=email_data["subject"],
            email_body=email_data["body"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Email generation failed: {str(e)}")
