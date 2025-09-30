# Minimal Flask + Gemini backend for GrantForgeUSA v1
from flask import Flask, jsonify, request
from flask_cors import CORS
import os

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

@app.get("/health")
def health():
    return jsonify(ok=True)

# ---------- AI Draft endpoint (Gemini only) ----------
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
    tester_name = data.get("tester_name","Tester")
    category = data.get("category","General")
    title = data.get("title","Untitled Project")
    summary = data.get("summary","")
    amount = data.get("amount",0)
    keywords = data.get("keywords","")
    opp_id = data.get("opp_id","")
    opp_title = data.get("opp_title","")

    if not GOOGLE_API_KEY:
        return jsonify(draft="ERROR: GOOGLE_API_KEY is not set on the server."), 200

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

    return jsonify(draft=text), 200