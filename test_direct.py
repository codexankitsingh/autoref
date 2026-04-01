import sys
import os
import traceback

sys.path.insert(0, os.path.abspath("backend"))

try:
    from config import get_settings
    settings = get_settings()
    from google import genai
    print("Key:", settings.gemini_api_key[:5])
    client = genai.Client(api_key=settings.gemini_api_key)
    res = client.models.generate_content(
        model="gemini-1.5-flash",
        contents="Say hello"
    )
    print("SUCCESS", res.text)
except Exception as e:
    print("FAIL EXCEPTION:", repr(e))
    traceback.print_exc()
