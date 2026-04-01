import os
from services.ai_service import ai_service

def verify():
    print("Testing generate_email bypass...")
    try:
        res = ai_service.generate_email({
            "company": "Netflix",
            "role": "Backend Engineer",
            "skills": ["Python", "FastAPI"],
            "location": "Remote"
        }, "I am an experienced Python developer.")
        
        with open("verification_results.txt", "w") as f:
            f.write("SUBJECT: " + res.get("subject", "") + "\n")
            f.write("BODY:\n" + res.get("body", "") + "\n")
        print("Success! Check verification_results.txt")
    except Exception as e:
        import traceback
        with open("verification_results.txt", "w") as f:
            f.write("EXCEPTION: " + str(e) + "\n")
            traceback.print_exc(file=f)
        print("Failed! Check verification_results.txt")

if __name__ == "__main__":
    verify()
