# GrantforgeUSA — v11 local/preview backend (TEST MODE)
# Purpose: Stripe Checkout (test), PDF draft stub, lightweight CSV log, status probes

import os, json
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
import stripe
from dotenv import load_dotenv
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import pandas as pd

# ---------- bootstrap env ----------
load_dotenv()

# Required Stripe keys
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")         # sk_test_...
PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")   # pk_test_...
assert stripe.api_key and PUBLISHABLE_KEY, "Stripe keys missing in .env"

# Redirect base (where to send user after checkout)
# For LOCAL default we point to this Flask app, for Vercel set FRONTEND_URL to your vercel.app
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://127.0.0.1:5001")

# Output dir for PDFs/CSV
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "v11_payment_data")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Pricing (USD)
BASE_PRICE = 19.99
TEACHER_PRICE = 9.99

# ---------- Flask app ----------
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})  # OK for test; restrict in prod

# ---------- helpers ----------
def cents(x: float) -> int:
    return int(round(x * 100))

def make_pdf(order_id: str, payload: dict) -> str:
    """
    Creates a very simple one-page PDF stub as a stand-in for draft output.
    """
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

# ---------- health ----------
@app.get("/")
def home():
    return "<h2>GrantforgeUSA v11 Local Server</h2><p>Status: OK</p>"

@app.get("/get/health")
def get_health():
    return jsonify(ok=True, publishableKey=bool(PUBLISHABLE_KEY))

# ---------- checkout ----------
@app.post("/create-checkout-session")
def create_checkout_session():
    """
    Expected JSON body:
    {
      "name": "Tester",
      "category": "Education" | "Small Business" | "City/Municipality" | "Church" | "501c",
      "isTeacher": true/false
    }
    """
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify(ok=False, error="Invalid JSON"), 400

    # Normalize inputs with sensible defaults for manual testing
    name = (data.get("name") or "Tester").strip()
    category = (data.get("category") or "General").strip()
    is_teacher = bool(data.get("isTeacher"))

    # Pricing rule
    price = TEACHER_PRICE if is_teacher and category.lower().startswith("education") else BASE_PRICE

    # Naming
    product_name = f"Grant Draft ({category})"
    if is_teacher:
        product_name += " — Teacher"

    # Local order id (for files/logs)
    order_id = datetime.utcnow().strftime("ORD-%Y%m%d-%H%M%S-%f")

    # Metadata visible in Stripe Dashboard
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
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {"name": product_name},
                        "unit_amount": cents(price),
                    },
                    "quantity": 1,
                }
            ],
            # Redirects — FRONTEND_URL controls where this goes (Flask local or Vercel)
            success_url=f"{FRONTEND_URL}/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{FRONTEND_URL}/cancel",
            metadata=metadata,
        )
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 400

    # Lightweight CSV log so we know what we charged
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
    try:
        if os.path.exists(log_path):
            df = pd.read_csv(log_path)
            df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
        else:
            df = pd.DataFrame([row])
        df.to_csv(log_path, index=False)
    except Exception:
        # Don't block checkout if log write fails
        pass

    # Make a test PDF stub (non-blocking)
    try:
        make_pdf(order_id, {
            "name": name,
            "category": category,
            "teacher": is_teacher,
            "price": price
        })
    except Exception:
        pass

    return jsonify(ok=True, url=session.url, sessionId=session.id, publishableKey=PUBLISHABLE_KEY)

# ---------- simple success/cancel pages (work locally; optional on Vercel) ----------
@app.get("/success")
def success():
    session_id = request.args.get("session_id", "")
    return f"<h3>✅ Payment Success!</h3><p>Session ID: {session_id}</p>"

@app.get("/cancel")
def cancel():
    return "<h3>❌ Payment Cancelled</h3>"

# ---------- optional session probe ----------
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

# ---------- dev server ----------
if _name_ == "_main_":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
