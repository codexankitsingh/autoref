import json
from services.ai_service import ai_service
from database import SessionLocal
from models.user import User

db = SessionLocal()
user = db.query(User).first()
user_profile = user.profile_text if user else ""
db.close()

jd_text = """
Riverbed, the leader in AI observability... (see previous JD)
Position
As a Graduate Software Engineering Intern in the SteelHead Mobile team, you will work on enterprise-grade systems and networking software used by global customers. This role is designed for recent college graduates who want strong hands-on experience in C/C++, systems programming, and networking, with a clear path toward full-time engineering roles.
What You Will Do
Contribute to development, testing, and debugging of SteelHead Mobile features.
Work on system-level and networking-focused code.
What Makes You An Ideal Candidate
Recent BE / BTech graduate in Computer Science, Computer Engineering, or related discipline
Strong fundamentals in C++/Python programming.
Good understanding of Operating Systems, Data Structures, and Computer Networks.
Networking fundamentals (TCP/IP, latency, bandwidth).
Exposure to system-level or performance-oriented programming.
"""

parsed = ai_service.parse_jd(jd_text)
email = ai_service.generate_email(parsed, user_profile, target_role="Systems")
print("SUBJECT:", email["subject"])
print("BODY:\\n", email["body"])
