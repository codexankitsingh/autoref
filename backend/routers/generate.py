"""Router: Email Generation from JD."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from schemas import GenerateEmailRequest, GenerateEmailResponse, ParsedJD
from services.ai_service import ai_service
from models.user import User
from dependencies import get_approved_user

router = APIRouter(prefix="/api", tags=["generate"])


@router.post("/generate-email", response_model=GenerateEmailResponse)
def generate_email(
    request: GenerateEmailRequest,
    current_user: User = Depends(get_approved_user),
):
    """
    Parse a JD and generate a tailored referral email.
    Uses the current user's profile_text for personalization.
    """
    try:
        # Parse JD
        parsed = ai_service.parse_jd(request.jd_text, model_name=request.model)
        parsed_jd = ParsedJD(**parsed)

        # Use current user's profile for AI context
        user_profile = current_user.profile_text or ""

        # Generate email
        email_data = ai_service.generate_email(
            jd_data=parsed,
            user_profile=user_profile,
            model_name=request.model,
            target_role=request.target_role,
        )

        return GenerateEmailResponse(
            parsed_jd=parsed_jd,
            subject=email_data["subject"],
            email_body=email_data["body"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Email generation failed: {str(e)}")
