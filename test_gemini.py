import os
import sys

# Setup paths to import from backend
sys.path.insert(0, os.path.abspath("backend"))

from services.ai_service import ai_service
from config import get_settings

settings = get_settings()
print(f"Testing with API Key: {settings.gemini_api_key[:5]}...{settings.gemini_api_key[-5:]}")

try:
    print("Sending test prompt to Gemini...")
    res = ai_service._call_gemini("Say 'hello' in exactly one word.")
    print("SUCCESS! Model responded with:", res)
except Exception as e:
    print("FAILED! Exception caught:")
    print(repr(e))
