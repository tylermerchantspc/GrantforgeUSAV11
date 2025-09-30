# GrantForgeUSA v1 — Path B: Live Grants.gov search (JSON API w/ HTML fallback) + Gemini drafts
from flask import Flask, jsonify, request
from flask_cors import CORS
import os, re, html, json, requests
import google.generativeai as genai

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

@app.get("/health")
def health():
    return jsonify(ok=True)

HTTP_TIMEOUT = 25

# ----------------------- Helpers -----------------------
def _keywords_for_category(cat: str) -> str:
    c = (cat or "").lower()
    if "educ" in c: return "school education STEM classroom students teacher k12"
    if "small" in c or "business" in c: return "small business SBA startup entrepreneur capital"
    if "city" in c or "community" in c or "municip" in c: return "city community infrastructure parks health"
    if "faith" in c or "church" in c: return "faith church nonprofit community education youth"
    return "community nonprofit education workforce"

def _score(item, q_words, category_hint):
    score = 60
    text = f"{item.get('title','')} {item.get('summary','')} {item.get('category','')}".lower()
    for w in q_words:
        w = (w or "").strip().lower()
        if w and w in text: score += 8
    if category_hint and category_hint.lower() in text: score += 10
    if "program" in text or "grant" in text: score += 4
    return min(100, score)

# ----------------------- Primary source: Grants.gov JSON Search -----------------------
# NOTE: This endpoint is publicly reachable for keyword queries in many environments.
# If it ever changes or rate-limits, the code falls back to HTML scraping.

API_URL = "https://www.grants.gov/grantsws/rest/opportunities/search"

def _search_grants_api(q: str, max_records: int = 25):
    params = {
        "keyword": q,
        "oppStatuses": "OPEN",
        "sortBy": "openDate|desc",
        "startRecordNum": 1,
        "maxRecords": max_records,
    }
    r = requests.get(API_URL, params=params, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    hits = data.get("oppHits") or data.get("opportunities") or []
    items = []
    for h in hits:
        # Try common field names; ignore if missing
        opp_id = str(h.get("opportunityId") or h.get("id") or h.get("opportunityNumber") or "")
        title = (h.get("title") or h.get("opportunityTitle") or "").strip()
        link  = (h.get("unformattedOpportunityURL") or h.get("opportunityUrl") or h.get("url") or "")
        if not link and opp_id:
            link = f"https://www.grants.gov/search-results-detail/{opp_id}"
        summary = (h.get("synopsis") or h.get("summary") or h.get("description") or "").strip()
        cat = ", ".join(h.get("categories", []) or h.get("category", []) or []) if isinstance(h.get("categories"), list) else (h.get("category") or "")
        if title or link:
            items.append({
                "id": opp_id or link,
                "title": title,
                "link": link,
                "summary": summary,
                "category": cat
            })
    return items

# ----------------------- Fallback: HTML search scraping -----------------------
# If the JSON changes/blocks, scrape the public search page result cards.
SEARCH_URL = "https://www.grants.gov/search-grants"

# Basic patterns that are relatively stable:
_card = re.compile(r'<a[^>]+href="(/search-results-detail/\d+)"[^>]*>(.*?)</a>', re.I|re.S)
_strip_tags = re.compile(r"<.*?>", re.S)

def _search_grants_html(q: str, max_records: int = 25):
    r = requests.get(SEARCH_URL, params={"keyword": q}, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    html_text = r.text

    items = []
    for m in _card.finditer(html_text):
        href = m.group(1)
        title_html = m.group(2)
        title = _strip_tags.sub("", html.unescape(title_html)).strip()
        link = f"https://www.grants.gov{href}"
        opp_id = href.split("/")[-1]
        # Try to grab a bit of surrounding content for summary
        start = max(0, m.start() - 400)
        chunk = html_text[start:m.end()+400]
        # crude snippet
        snippet = _strip_tags.sub("", html.unescape(chunk))
        snippet = re.sub(r"\s+", " ", snippet).strip()
        snippet = snippet[:400] + ("…" if len(snippet) > 400 else "")
        items.append({
            "id": opp_id,
            "title": title,
            "link": link,
            "summary": snippet,
            "category": ""
        })
        if len(items) >= max_records:
            break
    return items

# ----------------------- Endpoint: /opportunities -----------------------
@app.get("/opportunities")
def opportunities():
    """
    Live Grants.gov search.
      q: keywords (space/comma separated). If empty, derived from category.
      category: hint to boost scoring
      limit: default 5
      min_score: default 70
    """
    q = (request.args.get("q") or "").strip()
    category = (request.args.get("category") or "").strip()
    try: limit = int(request.args.get("limit", "5"))
    except: limit = 5
    try: min_score = int(request.args.get("min_score", "70"))
    except: min_score = 70
    if not q: q = _keywords_for_category(category)

    items, errors = [], []
    # Try JSON API first
    try:
        items = _search_grants_api(q, max_records=max(25, limit*3))
    except Exception as e:
        errors.append(f"API search failed: {e}")

    # Fallback to HTML scraping if needed
    if not items:
        try:
            items = _search_grants_html(q, max_records=max(25, limit*3))
        except Exception as e:
            errors.append(f"HTML search failed: {e}")

    if not items:
        return jsonify(items=[], errors=errors), 200

    # Score + filter
    q_words = re.split(r"[,\s]+", q)
    for it in items:
        it["score"] = _score(it, q_words, category)
    items.sort(key=lambda x: x["score"], reverse=True)
    filtered = [it for it in items if it["score"] >= min_score][:limit]
    if not filtered:  # if filter too tight, return top N anyway
        filtered = items[:limit]
    return jsonify(items=filtered, errors=errors), 200

# ----------------------- /draft (Gemini) -----------------------
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
else:
    print("WARNING: GOOGLE_API_KEY is not set. /draft will return an error.")

PROMPT_TEMPLATE = """Create a first-draft grant narrative.

Applicant Category: {category}
Tester: {tester_name}
Project Title: {title}
Requested Amount (USD): {amount}
Keywords: {keywords}
Brief Summary: {summary}
Opportunity: {opp_id} - {opp_title}

Deliver sections:
1) Executive Summary
2) Statement of Need
3) Project Description & Activities
4) Objectives & Outcomes (measurable bullets)
5) Evaluation Plan
6) Organizational Capacity
7) Budget & Justification (bullets totaling ~ request)
8) Sustainability & Equity

700–1100 words. US spelling. No addresses or legal names.
"""

@app.post("/draft")
def draft():
    data = request.get_json(force=True) or {}
    tester_name = data.get("tester") or data.get("tester_name","Tester")
    category    = data.get("category","General")
    title       = data.get("title","Untitled Project")
    summary     = data.get("summary","")
    amount      = data.get("amount", 0)
    keywords    = data.get("keywords","")
    opp_id      = data.get("grant_id") or data.get("opp_id","")
    opp_title   = data.get("opp_title") or data.get("opportunity_title") or data.get("title_hint","")

    if not GOOGLE_API_KEY:
        return jsonify(narrative="ERROR: GOOGLE_API_KEY is not set on the server.",
                       checklist=[]), 200

    prompt = PROMPT_TEMPLATE.format(
        category=category, tester_name=tester_name, title=title,
        amount=amount, keywords=keywords, summary=summary,
        opp_id=opp_id, opp_title=opp_title
    )

    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        resp = model.generate_content(prompt)
        text = getattr(resp, "text", str(resp))
    except Exception as e:
        text = f"ERROR: {e}"

    checklist = [
        "Leadership approval recorded",
        "Eligibility confirmed & SAM.gov active",
        "Budget aligns with funder guidance",
        "Measurable outcomes defined",
        "Data collection & reporting plan in place",
    ]
    return jsonify(narrative=text, checklist=checklist), 200