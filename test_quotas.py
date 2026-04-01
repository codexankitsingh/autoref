import os
import sys

sys.path.insert(0, os.path.abspath("backend"))
from config import get_settings
from google import genai
from google.genai.errors import ClientError

def test_models():
    settings = get_settings()
    client = genai.Client(api_key=settings.gemini_api_key)
    
    models_to_test = [
        "gemini-2.5-flash-lite",
        "gemini-flash-latest",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite"
    ]
    
    results = []
    
    for model in models_to_test:
        try:
            res = client.models.generate_content(
                model=model,
                contents="test"
            )
            print(f"SUCCESS {model}: returned response.")
        except ClientError as e:
            # check if it's exhausted or not found
            msg = getattr(e, "message", str(e))
            if "limit:" in msg:
                limit = msg.split("limit: ")[1].split(",")[0]
                print(f"RATE_LIMITED {model}: Quota Limit {limit}")
            else:
                print(f"ERROR {model}: {msg}")
        except Exception as e:
            print(f"EXCEPTION {model}: {str(e)}")

if __name__ == "__main__":
    test_models()
