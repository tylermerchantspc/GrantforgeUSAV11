# GrantforgeUSA — v11 backend (TEST MODE)
# Health, CORS-safe API for FE, shortlist + draft stubs, Stripe test checkout

import os
from datetime import datetime

from flask import Flask, request, jsonify
from flask_cors import CORS
import stripe
from dotenv import load_dotenv

# Optional stubs (safe to keep even if not used)
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import pandas as pd

# ---------------- bootstrap env ----------------
load_dotenv()

FRONTEND_URL = os.getenv("FRONTEND_URL", "https://grantforge-usav-11.vercel.app")

# Stripe (test)
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")          # sk_test_...
PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")    # pk_test_...
# To require keys strictly, uncomment:
# assert stripe.api_key and PUBLISHABLE_KEY, "Stripe keys missing in .env"

OUTPUT_DIR = os.getenv("OUTPUT_DIR", "v11_payment_data")
os.makedirs(OUTPUT_DIR, exist_ok=True)

BASE_PRICE = 19.99
TEACHER_PRICE = 9.99

# ---------------- Flask app ----------------
app = Flask(__name__)

# Wide-open CORS for testing (keeps browser happy). Tighten later if desired.
CORS(app, origins="*")

# ---------------- helpers ----------------
def cents(x: float) -> int:
    return int(round(float(x) * 100))

def make_pdf(order_id: str, payload: dict) -> str:
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
        ts=datetime.utcnow().isoformat() + "Z",
    )

# ---------------- shortlist stub (Find Grants) ----------------
@app.post("/questionnaire")
def questionnaire():
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify(ok=False, error="Invalid JSON"), 400

    org = (data.get("organization") or data.get("org") or "Your Organization").strip()
    keywords = (data.get("keywords") or data.get("keyword") or "general").strip()

    shortlist = [
        {
            "title": f"{keywords.title()} Community Support Grant",
            "program": "GF-TEST-001",
            "amount": "$25,000",
            "deadline": "2025-12-31",
            "fit": "High",
        },
        {
            "title": f"{keywords.title()} Capacity Mini-Grant",
            "program": "GF-TEST-002",
            "amount": "$5,000",
            "deadline": "2025-11-30",
            "fit": "Medium",
        },
    ]
    return jsonify(ok=True, organization=org, keywords=keywords, results=shortlist)

# ---- alias so older FE route still works ----
@app.route("/find-grants", methods=["POST", "OPTIONS"])
def find_grants_alias():
    if request.method == "OPTIONS":
        return ("", 204)
    return questionnaire()

# ---------------- draft stub (Draft button) ----------------
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

    price = TEACHER_PRICE if is_teacher and category.lower().startswith("education") else BASE_PRICE
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

# ---------------- session probe ----------------
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

# ---------------- dev server ----------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
