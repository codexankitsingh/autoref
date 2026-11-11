#!/usr/bin/env python3
"""
Knowledge Transfer (KT) Page Creator for Ankit J Kumar
=======================================================
Run this script from within the Rakuten corporate network (or VPN).

Requirements:
    pip install requests

Usage:
    python3 kt_page_creator.py
"""

import json
import os
import sys
import time
import re
import html
from collections import defaultdict, Counter
from datetime import datetime

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ─── Configuration ───────────────────────────────────────────────────────────
# Set these environment variables before running:
#   export JIRA_PAT="<your Jira PAT>"
#   export CONFLUENCE_PAT="<your Confluence PAT>"
# Optionally override the base URLs:
#   export JIRA_BASE_URL="https://jira.rakuten-it.com/jira"
#   export CONFLUENCE_BASE_URL="https://confluence.rakuten-it.com/confluence"

JIRA_BASE      = os.environ.get("JIRA_BASE_URL",      "https://jira.rakuten-it.com/jira")
JIRA_PAT       = os.environ.get("JIRA_PAT",           "")   # set via env var

CONFLUENCE_BASE = os.environ.get("CONFLUENCE_BASE_URL", "https://confluence.rakuten-it.com/confluence")
CONFLUENCE_PAT  = os.environ.get("CONFLUENCE_PAT",      "")  # set via env var

JIRA_USER       = "ankit.j.kumar"
JIRA_EMAIL      = "ankit.j.kumar@rakuten.com"

PAGE_TITLE      = "Knowledge Transfer - Ankit J Kumar"
MAX_ISSUES      = 500       # hard cap across pagination
ISSUES_PER_PAGE = 100

# ─── HTTP session helpers ─────────────────────────────────────────────────────

def make_session(token: str) -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    })
    retry = Retry(total=3, backoff_factor=1,
                  status_forcelist=[429, 500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.verify = False          # skip SSL verify for corporate cert chains
    return session


def jira_get(session, path, params=None):
    url = f"{JIRA_BASE}{path}"
    r = session.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def confluence_get(session, path, params=None):
    url = f"{CONFLUENCE_BASE}{path}"
    r = session.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def confluence_post(session, path, payload):
    url = f"{CONFLUENCE_BASE}{path}"
    r = session.post(url, json=payload, timeout=60)
    r.raise_for_status()
    return r.json()

# ─── Step 1: Fetch Jira data ──────────────────────────────────────────────────

def fetch_user_info(session):
    print("► Fetching Jira user info …")
    try:
        return jira_get(session, "/rest/api/2/myself")
    except Exception as e:
        print(f"  ⚠ Could not fetch user info: {e}")
        return {"displayName": "Ankit J Kumar", "emailAddress": JIRA_EMAIL}


def search_issues(session, jql, max_results=MAX_ISSUES):
    """Paginate through a JQL search and return all issues."""
    all_issues = []
    start_at   = 0
    fields     = (
        "summary,description,status,priority,issuetype,project,"
        "components,labels,created,updated,resolutiondate,comment,"
        "assignee,reporter,fixVersions,customfield_10014"   # epic link
    )
    while True:
        remaining = max_results - len(all_issues)
        if remaining <= 0:
            break
        page_size = min(ISSUES_PER_PAGE, remaining)
        print(f"  Fetching issues {start_at}–{start_at + page_size - 1} …")
        try:
            data = jira_get(session, "/rest/api/2/search", params={
                "jql":        jql,
                "startAt":    start_at,
                "maxResults": page_size,
                "fields":     fields,
                "expand":     "names",
            })
        except Exception as e:
            print(f"  ⚠ Search error at offset {start_at}: {e}")
            break

        issues = data.get("issues", [])
        all_issues.extend(issues)
        total = data.get("total", 0)
        print(f"  Got {len(issues)} issues (total matching: {total})")
        if start_at + len(issues) >= total or len(issues) == 0:
            break
        start_at += len(issues)
        time.sleep(0.3)          # polite rate limit

    return all_issues


def fetch_all_issues(session):
    print("\n► Fetching assigned issues …")
    assigned = search_issues(session, f'assignee = "{JIRA_USER}" ORDER BY updated DESC')

    print("\n► Fetching reported issues …")
    reported = search_issues(
        session,
        f'reporter = "{JIRA_USER}" AND assignee != "{JIRA_USER}" ORDER BY updated DESC',
        max_results=200,
    )

    # De-duplicate by key
    seen   = set()
    merged = []
    for issue in assigned + reported:
        key = issue["key"]
        if key not in seen:
            seen.add(key)
            merged.append(issue)

    print(f"\n  Total unique issues collected: {len(merged)}")
    return merged

# ─── Step 2: Analyse the data ─────────────────────────────────────────────────

def safe_str(obj, fallback="—"):
    if obj is None:
        return fallback
    if isinstance(obj, str):
        return obj.strip() or fallback
    return str(obj)


def parse_issues(issues):
    projects         = {}          # key → {name, count, statuses}
    issue_types      = Counter()
    statuses         = Counter()
    priorities       = Counter()
    components_all   = Counter()
    labels_all       = Counter()
    open_issues      = []
    notable_issues   = []
    tech_words       = Counter()
    timeline_months  = Counter()

    TECH_KEYWORDS = {
        # Languages
        "python", "java", "kotlin", "scala", "go", "golang", "javascript",
        "typescript", "ruby", "bash", "shell", "perl", "swift", "rust",
        # Frameworks / platforms
        "spring", "django", "flask", "react", "angular", "vue", "node",
        "nodejs", "fastapi", "grpc", "graphql", "rest", "soap", "kafka",
        "rabbitmq", "celery", "airflow", "spark", "hadoop", "flink",
        # Infra / cloud
        "kubernetes", "k8s", "docker", "helm", "terraform", "ansible",
        "aws", "gcp", "azure", "ec2", "s3", "lambda", "ecs", "eks",
        "cloudformation", "jenkins", "gitlab", "github", "circleci", "argocd",
        # DBs
        "mysql", "postgres", "postgresql", "mongodb", "redis", "elasticsearch",
        "dynamodb", "cassandra", "oracle", "sqlite", "bigquery", "redshift",
        "snowflake", "hive", "presto",
        # Observability
        "prometheus", "grafana", "datadog", "splunk", "kibana", "newrelic",
        "jaeger", "zipkin", "opentelemetry",
        # Misc protocols / patterns
        "oauth", "jwt", "saml", "ldap", "ssl", "tls", "api", "microservice",
        "monolith", "cdc", "event-driven", "ddd", "ci/cd", "cicd",
    }

    for issue in issues:
        f        = issue.get("fields", {})
        key      = issue["key"]
        proj_key = f.get("project", {}).get("key", "UNKNOWN")
        proj_name= f.get("project", {}).get("name", "Unknown Project")

        # Project aggregation
        if proj_key not in projects:
            projects[proj_key] = {"name": proj_name, "count": 0, "statuses": Counter()}
        projects[proj_key]["count"]  += 1

        # Type / status / priority
        itype    = safe_str(f.get("issuetype", {}).get("name"))
        status   = safe_str(f.get("status",    {}).get("name"))
        priority = safe_str(f.get("priority",  {}).get("name"))
        issue_types[itype]  += 1
        statuses[status]    += 1
        priorities[priority]+= 1
        projects[proj_key]["statuses"][status] += 1

        # Components & labels
        for c in f.get("components", []):
            components_all[safe_str(c.get("name"))] += 1
        for lbl in f.get("labels", []):
            labels_all[lbl] += 1

        # Open issues
        closed_statuses = {"done", "closed", "resolved", "cancelled", "rejected",
                           "won't fix", "duplicate"}
        if status.lower() not in closed_statuses:
            open_issues.append(issue)

        # Notable: High/Highest priority, or has many comments
        comment_count = len(f.get("comment", {}).get("comments", []))
        if priority.lower() in {"high", "highest", "critical", "blocker"} or comment_count >= 5:
            notable_issues.append(issue)

        # Tech keyword extraction from summary + description + comments
        text_blob = " ".join([
            safe_str(f.get("summary")),
            safe_str(f.get("description")),
        ])
        for c in f.get("comment", {}).get("comments", []):
            body = c.get("body", "")
            if body:
                text_blob += " " + body

        words = re.findall(r'[a-z][a-z0-9\-/]+', text_blob.lower())
        for w in words:
            if w in TECH_KEYWORDS:
                tech_words[w] += 1

        # Timeline
        created = f.get("created", "")
        if created:
            try:
                month = created[:7]   # "YYYY-MM"
                timeline_months[month] += 1
            except Exception:
                pass

    return {
        "projects":        projects,
        "issue_types":     issue_types,
        "statuses":        statuses,
        "priorities":      priorities,
        "components":      components_all,
        "labels":          labels_all,
        "open_issues":     open_issues,
        "notable_issues":  list({i["key"]: i for i in notable_issues}.values()),
        "tech_words":      tech_words,
        "timeline":        timeline_months,
    }

# ─── Step 3: Build Confluence page body ──────────────────────────────────────

def esc(s):
    """HTML-escape a plain-text string for use in Confluence storage format."""
    return html.escape(str(s), quote=True)


def status_color(status_name: str) -> str:
    s = status_name.lower()
    if "done" in s or "closed" in s or "resolved" in s:
        return "Green"
    if "progress" in s or "review" in s or "testing" in s:
        return "Blue"
    if "blocked" in s or "impediment" in s:
        return "Red"
    return "Yellow"


def build_page_body(user_info, issues, analysis, jira_base):
    name         = user_info.get("displayName", "Ankit J Kumar")
    email        = user_info.get("emailAddress", JIRA_EMAIL)
    now          = datetime.utcnow().strftime("%d %b %Y %H:%M UTC")
    total        = len(issues)
    projects     = analysis["projects"]
    open_issues  = analysis["open_issues"]
    notable      = analysis["notable_issues"]
    tech_words   = analysis["tech_words"]
    components   = analysis["components"]
    labels       = analysis["labels"]
    issue_types  = analysis["issue_types"]
    statuses     = analysis["statuses"]
    timeline     = analysis["timeline"]

    # Sort months for timeline summary
    sorted_months = sorted(timeline.keys())
    first_month   = sorted_months[0]  if sorted_months else "N/A"
    last_month    = sorted_months[-1] if sorted_months else "N/A"

    # Top technologies
    top_tech = [t for t, _ in tech_words.most_common(20)]

    # ── Helper: colour status macro ──────────────────────────────────────────
    def status_macro(text, color="Yellow"):
        return (
            f'<ac:structured-macro ac:name="status">'
            f'<ac:parameter ac:name="colour">{color}</ac:parameter>'
            f'<ac:parameter ac:name="title">{esc(text)}</ac:parameter>'
            f'</ac:structured-macro>'
        )

    def panel(title, body, panel_type="info"):
        return (
            f'<ac:structured-macro ac:name="{panel_type}">'
            f'<ac:parameter ac:name="title">{esc(title)}</ac:parameter>'
            f'<ac:rich-text-body>{body}</ac:rich-text-body>'
            f'</ac:structured-macro>'
        )

    # ── Section 1: Overview ───────────────────────────────────────────────────
    proj_count  = len(projects)
    open_count  = len(open_issues)
    closed_count= total - open_count

    overview_table = (
        "<table><tbody>"
        f"<tr><th>Field</th><th>Details</th></tr>"
        f"<tr><td><strong>Name</strong></td><td>{esc(name)}</td></tr>"
        f"<tr><td><strong>Email</strong></td><td>{esc(email)}</td></tr>"
        f"<tr><td><strong>Total Jira tickets</strong></td><td>{total}</td></tr>"
        f"<tr><td><strong>Projects touched</strong></td><td>{proj_count}</td></tr>"
        f"<tr><td><strong>Open / in-progress tickets</strong></td><td>{open_count}</td></tr>"
        f"<tr><td><strong>Resolved / closed tickets</strong></td><td>{closed_count}</td></tr>"
        f"<tr><td><strong>Activity window</strong></td><td>{esc(first_month)} → {esc(last_month)}</td></tr>"
        f"<tr><td><strong>KT page generated</strong></td><td>{esc(now)}</td></tr>"
        "</tbody></table>"
    )

    issue_type_rows = "".join(
        f"<tr><td>{esc(k)}</td><td>{v}</td></tr>"
        for k, v in issue_types.most_common()
    )
    status_rows = "".join(
        f"<tr><td>{status_macro(k, status_color(k))}</td><td>{v}</td></tr>"
        for k, v in statuses.most_common()
    )

    section1 = (
        "<h1>1. Overview</h1>"
        + panel(
            "About this page",
            "<p>This Knowledge Transfer document was auto-generated from Jira data. "
            "It captures the breadth of work done by "
            + esc(name)
            + " and is intended to help onboard a successor or distribute ownership.</p>",
        )
        + overview_table
        + "<h3>Work breakdown by issue type</h3>"
        "<table><tbody>"
        "<tr><th>Issue type</th><th>Count</th></tr>"
        + issue_type_rows
        + "</tbody></table>"
        "<h3>Status distribution</h3>"
        "<table><tbody>"
        "<tr><th>Status</th><th>Count</th></tr>"
        + status_rows
        + "</tbody></table>"
    )

    # ── Section 2: Projects ───────────────────────────────────────────────────
    proj_rows = ""
    for pkey, pdata in sorted(projects.items(), key=lambda x: -x[1]["count"]):
        top_statuses = ", ".join(
            f"{s} ({c})" for s, c in pdata["statuses"].most_common(3)
        )
        jira_link = (
            f'<a href="{jira_base}/issues?jql=project%3D{esc(pkey)}'
            f'+AND+assignee%3D%22{esc(JIRA_USER)}%22">{esc(pkey)}</a>'
        )
        proj_rows += (
            f"<tr>"
            f"<td>{jira_link}</td>"
            f"<td>{esc(pdata['name'])}</td>"
            f"<td>{pdata['count']}</td>"
            f"<td>{esc(top_statuses)}</td>"
            f"</tr>"
        )

    section2 = (
        "<h1>2. Projects &amp; Systems Worked On</h1>"
        "<table><tbody>"
        "<tr><th>Project key</th><th>Project name</th><th>Ticket count</th><th>Status distribution</th></tr>"
        + proj_rows
        + "</tbody></table>"
    )

    # ── Section 3: Technical expertise ───────────────────────────────────────
    comp_rows = "".join(
        f"<tr><td>{esc(c)}</td><td>{n}</td></tr>"
        for c, n in components.most_common(30)
    ) if components else "<tr><td colspan='2'><em>No component data extracted</em></td></tr>"

    label_rows = "".join(
        f"<tr><td><code>{esc(l)}</code></td><td>{n}</td></tr>"
        for l, n in labels.most_common(30)
    ) if labels else "<tr><td colspan='2'><em>No label data extracted</em></td></tr>"

    tech_list = "".join(
        f"<li><strong>{esc(t)}</strong> (mentioned {tech_words[t]}×)</li>"
        for t in top_tech
    ) if top_tech else "<li><em>No specific technologies detected from text</em></li>"

    section3 = (
        "<h1>3. Technical Areas of Expertise</h1>"
        + panel(
            "How this was derived",
            "<p>Technology keywords were extracted from ticket summaries, descriptions, "
            "and comments. Components come from Jira component assignments.</p>",
            "note",
        )
        + "<h3>Jira components (most active)</h3>"
        "<table><tbody>"
        "<tr><th>Component</th><th>Tickets</th></tr>"
        + comp_rows
        + "</tbody></table>"
        "<h3>Jira labels (most used)</h3>"
        "<table><tbody>"
        "<tr><th>Label</th><th>Tickets</th></tr>"
        + label_rows
        + "</tbody></table>"
        "<h3>Technologies detected in ticket text</h3>"
        f"<ul>{tech_list}</ul>"
    )

    # ── Section 4: Work approach ──────────────────────────────────────────────
    # Derive patterns from the most-commented notable tickets
    approach_items = ""
    pattern_tickets = sorted(
        issues,
        key=lambda i: len(i.get("fields", {}).get("comment", {}).get("comments", [])),
        reverse=True,
    )[:5]

    for issue in pattern_tickets:
        f        = issue.get("fields", {})
        key      = issue["key"]
        summary  = safe_str(f.get("summary"))
        comments = f.get("comment", {}).get("comments", [])
        n_cmt    = len(comments)
        # Include the first ~300 chars of the most-recent comment as a snippet
        snippet  = ""
        if comments:
            body = comments[-1].get("body", "")
            snippet = body[:300].replace("<", "&lt;").replace(">", "&gt;")
            if len(body) > 300:
                snippet += " …"
        approach_items += (
            f"<li>"
            f'<strong><a href="{jira_base}/browse/{esc(key)}">{esc(key)}</a></strong>: '
            f"{esc(summary)} — <em>{n_cmt} comments</em>"
            + (f"<br/><blockquote>{snippet}</blockquote>" if snippet else "")
            + "</li>"
        )

    section4 = (
        "<h1>4. Work Approach &amp; Patterns</h1>"
        + panel(
            "Note",
            "<p>Patterns are inferred from tickets with the highest engagement (most comments). "
            "These represent areas where thorough discussion and iteration were needed.</p>",
            "note",
        )
        + "<ul>"
        + (approach_items or "<li><em>Insufficient comment data to derive patterns.</em></li>")
        + "</ul>"
    )

    # ── Section 5: Notable / key contributions ────────────────────────────────
    notable_rows = ""
    for issue in notable[:30]:
        f        = issue.get("fields", {})
        key      = issue["key"]
        summary  = esc(safe_str(f.get("summary")))
        status   = safe_str(f.get("status", {}).get("name"))
        priority = safe_str(f.get("priority", {}).get("name"))
        proj     = safe_str(f.get("project", {}).get("key"))
        n_cmt    = len(f.get("comment", {}).get("comments", []))
        notable_rows += (
            f"<tr>"
            f'<td><a href="{jira_base}/browse/{esc(key)}">{esc(key)}</a></td>'
            f"<td>{summary}</td>"
            f"<td>{esc(proj)}</td>"
            f"<td>{status_macro(status, status_color(status))}</td>"
            f"<td>{esc(priority)}</td>"
            f"<td>{n_cmt}</td>"
            f"</tr>"
        )

    section5 = (
        "<h1>5. Key Contributions &amp; Notable Work</h1>"
        + panel(
            "Selection criteria",
            "<p>Tickets listed here are High/Highest/Critical priority "
            "or have 5+ comments indicating significant collaboration.</p>",
        )
        + (
            "<table><tbody>"
            "<tr><th>Key</th><th>Summary</th><th>Project</th><th>Status</th>"
            "<th>Priority</th><th>Comments</th></tr>"
            + notable_rows
            + "</tbody></table>"
            if notable_rows
            else "<p><em>No issues met the notable threshold.</em></p>"
        )
    )

    # ── Section 6: Open / In-Progress work ───────────────────────────────────
    open_rows = ""
    for issue in open_issues[:50]:
        f        = issue.get("fields", {})
        key      = issue["key"]
        summary  = esc(safe_str(f.get("summary")))
        status   = safe_str(f.get("status", {}).get("name"))
        priority = safe_str(f.get("priority", {}).get("name"))
        proj     = safe_str(f.get("project", {}).get("key"))
        updated  = safe_str(f.get("updated", ""))[:10]
        open_rows += (
            f"<tr>"
            f'<td><a href="{jira_base}/browse/{esc(key)}">{esc(key)}</a></td>'
            f"<td>{summary}</td>"
            f"<td>{esc(proj)}</td>"
            f"<td>{status_macro(status, status_color(status))}</td>"
            f"<td>{esc(priority)}</td>"
            f"<td>{esc(updated)}</td>"
            f"</tr>"
        )

    section6 = (
        "<h1>6. Ongoing / In-Progress Work</h1>"
        + panel(
            "Handover note",
            "<p>These tickets are currently open and will need to be assigned or handed over. "
            "Discuss each item with the successor to clarify context and next steps.</p>",
            "warning",
        )
        + (
            "<table><tbody>"
            "<tr><th>Key</th><th>Summary</th><th>Project</th><th>Status</th>"
            "<th>Priority</th><th>Last updated</th></tr>"
            + open_rows
            + "</tbody></table>"
            if open_rows
            else "<p><em>No open tickets found — all work is resolved.</em></p>"
        )
    )

    # ── Section 7: Tools & Technologies ──────────────────────────────────────
    tech_table_rows = "".join(
        f"<tr><td><strong>{esc(t)}</strong></td><td>{tech_words[t]}</td>"
        f"<td>{_tech_category(t)}</td></tr>"
        for t in top_tech
    ) if top_tech else "<tr><td colspan='3'><em>N/A</em></td></tr>"

    section7 = (
        "<h1>7. Tools &amp; Technologies</h1>"
        "<table><tbody>"
        "<tr><th>Technology</th><th>Mention frequency</th><th>Category</th></tr>"
        + tech_table_rows
        + "</tbody></table>"
    )

    # ── Section 8: Ticket summary per project ────────────────────────────────
    issues_by_project = defaultdict(list)
    for issue in issues:
        pkey = issue.get("fields", {}).get("project", {}).get("key", "UNKNOWN")
        issues_by_project[pkey].append(issue)

    section8_parts = ["<h1>8. Ticket Summary by Project</h1>"]
    for pkey in sorted(issues_by_project.keys(), key=lambda k: -projects.get(k, {}).get("count", 0)):
        pname = projects.get(pkey, {}).get("name", pkey)
        section8_parts.append(f"<h2>{esc(pkey)} — {esc(pname)}</h2>")
        section8_parts.append(
            "<table><tbody>"
            "<tr><th>Key</th><th>Summary</th><th>Type</th><th>Status</th><th>Priority</th><th>Updated</th></tr>"
        )
        for issue in sorted(
            issues_by_project[pkey],
            key=lambda i: i.get("fields", {}).get("updated", ""),
            reverse=True,
        )[:50]:  # cap per project
            f        = issue.get("fields", {})
            key      = issue["key"]
            summary  = esc(safe_str(f.get("summary")))
            itype    = safe_str(f.get("issuetype", {}).get("name"))
            status   = safe_str(f.get("status", {}).get("name"))
            priority = safe_str(f.get("priority", {}).get("name"))
            updated  = safe_str(f.get("updated", ""))[:10]
            section8_parts.append(
                f"<tr>"
                f'<td><a href="{jira_base}/browse/{esc(key)}">{esc(key)}</a></td>'
                f"<td>{summary}</td>"
                f"<td>{esc(itype)}</td>"
                f"<td>{status_macro(status, status_color(status))}</td>"
                f"<td>{esc(priority)}</td>"
                f"<td>{esc(updated)}</td>"
                f"</tr>"
            )
        section8_parts.append("</tbody></table>")

    section8 = "".join(section8_parts)

    return "\n".join([section1, section2, section3, section4,
                      section5, section6, section7, section8])


def _tech_category(t):
    CATS = {
        "Language":      {"python","java","kotlin","scala","go","golang","javascript",
                          "typescript","ruby","bash","shell","perl","swift","rust"},
        "Framework":     {"spring","django","flask","react","angular","vue","node",
                          "nodejs","fastapi","grpc","graphql"},
        "Messaging":     {"kafka","rabbitmq","celery"},
        "Data/ML":       {"airflow","spark","hadoop","flink","bigquery","redshift",
                          "snowflake","hive","presto"},
        "Cloud/Infra":   {"kubernetes","k8s","docker","helm","terraform","ansible",
                          "aws","gcp","azure","ec2","s3","lambda","ecs","eks",
                          "cloudformation","jenkins","gitlab","github","circleci","argocd"},
        "Database":      {"mysql","postgres","postgresql","mongodb","redis",
                          "elasticsearch","dynamodb","cassandra","oracle","sqlite"},
        "Observability": {"prometheus","grafana","datadog","splunk","kibana","newrelic",
                          "jaeger","zipkin","opentelemetry"},
        "Security":      {"oauth","jwt","saml","ldap","ssl","tls"},
        "Architecture":  {"api","microservice","monolith","cdc","event-driven","ddd",
                          "ci/cd","cicd","rest","soap"},
    }
    for cat, words in CATS.items():
        if t in words:
            return cat
    return "Other"

# ─── Confluence space lookup ──────────────────────────────────────────────────

def find_personal_space(session):
    """Try several approaches to find Ankit's personal space key."""
    # Approach 1: well-known personal space key pattern
    for candidate_key in [
        f"~{JIRA_USER}",
        f"~{JIRA_USER.replace('.', '')}",
        f"~{JIRA_EMAIL}",
        "~ankit.j.kumar",
    ]:
        try:
            data = confluence_get(session, f"/rest/api/space/{candidate_key}")
            print(f"  ✔ Found personal space: {candidate_key}")
            return candidate_key
        except Exception:
            pass

    # Approach 2: enumerate personal spaces
    try:
        data = confluence_get(session, "/rest/api/space", params={
            "type": "personal", "limit": 100
        })
        for space in data.get("results", []):
            key   = space.get("key", "")
            name  = space.get("name", "").lower()
            if "ankit" in name or JIRA_USER in key.lower():
                print(f"  ✔ Found personal space via list: {key}")
                return key
    except Exception as e:
        print(f"  ⚠ Could not enumerate personal spaces: {e}")

    raise RuntimeError(
        f"Could not locate Ankit's personal Confluence space. "
        f"Please create it manually or provide the correct space key."
    )


def get_parent_page_id(session, space_key):
    """Return the numeric ID of the space's root page (to use as parent)."""
    try:
        data = confluence_get(session, "/rest/api/content", params={
            "type":     "page",
            "spaceKey": space_key,
            "title":    space_key.lstrip("~"),   # personal space root often named by username
            "expand":   "ancestors",
        })
        results = data.get("results", [])
        if results:
            return results[0]["id"]
    except Exception:
        pass

    # Fall back: get the space's homepage id
    try:
        data = confluence_get(session, f"/rest/api/space/{space_key}", params={"expand": "homepage"})
        return data.get("homepage", {}).get("id")
    except Exception:
        pass

    return None

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    import urllib3
    urllib3.disable_warnings()    # suppress InsecureRequestWarning

    if not JIRA_PAT:
        print("ERROR: JIRA_PAT environment variable is not set.")
        print("  export JIRA_PAT='<your Jira personal access token>'")
        sys.exit(1)
    if not CONFLUENCE_PAT:
        print("ERROR: CONFLUENCE_PAT environment variable is not set.")
        print("  export CONFLUENCE_PAT='<your Confluence personal access token>'")
        sys.exit(1)

    print("=" * 60)
    print("  KT Page Creator — Ankit J Kumar")
    print("=" * 60)

    jira_session = make_session(JIRA_PAT)
    conf_session = make_session(CONFLUENCE_PAT)

    # Step 1: Fetch data
    user_info = fetch_user_info(jira_session)
    issues    = fetch_all_issues(jira_session)

    if not issues:
        print("\n⚠ No issues found — check that the PAT is valid and the user exists.")
        sys.exit(1)

    # Step 2: Analyse
    print("\n► Analysing data …")
    analysis = parse_issues(issues)
    print(f"  Projects: {len(analysis['projects'])}")
    print(f"  Open tickets: {len(analysis['open_issues'])}")
    print(f"  Notable tickets: {len(analysis['notable_issues'])}")
    print(f"  Top technologies: {list(analysis['tech_words'].most_common(5))}")

    # Save raw data for debugging
    with open("jira_issues_raw.json", "w") as fh:
        json.dump(issues, fh, indent=2, default=str)
    print("  Raw issue data saved to jira_issues_raw.json")

    # Step 3: Build page & publish
    print("\n► Building Confluence page body …")
    body = build_page_body(user_info, issues, analysis, JIRA_BASE)

    print("► Finding Ankit's personal Confluence space …")
    space_key = find_personal_space(conf_session)
    parent_id = get_parent_page_id(conf_session, space_key)

    page_payload = {
        "type":  "page",
        "title": PAGE_TITLE,
        "space": {"key": space_key},
        "body": {
            "storage": {
                "value":          body,
                "representation": "storage",
            }
        },
    }
    if parent_id:
        page_payload["ancestors"] = [{"id": parent_id}]

    print(f"► Creating page '{PAGE_TITLE}' in space {space_key} …")
    try:
        result = confluence_post(conf_session, "/rest/api/content", page_payload)
    except requests.HTTPError as e:
        # If page already exists, update it
        if e.response is not None and e.response.status_code == 400:
            err_body = e.response.text
            if "title" in err_body.lower() and "already" in err_body.lower():
                print("  Page already exists — fetching its ID to update …")
                search = confluence_get(conf_session, "/rest/api/content", params={
                    "type":     "page",
                    "spaceKey": space_key,
                    "title":    PAGE_TITLE,
                    "expand":   "version",
                })
                existing  = search["results"][0]
                page_id   = existing["id"]
                version   = existing["version"]["number"] + 1
                page_payload["version"] = {"number": version}
                url = f"/rest/api/content/{page_id}"
                r   = conf_session.put(
                    f"{CONFLUENCE_BASE}{url}",
                    json=page_payload,
                    timeout=60,
                )
                r.raise_for_status()
                result = r.json()
            else:
                raise
        else:
            raise

    page_id  = result["id"]
    page_url = (
        result.get("_links", {}).get("base", CONFLUENCE_BASE)
        + result.get("_links", {}).get("webui", f"/pages/viewpage.action?pageId={page_id}")
    )

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  ✅ KT Page created successfully!")
    print("=" * 60)
    print(f"  Page URL  : {page_url}")
    print(f"  Page ID   : {page_id}")
    print(f"  Space key : {space_key}")
    print()
    print("  Summary:")
    print(f"    Total tickets processed : {len(issues)}")
    print(f"    Projects covered        : {len(analysis['projects'])}")
    proj_list = ", ".join(sorted(analysis["projects"].keys()))
    print(f"    Project keys            : {proj_list}")
    print(f"    Open tickets            : {len(analysis['open_issues'])}")
    print(f"    Notable tickets         : {len(analysis['notable_issues'])}")
    print(f"    Top technologies        : {', '.join(t for t,_ in analysis['tech_words'].most_common(8))}")
    print("=" * 60)

    return page_url


if __name__ == "__main__":
    main()
