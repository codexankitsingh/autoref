import requests

try:
    res = requests.post("http://localhost:8888/api/generate-email", json={
        "jd_text": "Looking for a Data Engineer with big data experience.",
        "recipient_email": "test@amazon.com",
        "recipient_name": "Bob"
    }, timeout=30)
    print("STATUS:", res.status_code)
    print("RESPONSE:", res.text)
except Exception as e:
    import traceback
    traceback.print_exc()
