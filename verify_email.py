import sys
import os
import json

sys.path.insert(0, os.path.abspath("backend"))

from services.ai_service import ai_service
from config import get_settings

try:
    print("Testing generate_email bypass using the new gemini SDK...")
    res = ai_service.generate_email({
        "company": "Google",
        "role": "Software Engineer",
        "skills": ["Python", "Machine Learning"],
        "location": "Remote"
    }, "I am an experienced Python developer with a strong ML background.")
    
    print("\n--- SUCCESS ---")
    print("SUBJECT:", res.get("subject"))
    print("BODY:\n", res.get("body"))
    
except Exception as e:
    print("FATAL EXCEPTION:")
    import traceback
    traceback.print_exc()
