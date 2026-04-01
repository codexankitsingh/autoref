import sys
import os
import traceback

sys.path.insert(0, os.path.abspath("backend"))

try:
    from services.ai_service import ai_service
    from config import get_settings

    settings = get_settings()
    print("API Key loaded:", settings.gemini_api_key[-4:])
    
    print("Testing generate_email...")
    result = ai_service.generate_email({"company": "Amazon", "role": "SDE1", "skills": ["Python"]}, "My profile")
    print("RESULT:", result)
except Exception as e:
    print("FATAL ERROR:")
    traceback.print_exc()

