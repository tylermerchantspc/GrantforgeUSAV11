# GrantforgeUSA — v11 backend (TEST MODE)
# Purpose: Health, blackout-proof shortlist with money-match scoring,
#          free preview draft, Stripe test checkout, CORS for FE.

import os
from datetime import datetime, date
from flask import Flask, request, jsonify
from flask_cors import CORS
import stripe
from dotenv import load_dotenv

# Optional stubs (safe to keep; ignore failures in prod)
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
except Exception:
    letter = None
    canvas = None

try:
    import pandas as pd
except Exception:
    pd = None

# ---------------- bootstrap env ----------------
load_dotenv()

FRONTEND_URL = os.getenv("FRONTEND_URL", "https://grantforge-usav-11.vercel.app")

# Stripe (test)
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")          # sk_test_...
PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")    # pk_test_...
# assert stripe.api_key and PUBLISHABLE_KEY, "Stripe keys missing in .env"  # enable if needed

OUTPUT_DIR = os.getenv("OUTPUT_DIR", "v11_payment_data")
os.makedirs(OUTPUT_DIR, exist_ok=True)

BASE_PRICE = 19.99
TEACHER_PRICE = 9.99

# ---------------- local grants DB (blackout-proof) ----------------
import json
DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "grants.json")
try:
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        GRANTS = json.load(f)
except Exception:
    GRANTS = []  # service still runs without data

# ---------------- Flask app ----------------
app = Flask(__name__)

# Wide-open CORS for testing; tighten to your exact domain(s) in prod
CORS(app, origins="*")

# ---------------- helpers ----------------
def cents(x: float) -> int:
    try:
        return int(round(float(x) * 100))
    except Exception:
        return 0

def make_pdf(order_id: str, payload: dict) -> str:
    """Best-effort PDF stub; ignored if reportlab missing."""
    if not (letter and canvas):
        return ""
    pdf_path = os.path.join(OUTPUT_DIR, f"{order_id}.pdf")
    c = canvas.Canvas(pdf_path, pagesize=letter)
    c.drawString(50, 750, "GrantforgeUSA | Draft (TEST)")
    c.drawString(50, 730, f"Order: {order_id}")
    c.drawString(50, 710, f"Created: {datetime.utcnow().isoformat()}Z")
    y = 690
    for k, v in payload.items():
        c.drawString(50, y, f"{k}: {v}")
        y -= 18
    c.showPage()
    c.save()
    return pdf_path

def to_float(x):
    try:
        return float(str(x or "").replace(",", "").strip() or 0)
    except Exception:
        return 0.0

def norm_type(cat: str) -> str:
    c = (cat or "").lower()
    if "teacher" in c: return "teacher"
    if "school" in c: return "school"
    if "501" in c: return "501c3"
    if "church" in c or "faith" in c: return "church"
    if "small" in c and "business" in c: return "small_business"
    if "municip" in c or "city" in c or "county" in c: return "municipality"
    if "community" in c or "club" in c: return "community"
    return "other"

# ---------------- health ----------------
@app.get("/")
def home():
    return "<h2>GrantforgeUSA v11 Backend</h2><p>Status: OK</p>"

@app.get("/get/health")
def get_health():
    return jsonify(
        ok=True,
        publishableKey=bool(PUBLISHABLE_KEY),
        frontendUrl=FRONTEND_URL,
        grantsCount=len(GRANTS),
        ts=datetime.utcnow().isoformat() + "Z",
    )

# ---------------- shortlist with money-match scoring ----------------
@app.post("/questionnaire")
def questionnaire():
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify(ok=False, error="Invalid JSON"), 400

    org = (data.get("organization") or "Your Organization").strip()
    category = (data.get("category") or "").strip()
    keywords = (data.get("keywords") or "general").strip()
    timeline = (data.get("timeline") or "").strip()
    project_title = (data.get("projectTitle") or "").strip()
    audience = (data.get("audience") or "").strip()
    outcomes = (data.get("outcomes") or "").strip()

    requested = to_float(data.get("amountRequested"))
    budget    = to_float(data.get("budget"))

    otype = norm_type(category)
    kw_set = set([w.strip().lower() for w in str(keywords).split(",") if w.strip()]) or set()

    today = date.today()
    results = []

    for g in GRANTS:
        reasons = []
        eligible = True

        # Hard fails
        if otype not in g.get("eligible_types", []):
            eligible = False
            reasons.append("Organization type not eligible")

        # Deadline check
        try:
            y, m, d = map(int, g.get("deadline", "2100-01-01").split("-"))
            if date(y, m, d) < today:
                eligible = False
                reasons.append("Deadline passed")
        except Exception:
            pass

        # Requested amount vs program window
        min_a = float(g.get("min_amount", 0) or 0)
        max_a = float(g.get("max_amount", 0) or 0)
        if requested > 0 and (requested < min_a or requested > max_a):
            eligible = False
            reasons.append(
                f"Requested ${int(requested):,} outside program range ${int(min_a):,}-${int(max_a):,}"
            )

        # Cash match requirement vs budget (conservative)
        req_match = float(g.get("requires_match_percent", 0) or 0) / 100.0
        if req_match > 0 and budget > 0 and requested > 0:
            needed = requested * req_match
            # assume ~10% of annual budget is comfortably liquid for matches
            if needed > 0.10 * budget:
                eligible = False
                reasons.append(
                    f"Requires ~{int(req_match*100)}% cash match that likely exceeds capacity"
                )

        # Score if eligible
        fit_score = 0
        if eligible:
            # Money fit (60%)
            if min_a and max_a and requested > 0 and max_a > min_a:
                mid = (min_a + max_a) / 2.0
                rng = (max_a - min_a)
                money = max(0.0, 1.0 - abs(requested - mid) / (rng / 2.0))
            else:
                money = 0.7  # neutral if unknown

            # Keyword fit (30%)
            g_tags = set([t.lower() for t in g.get("tags", [])])
            if kw_set:
                overlap = len(g_tags & kw_set)
                keywords_score = min(1.0, overlap / max(1, len(kw_set)))
            else:
                keywords_score = 0.6

            # Budget ratio (10%)
            if budget > 0 and requested > 0:
                ratio = requested / budget
                if ratio <= 0.2:
                    br = 1.0
                elif ratio >= 0.5:
                    br = 0.2
                else:
                    br = 1.0 - (ratio - 0.2) * (0.8 / 0.3)
            else:
                br = 0.6

            fit_score = round(100 * (0.6 * money + 0.3 * keywords_score + 0.1 * br))

        # Force 0 when any hard fail
        if not eligible:
            fit_score = 0

        results.append({
            "title": g.get("title"),
            "program_url": g.get("program_url"),
            "deadline": g.get("deadline"),
            "min_amount": int(min_a),
            "max_amount": int(max_a),
            "requires_match_percent": int(req_match * 100),
            "eligible": eligible,
            "fit_score": fit_score,
            "reasons": reasons,
            "amount": f"${int(min_a):,}-${int(max_a):,}",
            "fit": "High" if fit_score >= 75 else "Medium" if fit_score >= 50 else "Low"
        })

    # Sort: eligible first, highest score first
    results.sort(key=lambda r: (r["eligible"], r["fit_score"]), reverse=True)

    msg = None
    if not any(r["eligible"] for r in results):
        msg = "No qualifying opportunities found."

    return jsonify(
        ok=True,
        organization=org,
        keywords=keywords,
        results=results,
        message=msg
    )

# ---------------- free preview draft (outline stub) ----------------
@app.post("/draft")
def draft():
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify(ok=False, error="Invalid JSON"), 400

    org = (data.get("organization") or "Your Organization").strip()
    topic = (data.get("topic") or data.get("keywords") or "community").strip()

    outline = {
        "Summary": f"{org} seeks support for a {topic} initiative to serve local needs.",
        "Need": f"There is a documented need around {topic} impacting our service area.",
        "Objectives": ["Objective 1", "Objective 2", "Objective 3"],
        "Methods": ["Method A", "Method B"],
        "Budget Narrative": "Funds will support staff time, supplies, and outreach.",
        "Impact": "Expected outcomes include improved access and measurable gains.",
        "Compliance": "We will follow all program rules and reporting requirements.",
    }
    return jsonify(ok=True, outline=outline)

# ---------------- Stripe Checkout (test) ----------------
@app.post("/create-checkout-session")
def create_checkout_session():
    if not (stripe.api_key and PUBLISHABLE_KEY):
        return jsonify(ok=False, error="Stripe test keys are not configured"), 400

    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify(ok=False, error="Invalid JSON"), 400

    name = (data.get("name") or "Tester").strip()
    category = (data.get("category") or "General").strip()
    is_teacher = bool(data.get("isTeacher"))

    price = TEACHER_PRICE if is_teacher and category.lower().startswith("teacher") else BASE_PRICE
    product_name = f"Grant Draft ({category})" + (" — Teacher" if is_teacher else "")

    order_id = datetime.utcnow().strftime("ORD-%Y%m%d-%H%M%S-%f")
    metadata = {
        "order_id": order_id,
        "name": name,
        "category": category,
        "is_teacher": str(is_teacher),
        "price": f"{price:.2f}",
    }

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": product_name},
                    "unit_amount": cents(price),
                },
                "quantity": 1,
            }],
            success_url=f"{FRONTEND_URL}/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{FRONTEND_URL}/cancel",
            metadata=metadata,
        )
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 400

    # best-effort CSV + PDF stubs (ignore failures)
    try:
        if pd:
            log_path = os.path.join(OUTPUT_DIR, "payments_log.csv")
            row = {
                "ts_utc": datetime.utcnow().isoformat() + "Z",
                "order_id": order_id,
                "name": name,
                "category": category,
                "is_teacher": is_teacher,
                "price": price,
                "session_id": session.id,
                "session_url": session.url,
            }
            if os.path.exists(log_path):
                df = pd.read_csv(log_path)
                df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
            else:
                df = pd.DataFrame([row])
            df.to_csv(log_path, index=False)
    except Exception:
        pass

    try:
        make_pdf(order_id, {"name": name, "category": category, "teacher": is_teacher, "price": price})
    except Exception:
        pass

    return jsonify(ok=True, url=session.url, sessionId=session.id, publishableKey=PUBLISHABLE_KEY)

# ---------------- session probe + simple success/cancel ----------------
@app.get("/session")
def get_session():
    session_id = request.args.get("id")
    if not session_id:
        return jsonify(ok=False, error="missing id"), 400
    try:
        s = stripe.checkout.Session.retrieve(session_id)
        return jsonify(ok=True, status=s.status, payment_status=s.payment_status)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 400

@app.get("/success")
def success():
    session_id = request.args.get("session_id", "")
    return f"<h3>✅ Payment Success!</h3><p>Session ID: {session_id}</p>"

@app.get("/cancel")
def cancel():
    return "<h3>❌ Payment Cancelled</h3>"

# ---------------- dev server ----------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
