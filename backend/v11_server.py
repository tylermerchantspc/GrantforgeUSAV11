# GrantforgeUSA — v11 backend (TEST MODE)
# Purpose: shortlist w/ real matching + fraud checks, Stripe test checkout, reliable PDF download

import os, json
from datetime import datetime, date
from typing import Dict, Any, List

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import stripe
from dotenv import load_dotenv

# Optional stubs
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import pandas as pd

# ---------------- bootstrap env ----------------
load_dotenv()

FRONTEND_URL = os.getenv("FRONTEND_URL", "https://grantforge-usav-11.vercel.app")

# Stripe (test)
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")          # sk_test_...
PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")    # pk_test_...

OUTPUT_DIR = os.getenv("OUTPUT_DIR", "v11_payment_data")
DATA_DIR = os.getenv("DATA_DIR", "backend/data")
GRANTS_PATH = os.path.join(DATA_DIR, "grants.json")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Pricing
BASE_PRICE = 49.99
TEACHER_PRICE = 9.99
SMALL_PRICE = 49.99
MEDIUM_PRICE = 99.99
LARGE_PRICE = 199.99

# ---------------- Flask app ----------------
app = Flask(__name__)
CORS(app, origins="*")

# ---------------- helpers ----------------
def cents(x: float) -> int:
    return int(round(float(x) * 100))

def _now_utc():
    return datetime.utcnow().isoformat() + "Z"

def _read_json(path: str) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def _norm_words(s: str) -> List[str]:
    return [w.strip().lower() for w in (s or "").replace(",", " ").split() if w.strip()]

def _safe_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default

def _deadline_ok(deadline_str: str) -> bool:
    try:
        d = date.fromisoformat(deadline_str)
        return d >= date.today()
    except Exception:
        return True  # if missing, don’t block

def fallback_grants_gov_url(title: str, tags: List[str]) -> str:
    q = "+".join(_norm_words(title)[:6] + tags[:4])
    return f"https://www.grants.gov/search-results?keywords={q}"

def make_pdf(order_id: str, payload: Dict[str, Any]) -> str:
    pdf_path = os.path.join(OUTPUT_DIR, f"{order_id}.pdf")
    c = canvas.Canvas(pdf_path, pagesize=letter)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, 770, "GrantforgeUSA | Draft (TEST)")
    c.setFont("Helvetica", 10)
    c.drawString(50, 755, f"Order: {order_id}")
    c.drawString(50, 742, f"Created: {_now_utc()}")

    y = 720
    for k, v in payload.items():
        if y < 60:
            c.showPage(); y = 770
            c.setFont("Helvetica", 10)
        c.drawString(50, y, f"{k}: {v}")
        y -= 14
    c.showPage()
    c.save()
    return pdf_path

def price_for(category: str, annual_budget: float) -> float:
    c = (category or "").lower()
    if c.startswith("teacher"):
        return TEACHER_PRICE
    if annual_budget <= 500_000:
        return SMALL_PRICE
    if annual_budget <= 2_000_000:
        return MEDIUM_PRICE
    return LARGE_PRICE

def fraud_check(category: str, amount: float) -> Dict[str, Any]:
    """Simple guardrails by category. Return {ok: bool, msg: str}."""
    c = (category or "").lower()

    limits = []
    if c.startswith("teacher"):
        limits.append(("Teachers are limited to $15,000 per draft.", amount <= 15_000))
    elif "school" in c or "district" in c:
        limits.append(("Schools/Districts are limited to $250,000 per draft.", amount <= 250_000))
    elif "church" in c or "faith" in c:
        limits.append(("Faith orgs are limited to $150,000 per draft.", amount <= 150_000))
    elif "501" in c or "nonprofit" in c:
        limits.append(("Nonprofits are limited to $500,000 per draft.", amount <= 500_000))
    else:
        limits.append(("Other orgs are limited to $350,000 per draft.", amount <= 350_000))

    for msg, ok in limits:
        if not ok:
            return {"ok": False, "msg": msg}
    if amount <= 0:
        return {"ok": False, "msg": "Requested amount must be greater than 0."}
    return {"ok": True, "msg": ""}

def score_grant(gr: Dict[str, Any], category: str, kws: List[str], amount: float) -> Dict[str, Any]:
    score = 0
    fit_notes = []

    # category
    elig = [e.lower() for e in gr.get("eligible_types", [])]
    if any(t in (category or "").lower() for t in elig):
        score += 2
    else:
        fit_notes.append("Category not an explicit match")

    # amount window
    min_amt = _safe_float(gr.get("min_amount"), 0.0)
    max_amt = _safe_float(gr.get("max_amount"), 10**12)
    if amount < min_amt:
        fit_notes.append(f"Ask (${amount:,.0f}) is below minimum (${min_amt:,.0f})")
    elif amount > max_amt:
        fit_notes.append(f"Ask (${amount:,.0f}) exceeds maximum (${max_amt:,.0f})")
    else:
        score += 2

    # keywords vs tags
    tags = [t.lower() for t in gr.get("tags", [])]
    overlap = set(kws) & set(tags)
    score += min(len(overlap), 3)  # up to +3

    # deadline
    if _deadline_ok(gr.get("deadline", "")):
        score += 1
    else:
        fit_notes.append("Deadline has passed")

    # match %
    req_match = int(gr.get("requires_match_percent", 0) or 0)
    if req_match > 0:
        fit_notes.append(f"Requires {req_match}% match")

    fit = "High" if score >= 5 else "Medium" if score >= 3 else "Low"
    return {"score": score, "fit": fit, "fit_notes": "; ".join(fit_notes)}

def shortlist(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    grants = _read_json(GRANTS_PATH) or []
    category = payload.get("category") or payload.get("who") or ""
    amount = _safe_float(payload.get("amountRequested"))
    kws = _norm_words(payload.get("keywords", ""))

    rows = []
    for gr in grants:
        s = score_grant(gr, category, kws, amount)
        if s["fit"] == "Low":
            continue
        url = gr.get("program_url") or fallback_grants_gov_url(gr.get("title", ""), gr.get("tags", []))
        rows.append({
            "title": gr.get("title"),
            "program": gr.get("program") or gr.get("program_id") or gr.get("program_url") or "unknown",
            "program_url": url,
            "amount": f"${int(_safe_float(gr.get('max_amount'), 0)):,.0f}",
            "deadline": gr.get("deadline", "TBA"),
            "fit": s["fit"],
            "fit_notes": s["fit_notes"],
            "requires_match_percent": gr.get("requires_match_percent", 0),
            "max_amount": _safe_float(gr.get("max_amount"), 0),
        })
    # order: High first, then Medium
    rows.sort(key=lambda r: (0 if r["fit"] == "High" else 1, -_safe_float(r.get("max_amount"), 0)))
    return rows[:3]  # show top 3

def append_payment_log(row: Dict[str, Any]) -> str:
    path = os.path.join(OUTPUT_DIR, "payments_log.csv")
    try:
        if os.path.exists(path):
            df = pd.read_csv(path)
            df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
        else:
            df = pd.DataFrame([row])
        df.to_csv(path, index=False)
    except Exception:
        pass
    return path

def find_log_by_session(session_id: str) -> Dict[str, Any]:
    path = os.path.join(OUTPUT_DIR, "payments_log.csv")
    try:
        if not os.path.exists(path):
            return {}
        df = pd.read_csv(path)
        hit = df.loc[df["session_id"] == session_id]
        if hit.empty:
            return {}
        return hit.iloc[0].to_dict()
    except Exception:
        return {}

# ---------------- health ----------------
@app.get("/")
def home():
    return "<h2>GrantforgeUSA v11 Backend</h2><p>Status: OK</p>"

@app.get("/get/health")
def get_health():
    return jsonify(ok=True, publishableKey=bool(PUBLISHABLE_KEY), frontendUrl=FRONTEND_URL, ts=_now_utc())

# ---------------- shortlist ----------------
@app.post("/questionnaire")
def questionnaire():
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify(ok=False, error="Invalid JSON"), 400

    org = (data.get("organization") or "Your Organization").strip()
    results = shortlist(data)
    return jsonify(ok=True, organization=org, results=results)

# ---------------- draft stub (improved preview text) ----------------
@app.post("/preview")
def preview():
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify(ok=False, error="Invalid JSON"), 400

    org = (data.get("organization") or "Your Organization").strip()
    topic = (data.get("keywords") or "").strip()
    title = (data.get("projectTitle") or "Proposed initiative").strip()
    audience = (data.get("audience") or "").strip()
    timeline = (data.get("timeline") or "").strip()
    amount = _safe_float(data.get("amountRequested"))

    summary = (
        f"{org} proposes “{title},” a focused initiative aligned with {topic or 'community needs'}. "
        f"The project requests ${amount:,.0f} to support materials, coordination, and participant-facing activities. "
        f"Primary beneficiaries: {audience or 'local community'}. Timeline: {timeline or 'TBA'}."
    )
    return jsonify(ok=True, summary=summary)

# ---------------- Stripe Checkout (test) ----------------
@app.post("/create-checkout-session")
def create_checkout_session():
    if not (stripe.api_key and PUBLISHABLE_KEY):
        return jsonify(ok=False, error="Stripe test keys are not configured"), 400

    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify(ok=False, error="Invalid JSON"), 400

    # intake
    org = (data.get("organization") or "Customer").strip()
    category = (data.get("category") or data.get("who") or "Other").strip()
    amount_req = _safe_float(data.get("amountRequested"))
    annual_budget = _safe_float(data.get("annualBudget"), 0)
    grant = data.get("grant") or {}  # selected grant row

    # fraud & amount sanity
    chk = fraud_check(category, amount_req)
    if not chk["ok"]:
        return jsonify(ok=False, error=chk["msg"]), 400
    max_amt = _safe_float(grant.get("max_amount"), 0)
    if max_amt and amount_req > max_amt:
        return jsonify(ok=False, error=f"Requested ${amount_req:,.0f} exceeds this program’s maximum (${max_amt:,.0f})."), 400

    # price
    price = price_for(category, annual_budget)
    product_name = f"Grant Draft — {category}"

    # order id + metadata
    order_id = datetime.utcnow().strftime("ORD-%Y%m%d-%H%M%S-%f")
    metadata = {
        "order_id": order_id,
        "org": org,
        "category": category,
        "amountRequested": f"{amount_req:.2f}",
        "annualBudget": f"{annual_budget:.2f}",
        "grant_title": grant.get("title", ""),
        "grant_program": grant.get("program", ""),
        "grant_deadline": grant.get("deadline", ""),
        "grant_url": grant.get("program_url", ""),
        "price": f"{price:.2f}",
    }

    # create checkout
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
            cancel_url=f"{FRONTEND_URL}",
            metadata=metadata,
        )
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 400

    # write log
    row = {
        "ts_utc": _now_utc(),
        "order_id": order_id,
        "org": org,
        "category": category,
        "amountRequested": amount_req,
        "annualBudget": annual_budget,
        "grant_title": metadata["grant_title"],
        "grant_program": metadata["grant_program"],
        "session_id": session.id,
        "session_url": session.url,
        "price": price,
        "pdf_path": "",  # updated below
    }
    append_payment_log(row)

    # eager PDF (best effort)
    try:
        pdf_path = make_pdf(order_id, metadata)
        # update the row with pdf_path
        try:
            path = os.path.join(OUTPUT_DIR, "payments_log.csv")
            df = pd.read_csv(path)
            ix = df.index[df["order_id"] == order_id]
            if len(ix) > 0:
                df.loc[ix, "pdf_path"] = pdf_path
                df.to_csv(path, index=False)
        except Exception:
            pass
    except Exception:
        pass

    return jsonify(ok=True, url=session.url, sessionId=session.id, publishableKey=PUBLISHABLE_KEY)

# Reliable PDF fetch by Stripe session id
@app.get("/download-by-session")
def download_by_session():
    session_id = request.args.get("session_id")
    if not session_id:
        return jsonify(ok=False, error="missing session_id"), 400

    # try log first
    row = find_log_by_session(session_id)

    # if not found or missing metadata, look up Stripe and rebuild
    if not row:
        try:
            s = stripe.checkout.Session.retrieve(session_id)
        except Exception as e:
            return jsonify(ok=False, error=f"Stripe lookup failed: {e}"), 400
        md = s.metadata or {}
        order_id = md.get("order_id") or datetime.utcnow().strftime("ORD-%Y%m%d-%H%M%S-%f")
        payload = dict(md)
        pdf_path = make_pdf(order_id, payload)
        append_payment_log({
            "ts_utc": _now_utc(),
            "order_id": order_id,
            "org": md.get("org", ""),
            "category": md.get("category", ""),
            "amountRequested": float(md.get("amountRequested", 0)),
            "annualBudget": float(md.get("annualBudget", 0)),
            "grant_title": md.get("grant_title", ""),
            "grant_program": md.get("grant_program", ""),
            "session_id": session_id,
            "session_url": "", "price": float(md.get("price", 0)), "pdf_path": pdf_path
        })
        return send_file(pdf_path, as_attachment=True)

    # row found: build if missing
    pdf_path = row.get("pdf_path") or ""
    if not (pdf_path and os.path.exists(pdf_path)):
        # rebuild from Stripe metadata
        try:
            s = stripe.checkout.Session.retrieve(session_id)
            md = s.metadata or {}
        except Exception as e:
            return jsonify(ok=False, error=f"Stripe lookup failed: {e}"), 400
        order_id = row.get("order_id") or md.get("order_id") or datetime.utcnow().strftime("ORD-%Y%m%d-%H%M%S-%f")
        payload = dict(md)
        pdf_path = make_pdf(order_id, payload)
        # persist
        try:
            path = os.path.join(OUTPUT_DIR, "payments_log.csv")
            df = pd.read_csv(path)
            ix = df.index[df["session_id"] == session_id]
            if len(ix) > 0:
                df.loc[ix, "pdf_path"] = pdf_path
                df.to_csv(path, index=False)
        except Exception:
            pass

    return send_file(pdf_path, as_attachment=True)
