# GrantForgeUSA v1 — Live Grants.gov (RSS) search + Gemini drafting
# Works for ALL categories (Education, Small Business, City/Community, Faith-based/501c3, etc.)
from flask import Flask, jsonify, request
from flask_cors import CORS
import os, re, requests, html
import xml.etree.ElementTree as ET

# --------------------------------------------
# Flask
# --------------------------------------------
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

@app.get("/health")
def health():
    return jsonify(ok=True)

# --------------------------------------------
# Live Grants.gov (RSS)  — NO API KEY REQUIRED
# --------------------------------------------
# Official RSS feeds (public). We'll merge New + Modified by Category.
RSS_NEW_BY_CATEGORY = "https://www.grants.gov/rss/GG_NewOppByCategory.xml"
RSS_MOD_BY_CATEGORY = "https://www.grants.gov/rss/GG_OppModByCategory.xml"

HTTP_TIMEOUT = 25

_illegal_xml_ctrls = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")

# Replace bare '&' with '&amp;' unless it's already an entity like &amp; or &#123;
_unescaped_amp = re.compile(r"&(?!(amp;|lt;|gt;|quot;|apos;|#[0-9]+;))")

def _sanitize_xml_text(txt: str) -> str:
    if not txt:
        return ""
    # drop illegal control characters
    txt = _illegal_xml_ctrls.sub("", txt)
    # make sure & is safe for XML parsing
    txt = _unescaped_amp.sub("&amp;", txt)
    return txt

def _fetch_rss(url: str) -> str:
    r = requests.get(url, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    return r.text

def _parse_items(xml_text: str):
    # Some feeds contain bad entities / control chars; sanitize first.
    safe_xml = _sanitize_xml_text(xml_text)
    root = ET.fromstring(safe_xml)
    chan = root.find("./channel")
    if chan is None:
        return []
    items = []
    for it in chan.findall("item"):
        title = (it.findtext("title") or "").strip()
        link  = (it.findtext("link")  or "").strip()
        desc  = (it.findtext("description") or "").strip()
        pub   = (it.findtext("pubDate") or "").strip()
        cat   = (it.findtext("category") or "").strip()
        # derive a simple id from the URL
        opp_id = link.rsplit("/", 1)[-1] if "/" in link else link
        # clean up description to plain text
        clean_desc = re.sub("<.*?>", "", html.unescape(desc))
        items.append({
            "id": opp_id,
            "title": title,
            "link": link,
            "category": cat,
            "summary": clean_desc,
            "pubDate": pub
        })
    return items

def _keywords_for_category(category_hint: str) -> str:
    c = (category_hint or "").lower()
    if "educ" in c:
        return "school,education,K12,STEM,classroom,students"
    if "small" in c or "business" in c:
        return "small business,SBA,startup,entrepreneur,capital"
    if "city" in c or "community" in c or "municip" in c:
        return "city,community,infrastructure,parks,health"
    if "faith" in c or "church" in c:
        return "faith,church,nonprofit,community,education,youth"
    # default general
    return "community,nonprofit,education,workforce"

def _score(item, q_words, category_hint):
    score = 60  # baseline
    text = f"{item.get('title','')} {item.get('summary','')} {item.get('category','')}".lower()
    for w in q_words:
        w = (w or "").strip().lower()
        if not w: 
            continue
        if w in text:
            score += 8
    if category_hint and category_hint.lower() in text:
        score += 10
    # small boost if Grants.gov title contains "program" or "grant"
    if "program" in text or "grant" in text:
        score += 4
    return min(100, score)

@app.get("/opportunities")
def opportunities():
    """
    Returns live opportunities from Grants.gov RSS feeds (no API).
      q: keywords (comma/space separated). If empty, derived from category.
      category: string hint ('Education', 'Small Business', 'City/Community', 'Faith-based', etc.)
      limit: number of items to return (default 5)
      min_score: minimum score to include (default 70)
    """
    q = (request.args.get("q") or "").strip()
    category = (request.args.get("category") or "").strip()
    try:
        limit = int(request.args.get("limit", "5"))
    except ValueError:
        limit = 5
    try:
        min_score = int(request.args.get("min_score", "70"))
    except ValueError:
        min_score = 70

    if not q:
        q = _keywords_for_category(category)

    # Fetch feeds; if one fails, continue with the other
    items = []
    errors = []
    for url in (RSS_NEW_BY_CATEGORY, RSS_MOD_BY_CATEGORY):
        try:
            xml = _fetch_rss(url)
            items.extend(_parse_items(xml))
        except Exception as e:
            errors.append(f"{url}: {e}")

    if not items and errors:
        # total failure — return helpful message but still valid JSON
        return jsonify(error="; ".join(errors), items=[]), 200

    # score + dedupe + sort
    q_words = re.split(r"[,\s]+", q)
    seen = set()
    ranked = []
    for it in items:
        item_id = it.get("id") or it.get("link")
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        it["score"] = _score(it, q_words, category)
        if it["score"] >= min_score:
            ranked.append(it)

    ranked.sort(key=lambda x: x["score"], reverse=True)
    return jsonify(items=ranked[:limit], errors=errors), 200

# --------------------------------------------
# AI Draft (Gemini)
# --------------------------------------------
import google.generativeai as genai

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

# done