from services.ai_service import ai_service
try:
    print("Generating...")
    res = ai_service.generate_follow_up("test", 1)
    print("Success:")
    print(res)
except Exception as e:
    print(f"Error: {e}")
