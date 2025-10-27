# GrantforgeUSA — v11 backend (TEST MODE, end-to-end)
# Health, intake + shortlist with money-match, AI preview (guarded), Stripe test checkout,
# stable PDF generation and download endpoint, simple anti-fraud validations.

import os
import csv
import json
from datetime import datetime
from typing import List, Dict, Any

from flask import Flask, request, jsonify, send_file, abort
from flask_cors import CORS
from dotenv import load_dotenv

import stripe
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import pandas as pd

# ---------- Optional: AI + Firestore (guarded) ----------
AI_OK = False
FS_OK = False
try:
    import google.generativeai as genai
    from google.cloud import firestore
    AI_OK = True
    FS_OK = True
except Exception:
    genai = None
    firestore = None
    AI_OK = False
    FS_OK = False

# ---------- Bootstrap env ----------
load_dotenv()

# Frontend base for redirects
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://grantforge-usav-11.vercel.app").rstrip("/")

# Stripe (TEST)
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")

# Files/Storage
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", os.path.join(BASE_DIR, "out"))
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Local DB file
GRANTS_PATH = os.path.join(DATA_DIR, "grants.json")

# Logging
LOG_CSV = os.path.join(OUTPUT_DIR, "payments_log.csv")
MAP_CSV = os.path.join(OUTPUT_DIR, "session_map.csv")  # session_id -> order_id -> filename

# Pricing
PRICES = {
    "Teacher (Classroom)": 9.99,
    "School / District": 49.99,         # falls under "Small" tier if they use size selector later
    "Small Nonprofit / Club": 49.99,    # <= 500,000
    "Medium Nonprofit": 99.99,          # 500,001 - 2,000,000
    "Large Nonprofit / Municipality": 199.99,  # > 2,000,000
    "Church / Faith Org": 49.99,
    "Small Business": 49.99,
    "Other": 49.99,
}

# Anti-fraud / sanity caps (simple)
REQUEST_CAP = {
    "Teacher (Classroom)": 25000,
    "School / District": 250000,
    "Small Nonprofit / Club": 100000,
    "Medium Nonprofit": 500000,
    "Large Nonprofit / Municipality": 2000000,
    "Church / Faith Org": 100000,
    "Small Business": 100000,
    "Other": 50000,
}

# ---------- App ----------
app = Flask(__name__)

ALLOWED_ORIGINS = [
    FRONTEND_URL,
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
CORS(app, resources={r"/*": {"origins": ALLOWED_ORIGINS}}, supports_credentials=False)

# ---------- Helpers ----------
def cents(x: float) -> int:
    return int(round(float(x) * 100))

def load_grants() -> List[Dict[str, Any]]:
    if not os.path.exists(GRANTS_PATH):
        return []
    with open(GRANTS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def tokenize(s: str) -> List[str]:
    return [w.strip().lower() for w in (s or "").replace("/", " ").replace(",", " ").split() if w.strip()]

def score_fit(grant: Dict[str, Any], form: Dict[str, Any]) -> Dict[str, Any]:
    """
    Money-match + category + keywords scoring -> High / Medium / Low
    """
    # Money match
    req = float(form.get("amount_requested", 0) or 0)
    min_amt = float(grant.get("min_amount") or 0)
    max_amt = float(grant.get("max_amount") or 0)
    money_ok = (min_amt <= req <= max_amt) if (min_amt and max_amt) else True

    # Category / eligibility
    who = (form.get("who") or "").lower()
    eligible_types = [t.lower() for t in grant.get("eligible_types", [])]
    cat_ok = True if not eligible_types else any(who.startswith(t) or t in who for t in eligible_types)

    # Keyword overlap
    form_kw = set(tokenize(form.get("keywords", "")))
    grant_kw = set([t.lower() for t in grant.get("tags", [])])
    kw_hits = len(form_kw.intersection(grant_kw))

    # Geographic (very light)
    geo = grant.get("geo_scope", "us").lower()
    geo_ok = geo in ("us", "national", "united states")

    # Score
    score = 0
    score += 2 if money_ok else 0
    score += 2 if cat_ok else 0
    score += 1 if kw_hits >= 1 else 0
    score += 1 if kw_hits >= 3 else 0
    score += 1 if geo_ok else 0

    if score >= 5: fit = "High"
    elif score >= 3: fit = "Medium"
    else: fit = "Low"

    return {
        "fit": fit,
        "score": score,
        "money_ok": money_ok,
        "cat_ok": cat_ok,
        "kw_hits": kw_hits,
        "geo_ok": geo_ok
    }

def guard_amount(who: str, amount: float) -> Dict[str, Any]:
    cap = REQUEST_CAP.get(who, REQUEST_CAP["Other"])
    ok = amount <= cap
    return {"ok": ok, "cap": cap}

def ensure_csv_headers(path: str, headers: List[str]):
    exists = os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        if not exists:
            writer.writeheader()

def log_payment_row(row: Dict[str, Any]):
    headers = ["ts_utc","order_id","name","category","price","session_id","session_url","filename"]
    ensure_csv_headers(LOG_CSV, headers)
    with open(LOG_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writerow(row)

def map_session(session_id: str, order_id: str, filename: str):
    headers = ["session_id","order_id","filename"]
    ensure_csv_headers(MAP_CSV, headers)
    with open(MAP_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writerow({"session_id": session_id, "order_id": order_id, "filename": filename})

def find_by_session(session_id: str) -> Dict[str, str]:
    if not os.path.exists(MAP_CSV):
        return {}
    with open(MAP_CSV, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("session_id") == session_id:
                return row
    return {}

def make_pdf(order_id: str, payload: Dict[str, Any]) -> str:
    filename = f"{order_id}.pdf"
    pdf_path = os.path.join(OUTPUT_DIR, filename)
    c = canvas.Canvas(pdf_path, pagesize=letter)

    # Header
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, 760, "GrantForgeUSA — Draft (TEST)")
    c.setFont("Helvetica", 10)
    c.drawString(50, 744, f"Order: {order_id}    Created: {datetime.utcnow().isoformat()}Z")

    # Body
    y = 720
    def line(txt: str, step=14):
        nonlocal y
        c.drawString(50, y, txt[:1000])
        y -= step

    line("Intake Summary")
    for k in ("organization","who","keywords","amount_requested","annual_budget","project_title","timeline","audience","notes"):
        v = payload.get(k, "")
        line(f" - {k.replace('_',' ').title()}: {v}")

    line("")
    line("Chosen Opportunity")
    chosen = payload.get("chosen_grant", {})
    line(f" - {chosen.get('title','(none)')}")
    line(f" - Deadline: {chosen.get('deadline','')}")
    line(f" - Amount range: ${chosen.get('min_amount','?')} — ${chosen.get('max_amount','?')}")
    line(f" - Fit: {payload.get('fit','')}")
    line("")

    preview = (payload.get("preview_text") or "Preview text unavailable.")
    line("Preview (auto-generated):")
    # wrap preview into lines
    for chunk in [preview[i:i+95] for i in range(0, len(preview), 95)]:
        line(chunk)

    c.showPage()
    c.save()
    return pdf_path

def ai_preview(form: Dict[str, Any], grant: Dict[str, Any]) -> str:
    text = f"""Organization: {form.get('organization')}
Who: {form.get('who')}
Project: {form.get('project_title')}
Need/Timeline: {form.get('timeline')}
Audience: {form.get('audience')}
Amount Requested: {form.get('amount_requested')}
Grant: {grant.get('title')} (deadline {grant.get('deadline')})

Draft a short, plain-English summary (120–160 words) describing fit and what the funding will support.
"""
    if AI_OK and os.getenv("GOOGLE_API_KEY"):
        try:
            genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
            model = genai.GenerativeModel("gemini-1.5-flash")
            resp = model.generate_content(text)
            return (resp.text or "").strip()[:1200] or "Summary pending."
        except Exception:
            pass
    # Fallback
    return (
        f"Your organization proposes a focused initiative aligned with {', '.join(tokenize(form.get('keywords','')))}. "
        f"The project seeks {form.get('amount_requested')} to expand reach and deliver measurable outcomes. "
        f"Requested funds will support materials, coordination, and participant-facing activities. "
        f"This summary highlights eligibility and alignment to help you decide before purchasing a full draft."
    )

# ---------- Routes ----------
@app.get("/")
def home():
    return "<h3>GrantForgeUSA v11 Backend</h3><p>Status: OK</p>"

@app.get("/get/health")
def get_health():
    return jsonify(
        ok=True,
        frontend=FRONTEND_URL,
        publishableKey=bool(PUBLISHABLE_KEY),
        ai_ready=AI_OK and bool(os.getenv("GOOGLE_API_KEY")),
        firestore_ready=FS_OK,
        ts=datetime.utcnow().isoformat()+"Z"
    )

@app.post("/questionnaire")
def questionnaire():
    """
    Intake -> shortlist recommendations with fit scoring.
    """
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify(ok=False, error="Invalid JSON"), 400

    # Normalize
    form = {
        "organization": (data.get("organization") or "").strip(),
        "who": (data.get("who") or "").strip(),
        "keywords": (data.get("keywords") or "").strip(),
        "amount_requested": float(data.get("amount_requested") or 0),
        "annual_budget": float(data.get("annual_budget") or 0),
        "project_title": (data.get("project_title") or "").strip(),
        "timeline": (data.get("timeline") or "").strip(),
        "audience": (data.get("audience") or "").strip(),
        "notes": (data.get("notes") or "").strip(),
    }

    # Anti-fraud cap
    cap_check = guard_amount(form["who"], form["amount_requested"])
    if not cap_check["ok"]:
        return jsonify(
            ok=False,
            error=f"Requested amount exceeds category limit (${cap_check['cap']:,}). "
                  f"Please adjust or choose the correct category."
        ), 400

    grants = load_grants()
    if not grants:
        return jsonify(ok=False, error="Grants database is empty."), 500

    # Score and sort
    scored = []
    for g in grants:
        s = score_fit(g, form)
        row = {
            "title": g.get("title"),
            "program_url": g.get("program_url"),
            "deadline": g.get("deadline"),
            "min_amount": g.get("min_amount"),
            "max_amount": g.get("max_amount"),
            "fit": s["fit"],
            "score": s["score"],
            "money_ok": s["money_ok"],
            "kw_hits": s["kw_hits"],
        }
        scored.append(row)

    scored.sort(key=lambda r: (r["money_ok"], r["score"]), reverse=True)
    top = scored[:3]

    # Compute price
    price = PRICES.get(form["who"], PRICES["Other"])

    return jsonify(ok=True, price=price, results=top)

@app.post("/preview")
def preview():
    """
    Generate a free short preview for a chosen grant.
    """
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify(ok=False, error="Invalid JSON"), 400

    form = data.get("form") or {}
    grant = data.get("grant") or {}

    txt = ai_preview(form, grant)
    return jsonify(ok=True, preview=txt)

@app.post("/create-checkout-session")
def create_checkout_session():
    if not (stripe.api_key and PUBLISHABLE_KEY):
        return jsonify(ok=False, error="Stripe test keys not configured."), 500

    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify(ok=False, error="Invalid JSON"), 400

    form = data.get("form") or {}
    chosen = data.get("grant") or {}
    who = (form.get("who") or "Other").strip()
    amount_requested = float(form.get("amount_requested") or 0)

    # Anti-fraud cap re-check
    cap_check = guard_amount(who, amount_requested)
    if not cap_check["ok"]:
        return jsonify(ok=False, error="Amount exceeds allowed cap for this category."), 400

    price = PRICES.get(who, PRICES["Other"])
    order_id = datetime.utcnow().strftime("ORD-%Y%m%d-%H%M%S-%f")

    # Generate preview text used in PDF
    preview_txt = ai_preview(form, chosen)

    # Create PDF now (pre-payment) so the file is guaranteed
    payload = {
        "organization": form.get("organization"),
        "who": who,
        "keywords": form.get("keywords"),
        "amount_requested": form.get("amount_requested"),
        "annual_budget": form.get("annual_budget"),
        "project_title": form.get("project_title"),
        "timeline": form.get("timeline"),
        "audience": form.get("audience"),
        "notes": form.get("notes"),
        "chosen_grant": chosen,
        "fit": chosen.get("fit", ""),
        "preview_text": preview_txt
    }
    pdf_path = make_pdf(order_id, payload)
    filename = os.path.basename(pdf_path)

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": f"Grant Draft — {who}"},
                    "unit_amount": cents(price),
                },
                "quantity": 1,
            }],
            success_url=f"{FRONTEND_URL}/thanks?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{FRONTEND_URL}/",
            metadata={
                "order_id": order_id,
                "filename": filename,
                "category": who,
                "organization": form.get("organization",""),
            }
        )
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 400

    # Log + map
    try:
        log_payment_row({
            "ts_utc": datetime.utcnow().isoformat()+"Z",
            "order_id": order_id,
            "name": form.get("organization",""),
            "category": who,
            "price": price,
            "session_id": session.id,
            "session_url": session.url,
            "filename": filename,
        })
        map_session(session.id, order_id, filename)
    except Exception:
        pass

    return jsonify(ok=True, url=session.url, sessionId=session.id, publishableKey=PUBLISHABLE_KEY)

@app.get("/download/<path:filename>")
def download(filename: str):
    """
    Download a generated PDF by filename (e.g., ORD-...pdf).
    """
    safe = os.path.basename(filename)
    path = os.path.join(OUTPUT_DIR, safe)
    if not os.path.exists(path):
        return jsonify(ok=False, error="not found"), 404
    try:
        return send_file(path, as_attachment=True, download_name=safe)
    except Exception:
        abort(500)

@app.get("/session")
def session_status():
    session_id = request.args.get("id")
    if not session_id:
        return jsonify(ok=False, error="missing id"), 400
    try:
        s = stripe.checkout.Session.retrieve(session_id)
        row = find_by_session(session_id)
        return jsonify(
            ok=True,
            status=s.status,
            payment_status=s.payment_status,
            file=row.get("filename"),
            order_id=row.get("order_id")
        )
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 400

# ---------- Dev server ----------
if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
