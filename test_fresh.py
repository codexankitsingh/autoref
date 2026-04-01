import sys
import os

sys.path.insert(0, os.path.abspath("backend"))

try:
    from config import get_settings
    settings = get_settings()
    from google import genai
    client = genai.Client(api_key=settings.gemini_api_key)
    res = client.models.generate_content(
        model="gemini-2.5-flash",
        contents="Generate exactly one single word: Apple"
    )
    print("SUCCESS:", res.text)
except Exception as e:
    import traceback
    print("FAIL EXCEPTION:", repr(e))
    traceback.print_exc()
