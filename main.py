# GrantForgeUSA v1 — Live Grants.gov (RSS, lenient) + Gemini drafts
from flask import Flask, jsonify, request
from flask_cors import CORS
import os, re, requests, html
import xml.etree.ElementTree as ET
import google.generativeai as genai

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

@app.get("/health")
def health():
    return jsonify(ok=True)

# ----------------------- RSS (no key) -----------------------
RSS_NEW_BY_CATEGORY = "https://www.grants.gov/rss/GG_NewOppByCategory.xml"
RSS_MOD_BY_CATEGORY = "https://www.grants.gov/rss/GG_OppModByCategory.xml"
HTTP_TIMEOUT = 25

_illegal_ctrls = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")
_unescaped_amp = re.compile(r"&(?!(amp;|lt;|gt;|quot;|apos;|#[0-9]+;))", re.I)
_strip_tags = re.compile(r"<.*?>", re.S)

def _sanitize_xml(s: str) -> str:
    if not s: return ""
    s = _illegal_ctrls.sub("", s)
    s = _unescaped_amp.sub("&amp;", s)
    return s

def _fetch_text(url: str) -> str:
    r = requests.get(url, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    # ignore undecodable bytes that break XML
    return r.content.decode("utf-8", errors="ignore")

def _parse_items_strict(xml_text: str):
    safe = _sanitize_xml(xml_text)
    root = ET.fromstring(safe)
    chan = root.find("./channel")
    if chan is None: return []
    items = []
    for it in chan.findall("item"):
        title = (it.findtext("title") or "").strip()
        link  = (it.findtext("link") or "").strip()
        desc  = (it.findtext("description") or "").strip()
        pub   = (it.findtext("pubDate") or "").strip()
        cat   = (it.findtext("category") or "").strip()
        opp_id = link.rsplit("/", 1)[-1] if "/" in link else link
        clean_desc = _strip_tags.sub("", html.unescape(desc)).strip()
        items.append({
            "id": opp_id, "title": title, "link": link,
            "category": cat, "summary": clean_desc, "pubDate": pub
        })
    return items

# Fallback: lenient regex parser if XML is malformed
_item_block = re.compile(r"<item\b[^>]*>(.*?)</item>", re.S|re.I)
def _grab(tag, s):
    m = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", s, re.S|re.I)
    return html.unescape(m.group(1).strip()) if m else ""

def _parse_items_lenient(xml_text: str):
    items = []
    for block in _item_block.findall(xml_text or ""):
        title = _grab("title", block)
        link  = _grab("link", block)
        desc  = _grab("description", block)
        pub   = _grab("pubDate", block)
        cat   = _grab("category", block)
        opp_id = link.rsplit("/", 1)[-1] if "/" in link else link
        clean_desc = _strip_tags.sub("", desc).strip()
        if title or link:
            items.append({
                "id": opp_id, "title": title, "link": link,
                "category": cat, "summary": clean_desc, "pubDate": pub
            })
    return items

def _fetch_and_parse(url: str):
    txt = _fetch_text(url)
    # try strict first
    try:
        return _parse_items_strict(txt)
    except Exception:
        # then lenient
        return _parse_items_lenient(txt)

def _keywords_for_category(cat: str) -> str:
    c = (cat or "").lower()
    if "educ" in c: return "school,education,K12,STEM,classroom,students"
    if "small" in c or "business" in c: return "small business,SBA,startup,entrepreneur,capital"
    if "city" in c or "community" in c or "municip" in c: return "city,community,infrastructure,parks,health"
    if "faith" in c or "church" in c: return "faith,church,nonprofit,community,education,youth"
    return "community,nonprofit,education,workforce"

def _score(item, q_words, category_hint):
    score = 60
    text = f"{item.get('title','')} {item.get('summary','')} {item.get('category','')}".lower()
    for w in q_words:
        w = (w or "").strip().lower()
        if w and w in text: score += 8
    if category_hint and category_hint.lower() in text: score += 10
    if "program" in text or "grant" in text: score += 4
    return min(100, score)

@app.get("/opportunities")
def opportunities():
    q = (request.args.get("q") or "").strip()
    category = (request.args.get("category") or "").strip()
    try: limit = int(request.args.get("limit", "5"))
    except: limit = 5
    try: min_score = int(request.args.get("min_score", "70"))
    except: min_score = 70
    if not q: q = _keywords_for_category(category)

    items, errors = [], []
    for url in (RSS_NEW_BY_CATEGORY, RSS_MOD_BY_CATEGORY):
        try:
            items.extend(_fetch_and_parse(url))
        except Exception as e:
            errors.append(f"{url}: {e}")

    if not items and errors:
        return jsonify(error="; ".join(errors), items=[]), 200

    q_words = re.split(r"[,\s]+", q)
    seen, ranked = set(), []
    for it in items:
        iid = it.get("id") or it.get("link")
        if not iid or iid in seen: continue
        seen.add(iid)
        it["score"] = _score(it, q_words, category)
        if it["score"] >= min_score:
            ranked.append(it)

    ranked.sort(key=lambda x: x["score"], reverse=True)
    return jsonify(items=ranked[:limit], errors=errors), 200

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