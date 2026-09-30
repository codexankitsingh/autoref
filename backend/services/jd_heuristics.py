"""Rule-based JD parsing when LLM is unavailable."""
import re


def parse_jd_heuristic(jd_text: str) -> dict:
    text = (jd_text or "").strip()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    role = None
    company = None
    location = None
    skills: list[str] = []

    for ln in lines[:12]:
        if not role:
            m = re.search(
                r"(?:job title|position|role)\s*[:\-]\s*(.+)",
                ln,
                re.I,
            )
            if m:
                role = m.group(1).strip()[:120]
        if not company:
            m = re.search(
                r"(?:company|employer|organization)\s*[:\-]\s*(.+)",
                ln,
                re.I,
            )
            if m:
                company = m.group(1).strip()[:120]

    if not role and lines:
        role = lines[0][:120]

    loc_match = re.search(
        r"(?:location|based in|work location)\s*[:\-]\s*(.+)",
        text,
        re.I,
    )
    if loc_match:
        location = loc_match.group(1).split("\n")[0].strip()[:120]

    skill_candidates = re.findall(
        r"\b(Python|SQL|PySpark|Spark|Airflow|Kafka|BigQuery|GCP|AWS|dbt|"
        r"Java|Scala|Docker|Kubernetes|ETL|ELT|Iceberg|Snowflake|Redshift|"
        r"PostgreSQL|MongoDB|Flink|Beam|Hadoop|Hive|Tableau|Looker)\b",
        text,
        re.I,
    )
    seen = set()
    for s in skill_candidates:
        key = s.lower()
        if key not in seen:
            seen.add(key)
            skills.append(s if s.isupper() else s.title())
        if len(skills) >= 8:
            break

    job_link = None
    link_match = re.search(r"https?://[^\s<>\"']+", text)
    if link_match:
        job_link = link_match.group(0)

    return {
        "company": company,
        "role": role,
        "skills": skills,
        "location": location,
        "job_id": None,
        "job_link": job_link,
    }
