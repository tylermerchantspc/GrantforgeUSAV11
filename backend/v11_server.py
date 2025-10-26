# GrantForgeUSA — v1.1 backend (TEST MODE)
# Purpose: Solid PDF generation (atomic writes), status checks, Stripe test checkout,
#          shortlist + preview endpoints, basic fraud caps, CORS for FE.

import os, io, json, time, shutil
from datetime import datetime
from typing import Dict, Any, List

from flask import Flask, request, jsonify, send_file, abort
from flask_cors import CORS
from dotenv import load_dotenv
import stripe

# Optional stubs (safe if libs are present)
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

TMP_DIR = "/tmp/grantforge"
os.makedirs(TMP_DIR, exist_ok=True)

# ---------------- Flask app ----------------
app = Flask(__name__)

# CORS: allow your Vercel site + localhost dev
CORS(app, resources={r"/*": {
    "origins": [
        "https://grantforge-usav-11.vercel.app",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
}})

# ---------------- helpers ----------------
def cents(x: float) -> int:
    return int(round(float(x) * 100))

def now_utc() -> str:
    return datetime.utcnow().isoformat() + "Z"

def safe_atomic_write_pdf(pdf_bytes: bytes, order_id: str) -> str:
    """
    Write to /tmp, fsync, then atomically move to OUTPUT_DIR.
    Returns final absolute path.
    """
    tmp_path = os.path.join(TMP_DIR, f"{order_id}.pdf.part")
    final_path = os.path.join(OUTPUT_DIR, f"{order_id}.pdf")

    # write tmp
    with open(tmp_path, "wb") as f:
        f.write(pdf_bytes)
        f.flush()
        os.fsync(f.fileno())

    # ensure destination dir exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    # atomic move
    shutil.move(tmp_path, final_path)
    return final_path

def pdf_exists(order_id: str) -> bool:
    return os.path.exists(os.path.join(OUTPUT_DIR, f"{order_id}.pdf"))

def make_pdf(order_id: str, intake: Dict[str, Any], grant: Dict[str, Any]) -> str:
    """
    Creates a simple one-page PDF draft stub (preview-level). Atomic write.
    """
    # Build PDF in-memory first
    buff = io.BytesIO()
    c = canvas.Canvas(buff, pagesize=letter)

    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, 760, "GrantForgeUSA — Draft (TEST)")
    c.setFont("Helvetica", 10)
    c.drawString(50, 742, f"Order: {order_id}")
    c.drawString(50, 730, f"Created: {now_utc()}")

    y = 710
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Selected Opportunity")
    y -= 16
    c.setFont("Helvetica", 10)
    c.drawString(50, y, f"Title: {grant.get('title','')}")
    y -= 14
    c.drawString(50, y, f"Deadline: {grant.get('deadline','')}")
    y -= 14
    c.drawString(50, y, f"Amount: {grant.get('max_amount','$—')}")
    y -= 14
    c.drawString(50, y, f"Fit: {grant.get('fit','—')}")
    y -= 22

    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Project Summary")
    y -= 16
    c.setFont("Helvetica", 10)

    lines = [
        f"Organization: {intake.get('organization','')}",
        f"Category: {intake.get('category','')}",
        f"Keywords: {', '.join(intake.get('keywords', []))}",
        f"Requested: ${intake.get('amount_requested','')}",
        f"Budget: ${intake.get('annual_budget','')}",
        f"Title: {intake.get('project_title','')}",
        f"Timeline: {intake.get('timeline','')}",
        f"Audience: {intake.get('audience','')}",
        f"Notes: {intake.get('notes','')}",
    ]
    for line in lines:
        c.drawString(50, y, line[:1000])
        y -= 14
        if y < 60:
            c.showPage()
            y = 760

    c.setFont("Helvetica-Oblique", 9)
    c.drawString(50, y-10, "This product uses AI to generate previews and draft language. Review and edit before any submission.")
    c.save()

    pdf_bytes = buff.getvalue()
    buff.close()

    # Atomic write to final location
    final_path = safe_atomic_write_pdf(pdf_bytes, order_id)
    return final_path

def fraud_caps(category: str, amount_requested: float) -> Dict[str, Any]:
    """
    Simple fraud/abuse guardrails. Returns {ok: bool, reason: str, normalized_amount: float}
    """
    caps = {
        "Teacher (Classroom)": 10000,                  # hard cap $10k
        "School / District": 250000,                   # $250k
        "Small Nonprofit / Club": 50000,               # $50k
        "Small Business": 50000,                       # $50k
        "City / Municipality": 2000000,                # $2M
        "Church / Faith Org": 100000,                  # $100k
        "501(c)(3) Nonprofit": 250000,                 # $250k
        "Other": 50000
    }
    absolute_min, absolute_max = 100, 5_000_000

    if amount_requested < absolute_min or amount_requested > absolute_max:
        return {"ok": False, "reason": "amount out of bounds", "normalized_amount": amount_requested}

    cap = caps.get(category, caps["Other"])
    if amount_requested > cap:
        return {"ok": False, "reason": f"amount exceeds category cap (${cap:,})", "normalized_amount": cap}

    return {"ok": True, "reason": "ok", "normalized_amount": amount_requested}

def shortlist_from_stub(intake: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Temporary shortlist (replace with full DB in Step 3).
    """
    kw = [k.strip().lower() for k in intake.get("keywords", []) if k.strip()]
    cat = intake.get("category","").lower()

    base = [
        {
            "id": "GF-TEST-001",
            "title": "Community Support Grant",
            "program_url": "https://example.org/community",
            "deadline": "2025-12-31",
            "max_amount": 25000,
            "fit": "High" if "community" in kw or cat in ("teacher (classroom)","school / district") else "Medium",
            "requires_match_percent": 0
        },
        {
            "id": "GF-TEST-002",
            "title": "Capacity Mini-Grant",
            "program_url": "https://example.org/capacity",
            "deadline": "2025-11-30",
            "max_amount": 5000,
            "fit": "Medium",
            "requires_match_percent": 0
        }
    ]
    # add a STEM-ish item if keywords contain stem/robot
    if any(k in kw for k in ("stem", "robot", "robotics")):
        base.insert(0, {
            "id": "GF-TEST-003",
            "title": "STEM Classroom Enrichment",
            "program_url": "https://example.org/stem-class",
            "deadline": "2026-03-31",
            "max_amount": 10000,
            "fit": "High" if "teacher (classroom)" == intake.get("category","") else "Medium",
            "requires_match_percent": 10
        })
    return base[:3]

# ---------------- routes ----------------
@app.get("/")
def home():
    return "<h2>GrantForgeUSA v1.1 Backend</h2><p>Status: OK</p>"

@app.get("/get/health")
def get_health():
    return jsonify(ok=True, frontendUrl=FRONTEND_URL, publishableKey=bool(PUBLISHABLE_KEY), ts=now_utc())

@app.post("/questionnaire")
def questionnaire():
    """
    Intake → shortlist (3 items max). Also enforces fraud caps.
    Body:
    {
      organization, category, keywords[], amount_requested, annual_budget,
      project_title, timeline, audience, notes, email
    }
    """
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify(ok=False, error="Invalid JSON"), 400

    org = (data.get("organization") or "").strip()
    category = (data.get("category") or "").strip()
    email = (data.get("email") or "").strip()

    try:
        amount_requested = float(data.get("amount_requested") or 0)
    except Exception:
        amount_requested = 0

    fraud = fraud_caps(category, amount_requested)
    if not fraud["ok"]:
        return jsonify(ok=False, error="Amount not allowed", reason=fraud["reason"]), 400

    shortlist = shortlist_from_stub({
        **data,
        "amount_requested": fraud["normalized_amount"]
    })

    # compute pay label based on category
    prices = {
        "Teacher (Classroom)": 9.99,
        "Small Nonprofit / Club": 49.99,
        "Small Business": 49.99,
        "School / District": 49.99,
        "Church / Faith Org": 49.99,
        "501(c)(3) Nonprofit": 99.99,
        "City / Municipality": 199.99,
        "Other": 49.99
    }
    price = prices.get(category, prices["Other"])

    return jsonify(ok=True, price=price, results=shortlist)

@app.post("/preview")
def preview():
    """
    Generates a free AI summary paragraph (stubbed here).
    Body: { intake: {...}, grant: {...} }
    """
    try:
        body = request.get_json(force=True) or {}
    except Exception:
        return jsonify(ok=False, error="Invalid JSON"), 400

    intake = body.get("intake") or {}
    grant = body.get("grant") or {}
    org = intake.get("organization","Your organization")
    keywords = ", ".join(intake.get("keywords", [])) or "community"
    req = intake.get("amount_requested","—")

    text = (f"{org} proposes a focused initiative aligned with {keywords}. "
            f"The project seeks ${req} to expand reach and deliver measurable outcomes. "
            f"This summary highlights eligibility and alignment to help you decide before purchasing a full draft.")
    return jsonify(ok=True, preview=text)

@app.post("/create-checkout-session")
def create_checkout_session():
    """
    Creates Stripe checkout session. Body:
    { intake: {...}, grant: {...}, price: 9.99/49.99/... }
    """
    if not (stripe.api_key and PUBLISHABLE_KEY):
        return jsonify(ok=False, error="Stripe test keys are not configured"), 400

    try:
        body = request.get_json(force=True) or {}
    except Exception:
        return jsonify(ok=False, error="Invalid JSON"), 400

    intake = body.get("intake") or {}
    grant = body.get("grant") or {}
    price = float(body.get("price") or 0)

    # fraud re-check
    category = intake.get("category","")
    amount_requested = float(intake.get("amount_requested") or 0)
    fraud = fraud_caps(category, amount_requested)
    if not fraud["ok"]:
        return jsonify(ok=False, error="Amount not allowed", reason=fraud["reason"]), 400

    order_id = datetime.utcnow().strftime("ORD-%Y%m%d-%H%M%S-%f")

    metadata = {
        "order_id": order_id,
        "organization": intake.get("organization",""),
        "category": category,
        "amount_requested": str(fraud["normalized_amount"]),
        "grant_id": grant.get("id",""),
        "grant_title": grant.get("title",""),
        "email": intake.get("email","")
    }

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": f"Grant Draft — {grant.get('title','') or 'Custom'}"},
                    "unit_amount": cents(price),
                },
                "quantity": 1,
            }],
            success_url=f"{FRONTEND_URL}/thanks?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{FRONTEND_URL}",
            metadata=metadata,
        )
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 400

    # lightweight CSV log
    try:
        log_path = os.path.join(OUTPUT_DIR, "payments_log.csv")
        row = {
            "ts_utc": now_utc(),
            "order_id": order_id,
            "organization": intake.get("organization",""),
            "category": category,
            "amount_requested": fraud["normalized_amount"],
            "price": price,
            "session_id": session.id,
            "session_url": session.url,
            "grant_id": grant.get("id",""),
            "grant_title": grant.get("title","")
        }
        if os.path.exists(log_path):
            df = pd.read_csv(log_path)
            df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
        else:
            df = pd.DataFrame([row])
        df.to_csv(log_path, index=False)
    except Exception:
        pass

    return jsonify(ok=True, sessionId=session.id, url=session.url, orderId=order_id)

@app.get("/draft/status/<order_id>")
def draft_status(order_id: str):
    """
    Returns whether the draft PDF exists yet.
    """
    return jsonify(ok=True, exists=pdf_exists(order_id))

@app.post("/draft/build")
def draft_build():
    """
    Build the PDF (called by FE after payment succeeds).
    Body: { order_id, intake, grant }
    """
    try:
        body = request.get_json(force=True) or {}
    except Exception:
        return jsonify(ok=False, error="Invalid JSON"), 400

    order_id = body.get("order_id","").strip()
    intake = body.get("intake") or {}
    grant = body.get("grant") or {}

    if not order_id:
        return jsonify(ok=False, error="missing order_id"), 400

    # if already exists, return url
    if pdf_exists(order_id):
        url = request.url_root.rstrip("/") + f"/download/{order_id}.pdf"
        return jsonify(ok=True, url=url, already=True)

    # build fresh
    try:
        final_path = make_pdf(order_id, intake, grant)
    except Exception as e:
        return jsonify(ok=False, error=f"pdf build failed: {e}"), 500

    url = request.url_root.rstrip("/") + f"/download/{order_id}.pdf"
    return jsonify(ok=True, url=url)

@app.get("/download/<filename>")
def download_pdf(filename: str):
    """
    Streams an existing PDF if present.
    """
    safe_name = os.path.basename(filename)
    final_path = os.path.join(OUTPUT_DIR, safe_name)
    if not os.path.exists(final_path):
        return jsonify(ok=False, error="not found"), 404

    return send_file(final_path, mimetype="application/pdf", as_attachment=True,
                     download_name=safe_name)

# ---------------- run ----------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
