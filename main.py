# GrantForgeUSA v1 — Minimal Flask + Gemini + Live Grants.gov (RSS) search
from flask import Flask, jsonify, request
from flask_cors import CORS
import os, re, requests
import xml.etree.ElementTree as ET

# ------------ Flask App ------------
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

@app.get("/health")
def health():
    return jsonify(ok=True)

# ------------ LIVE OPPORTUNITIES (NO API KEY) ------------
# Grants.gov official RSS feeds (no auth needed)
RSS_NEW_BY_CATEGORY = "https://www.grants.gov/rss/GG_NewOppByCategory.xml"
RSS_MOD_BY_CATEGORY = "https://www.grants.gov/rss/GG_OppModByCategory.xml"

def _fetch_rss(url: str):
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return r.text

def _parse_items(xml_text: str):
    # parse <item> title/description/link/pubDate/category
    root = ET.fromstring(xml_text)
    chan = root.find("./channel")
    if chan is None: return []
    items = []
    for it in chan.findall("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        desc = (it.findtext("description") or "").strip()
        pub  = (it.findtext("pubDate") or "").strip()
        cat  = (it.findtext("category") or "").strip()
        # derive a simple id from the URL (last segment)
        opp_id = link.rsplit("/", 1)[-1] if "/" in link else link
        # strip HTML from description
        clean_desc = re.sub("<.*?>", "", desc)
        items.append({
            "id": opp_id,
            "title": title,
            "link": link,
            "category": cat,
            "summary": clean_desc,
            "pubDate": pub
        })
    return items

def _score(item, q_words, category_hint):
    score = 60  # baseline "relevant"
    text = f"{item['title']} {item['summary']} {item['category']}".lower()
    for w in q_words:
        if w and w.lower() in text:
            score += 8
    if category_hint and category_hint.lower() in text:
        score += 10
    return min(100, score)

@app.get("/opportunities")
def opportunities():
    """
    Query params:
      q: keywords (comma or space separated)
      category: hint like 'Education', 'Small Business', etc.
      limit: default 5
    """
    q = request.args.get("q", "") or ""
    category = request.args.get("category", "") or ""
    try:
        limit = int(request.args.get("limit", "5"))
    except ValueError:
        limit = 5

    # fetch both feeds, merge, score, dedupe by id
    items = []
    try:
        xml_new = _fetch_rss(RSS_NEW_BY_CATEGORY)
        xml_mod = _fetch_rss(RSS_MOD_BY_CATEGORY)
        items = _parse_items(xml_new) + _parse_items(xml_mod)
    except Exception as e:
        return jsonify(error=f"RSS error: {e}", items=[]), 200

    q_words = re.split(r"[,\s]+", q.strip())
    seen = set()
    ranked = []
    for it in items:
        if it["id"] in seen: 
            continue
        seen.add(it["id"])
        it["score"] = _score(it, q_words, category)
        ranked.append(it)

    ranked.sort(key=lambda x: x["score"], reverse=True)
    return jsonify(items=ranked[:limit]), 200

# ------------ AI Draft endpoint (Gemini) ------------
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
    category = data.get("category","General")
    title = data.get("title","Untitled Project")
    summary = data.get("summary","")
    amount = data.get("amount", 0)
    keywords = data.get("keywords","")
    opp_id = data.get("grant_id") or data.get("opp_id","")
    opp_title = data.get("opp_title") or data.get("opportunity_title") or data.get("title_hint","")

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
        "Board/leadership approval documented",
        "Eligibility confirmed & SAM.gov active",
        "Budget aligns with funder guidance",
        "Measurable outcomes defined",
        "Data collection plan in place",
    ]

    return jsonify(narrative=text, checklist=checklist), 200