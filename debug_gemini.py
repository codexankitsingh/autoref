import json
from services.ai_service import ai_service
try:
    print("Test JD Parse...")
    parsed = ai_service.parse_jd("test job at google for software engineer with python and java")
    print("Parsed:", parsed)
    print("Test Generate Email...")
    email = ai_service.generate_email(parsed, "My profile", target_role="Backend/SDE")
    print("Generated:", email)
except Exception as e:
    print("Error:", e)
