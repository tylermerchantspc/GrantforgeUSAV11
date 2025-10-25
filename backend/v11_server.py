# GrantforgeUSA — v11 backend (TEST MODE)
# Intake → shortlist → free preview → Stripe pay → finalize → full PDF link

import os, json
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import stripe
from dotenv import load_dotenv

# --- optional (PDF + CSV stubs) ---
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import pandas as pd

# ---------------- bootstrap env ----------------
load_dotenv()

FRONTEND_URL = os.getenv("FRONTEND_URL", "https://grantforge-usav-11.vercel.app")

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")          # sk_test_...
PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")    # pk_test_...

OUTPUT_DIR = os.getenv("OUTPUT_DIR", "v11_payment_data")
os.makedirs(OUTPUT_DIR, exist_ok=True)

BASE_PRICE = 49.99     # default per-draft
TEACHER_PRICE = 9.99   # teacher/classroom per-draft
MID_PRICE = 99.99      # 500,001–2M
LARGE_PRICE = 199.99   # 2M+

# ---------------- sample grant data ----------------
# id is REQUIRED (used for preview + finalize)
SAMPLE_RESULTS = [
    {
        "id": "GF-TEST-001",
        "title": "Community Support Grant",
        "program": "GF-TEST-001",
        "amount": "$25,000",
        "deadline": "2025-12-31",
        "fit": "High",
        "requires_match_percent": 0,
    },
    {
        "id": "GF-TEST-002",
        "title": "Capacity Mini-Grant",
        "program": "GF-TEST-002",
        "amount": "$5,000",
        "deadline": "2025-11-30",
        "fit": "Medium",
        "requires_match_percent": 0,
    },
    {
        "id": "GF-TEST-003",
        "title": "Neighborhood Microgrant",
        "program": "GF-TEST-003",
        "amount": "$500–$2,500",
        "deadline": "2026-02-28",
        "fit": "Medium",
        "requires_match_percent": 0,
    },
]

# ---------------- helpers ----------------
def cents(x: float) -> int:
    return int(round(float(x) * 100))

def pricing_for_intake(intake: dict) -> float:
    who = (intake.get("who") or "").lower()
    budget = float(intake.get("budget") or 0.0)

    if "teacher" in who:
        return TEACHER_PRICE
    if budget <= 500000:
        return BASE_PRICE
    if 500000 < budget <= 2000000:
        return MID_PRICE
    return LARGE_PRICE

def make_pdf(order_id: str, payload: dict) -> str:
    pdf_path = os.path.join(OUTPUT_DIR, f"{order_id}.pdf")
    c = canvas.Canvas(pdf_path, pagesize=letter)

    # simple cover
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, 760, "GrantForgeUSA — Draft (TEST)")
    c.setFont("Helvetica", 10)
    c.drawString(50, 744, f"Order: {order_id}")
    c.drawString(50, 732, f"Created: {datetime.utcnow().isoformat()}Z")

    y = 708
    for k, v in payload.items():
        line = f"{k}: {v}"
        c.drawString(50, y, line[:110])
        y -= 14
        if y < 60:
            c.showPage(); y = 760

    c.showPage()
    c.save()
    return pdf_path

# ---------------- Flask app ----------------
app = Flask(__name__)
CORS(app, origins="*")  # wide open for test; restrict before prod

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

# ---------------- intake → shortlist ----------------
@app.post("/questionnaire")
def questionnaire():
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify(ok=False, error="Invalid JSON"), 400

    org = (data.get("organization") or "Your organization").strip()
    keywords = (data.get("keywords") or "").strip()

    # TODO: replace SAMPLE_RESULTS with filtered DB results
    results = SAMPLE_RESULTS[:2]  # show 2 for now

    return jsonify(ok=True, organization=org, keywords=keywords, results=results)

# ---------------- free short preview ----------------
@app.post("/preview")
def preview():
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify(ok=False, error="Invalid JSON"), 400

    grant_id = (data.get("grant_id") or "").strip()
    intake = data.get("intake") or {}

    if not grant_id:
        return jsonify(ok=False, error="missing grant_id"), 400

    org = (intake.get("organization") or "Your organization").strip()
    topic = (intake.get("keywords") or "community needs").strip()
    amount = intake.get("amount") or "requested support"

    teaser = (
        f"{org} proposes a focused initiative aligned with {topic}. "
        f"The project seeks {amount} to expand reach and deliver measurable outcomes. "
        f"Requested funds will be used for materials, coordination, and student-facing activities. "
        f"This summary highlights eligibility and alignment to help you decide before purchasing a full draft."
    )
    return jsonify(ok=True, grant_id=grant_id, preview=teaser)

# ---------------- Stripe: create checkout ----------------
@app.post("/create-checkout-session")
def create_checkout_session():
    if not (stripe.api_key and PUBLISHABLE_KEY):
        return jsonify(ok=False, error="Stripe test keys are not configured"), 400

    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify(ok=False, error="Invalid JSON"), 400

    intake = data.get("intake") or {}
    category = (data.get("category") or intake.get("who") or "General").strip()
    is_teacher = "teacher" in category.lower()
    grant_id = (data.get("grant_id") or "").strip()

    price = pricing_for_intake(intake)
    product_name = f"Grant Draft ({category})" + (" — Teacher" if is_teacher else "")
    order_id = datetime.utcnow().strftime("ORD-%Y%m%d-%H%M%S-%f")

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
            success_url=f"{FRONTEND_URL}/thanks?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{FRONTEND_URL}/cancel",
            metadata={
                "order_id": order_id,
                "price": f"{price:.2f}",
                "grant_id": grant_id,
                "intake": json.dumps(intake),
            },
        )
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 400

    # best-effort CSV log
    try:
        log_path = os.path.join(OUTPUT_DIR, "payments_log.csv")
        row = {
            "ts_utc": datetime.utcnow().isoformat() + "Z",
            "order_id": order_id,
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

    return jsonify(ok=True, url=session.url, sessionId=session.id, publishableKey=PUBLISHABLE_KEY)

# ---------------- finalize after payment → full draft ----------------
@app.get("/finalize")
def finalize():
    session_id = request.args.get("session_id", "").strip()
    if not session_id:
        return jsonify(ok=False, error="missing session_id"), 400
    try:
        s = stripe.checkout.Session.retrieve(session_id)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 400

    if s.payment_status != "paid":
        return jsonify(ok=False, error="payment not completed"), 400

    md = s.get("metadata", {}) or {}
    order_id = md.get("order_id") or datetime.utcnow().strftime("ORD-%Y%m%d-%H%M%S-%f")
    grant_id = md.get("grant_id") or "UNKNOWN"
    try:
        intake = json.loads(md.get("intake", "{}"))
    except Exception:
        intake = {}

    full_payload = {
        "order_id": order_id,
        "grant_id": grant_id,
        "organization": intake.get("organization") or "Your organization",
        "who": intake.get("who") or "Applicant",
        "keywords": intake.get("keywords") or "",
        "amount": intake.get("amount") or "",
        "budget": intake.get("budget") or "",
        "title": intake.get("title") or "",
        "timeline": intake.get("timeline") or "",
        "audience": intake.get("audience") or "",
        "notes": intake.get("notes") or "",
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }

    pdf_path = make_pdf(order_id, full_payload)
    download_url = f"{request.host_url}download/{order_id}.pdf"
    return jsonify(ok=True, order_id=order_id, download_url=download_url)

@app.get("/download/<order_id>.pdf")
def download_pdf(order_id):
    path = os.path.join(OUTPUT_DIR, f"{order_id}.pdf")
    if not os.path.exists(path):
        return jsonify(ok=False, error="not found"), 404
    return send_file(path, as_attachment=False, download_name=f"{order_id}.pdf")
