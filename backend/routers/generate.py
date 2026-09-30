"""Router: Email Generation from JD."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from schemas import GenerateEmailRequest, GenerateEmailResponse, ParsedJD
from services.ai_service import ai_service
from services.email_quality import validate_outbound_email
from services.llm_client import LLMAccessDeniedError, LLMConfigurationError
from services.outreach_constants import normalize_target_role
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

        user_profile = current_user.profile_text or ""

        # Generate email
        target_role = normalize_target_role(
            request.target_role or current_user.default_target_role
        )

        email_data = ai_service.generate_email(
            jd_data=parsed,
            user_profile=user_profile,
            model_name=request.model,
            target_role=target_role,
            recipient_name=request.recipient_name,
        )

        issues = validate_outbound_email(email_data["subject"], email_data["body"])
        if issues:
            raise HTTPException(
                status_code=422,
                detail="Generated email failed quality checks: " + " ".join(issues),
            )

        return GenerateEmailResponse(
            parsed_jd=parsed_jd,
            subject=email_data["subject"],
            email_body=email_data["body"],
        )
    except LLMAccessDeniedError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except LLMConfigurationError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Email generation failed: {str(e)}")
