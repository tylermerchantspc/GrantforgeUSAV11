# GrantforgeUSA — v11 backend (TEST/LIVE READY)
# Purpose: shortlist w/ real matching + fraud checks, Stripe checkout, reliable PDF download (eager + webhook)

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
FRONTEND_THANKS_URL = os.getenv("FRONTEND_THANKS_URL", f"{FRONTEND_URL}/thanks")

# Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")          # sk_test_... / sk_live_...
PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")    # pk_test_... / pk_live_...
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")  # whsec_...

APP_MODE = os.getenv("APP_MODE", "test").lower()  # "test" | "live"

OUTPUT_DIR = os.getenv("OUTPUT_DIR", "v11_payment_data")
PDF_DIR = os.path.join(OUTPUT_DIR, "pdfs")
LOG_PATH = os.path.join(OUTPUT_DIR, "payments_log.csv")

DATA_DIR = os.getenv("DATA_DIR", "backend/data")
GRANTS_PATH = os.path.join(DATA_DIR, "grants.json")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(PDF_DIR, exist_ok=True)

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
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"

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

def _pdf_header_mode_note() -> str:
    return "TEST MODE" if APP_MODE != "live" else "LIVE"

def make_pdf(order_id: str, payload: Dict[str, Any]) -> str:
    """
    Generates a simple, reliable PDF from the given payload.
    """
    pdf_path = os.path.join(PDF_DIR, f"{order_id}.pdf")
    c = canvas.Canvas(pdf_path, pagesize=letter)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, 770, f"GrantforgeUSA | Draft ({_pdf_header_mode_note()})")
    c.setFont("Helvetica", 10)
    c.drawString(50, 755, f"Order: {order_id}")
    c.drawString(50, 742, f"Created: {_now_utc()}")

    y = 720
    for k, v in payload.items():
        if y < 60:
            c.showPage(); y = 770
            c.setFont("Helvetica", 10)
        line = f"{k}: {v}"
        # wrap long lines roughly
        while len(line) > 110:
            c.drawString(50, y, line[:110])
            line = line[110:]
            y -= 14
            if y < 60:
                c.showPage(); y = 770; c.setFont("Helvetica", 10)
        c.drawString(50, y, line)
        y -= 14

    # footer
    if y < 80:
        c.showPage(); y = 770; c.setFont("Helvetica", 10)
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(50, 50, "Psalm 127:1 — Built with Faith. AI-generated draft; not an award or guarantee.")
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

def score_grant(gr: Dict[str, Any], category: str, kws: List[str], amount: float, state: str) -> Dict[str, Any]:
    score = 0
    fit_notes = []

    # category eligibility
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

    # state/region (if data present)
    states = [s.lower() for s in gr.get("eligible_states", [])]
    if states and state and state.lower() not in states:
        fit_notes.append("State may not be eligible")
    elif states:
        score += 1

    # match % note
    req_match = int(gr.get("requires_match_percent", 0) or 0)
    if req_match > 0:
        fit_notes.append(f"Requires {req_match}% match")

    fit = "High" if score >= 6 else "Medium" if score >= 3 else "Low"
    return {"score": score, "fit": fit, "fit_notes": "; ".join(fit_notes)}

def shortlist(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    grants = _read_json(GRANTS_PATH) or []
    category = payload.get("category") or payload.get("who") or ""
    amount = _safe_float(payload.get("amountRequested"))
    kws = _norm_words(payload.get("keywords", ""))
    state = (payload.get("state") or "").strip()

    rows = []
    for gr in grants:
        s = score_grant(gr, category, kws, amount, state)
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
    # order: High first, then Medium; within, by max amount desc
    rows.sort(key=lambda r: (0 if r["fit"] == "High" else 1, -_safe_float(r.get("max_amount"), 0)))
    return rows[:3]  # top 3 keeps UI tight

def _append_payment_log_row(row: Dict[str, Any]) -> None:
    try:
        if os.path.exists(LOG_PATH):
            df = pd.read_csv(LOG_PATH)
            df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
        else:
            df = pd.DataFrame([row])
        df.to_csv(LOG_PATH, index=False)
    except Exception:
        pass

def _update_payment_log_by(key: str, value: str, patch: Dict[str, Any]) -> None:
    try:
        if not os.path.exists(LOG_PATH):
            return
        df = pd.read_csv(LOG_PATH)
        ix = df.index[df[key] == value]
        if len(ix) > 0:
            for k, v in patch.items():
                df.loc[ix, k] = v
            df.to_csv(LOG_PATH, index=False)
    except Exception:
        pass

def find_log_by_session(session_id: str) -> Dict[str, Any]:
    try:
        if not os.path.exists(LOG_PATH):
            return {}
        df = pd.read_csv(LOG_PATH)
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
    return jsonify(
        ok=True,
        mode=APP_MODE,
        publishableKey=bool(PUBLISHABLE_KEY),
        frontendThanksUrl=FRONTEND_THANKS_URL,
        ts=_now_utc()
    )

@app.get("/healthz")
def healthz():
    return jsonify(ok=True, ts=_now_utc())

@app.get("/get/offline")
def get_offline():
    # Always local-first; we treat external outages as non-blocking
    # You can enhance this to attempt a grants.gov HEAD and return True on failure.
    return jsonify(ok=True, offline=False, ts=_now_utc())


# ---------------- shortlist/search ----------------
@app.post("/questionnaire")
def questionnaire():
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify(ok=False, error="Invalid JSON"), 400

    org = (data.get("organization") or "Your Organization").strip()
    results = shortlist(data)
    return jsonify(ok=True, organization=org, results=results)

# Alias for frontend convenience
@app.post("/search")
def search():
    return questionnaire()


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


# ---------------- Stripe Checkout ----------------
@app.post("/create-checkout-session")
def create_checkout_session():
    if not (stripe.api_key and PUBLISHABLE_KEY):
        return jsonify(ok=False, error="Stripe keys are not configured"), 400

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
        "app_mode": APP_MODE,
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
            success_url=f"{FRONTEND_THANKS_URL}?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{FRONTEND_URL}",
            metadata=metadata,
        )
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 400

    # write log (pre-payment)
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
        "pdf_path": "",  # updated by eager gen or webhook
        "paid": False,
    }
    _append_payment_log_row(row)

    # eager PDF (best effort from metadata)
    try:
        pdf_path = make_pdf(order_id, metadata)
        _update_payment_log_by("order_id", order_id, {"pdf_path": pdf_path})
    except Exception:
        pass

    return jsonify(ok=True, url=session.url, sessionId=session.id, publishableKey=PUBLISHABLE_KEY)


# ---------------- Stripe Webhook (reliable post-payment) ----------------
@app.post("/webhook/stripe")
def stripe_webhook():
    if not STRIPE_WEBHOOK_SECRET:
        return jsonify(ok=False, error="Webhook secret not configured"), 400

    payload = request.data
    sig_header = request.headers.get("Stripe-Signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        return jsonify(ok=False, error=f"Signature verification failed: {e}"), 400

    # We only care about a few events for now
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        session_id = session.get("id")
        md = session.get("metadata") or {}
        order_id = md.get("order_id") or datetime.utcnow().strftime("ORD-%Y%m%d-%H%M%S-%f")

        # build reliable payload (prefer md)
        payload_for_pdf = dict(md)
        payload_for_pdf.update({
            "stripe_session_id": session_id,
            "payment_status": session.get("payment_status"),
            "amount_total": session.get("amount_total"),
            "currency": session.get("currency"),
            "mode": session.get("mode"),
        })

        # generate/overwrite PDF
        try:
            pdf_path = make_pdf(order_id, payload_for_pdf)
            _update_payment_log_by("session_id", session_id, {
                "pdf_path": pdf_path,
                "paid": True
            })
        except Exception:
            pass

    return jsonify(ok=True)


# ---------------- Receipt / Download ----------------
@app.get("/receipt")
def receipt():
    session_id = request.args.get("session_id") or request.args.get("sid")
    if not session_id:
        return jsonify(ok=False, error="missing session_id"), 400

    # Try to serve from log
    row = find_log_by_session(session_id)
    if not row:
        # attempt to pull Stripe data
        try:
            s = stripe.checkout.Session.retrieve(session_id)
            md = s.metadata or {}
        except Exception as e:
            return jsonify(ok=False, error=f"Stripe lookup failed: {e}"), 400

        order_id = md.get("order_id") or datetime.utcnow().strftime("ORD-%Y%m%d-%H%M%S-%f")
        pdf_path = os.path.join(PDF_DIR, f"{order_id}.pdf")
        if not os.path.exists(pdf_path):
            try:
                pdf_path = make_pdf(order_id, dict(md))
            except Exception:
                pdf_path = ""

        # cache a minimal row to speed up future calls
        _append_payment_log_row({
            "ts_utc": _now_utc(),
            "order_id": order_id,
            "org": md.get("org", ""),
            "category": md.get("category", ""),
            "amountRequested": float(md.get("amountRequested", 0) or 0),
            "annualBudget": float(md.get("annualBudget", 0) or 0),
            "grant_title": md.get("grant_title", ""),
            "grant_program": md.get("grant_program", ""),
            "session_id": session_id,
            "session_url": "",
            "price": float(md.get("price", 0) or 0),
            "pdf_path": pdf_path,
            "paid": s.get("payment_status") == "paid",
        })
        row = find_log_by_session(session_id)

    # synthesize receipt
    dl_url = f"/download-by-session?session_id={session_id}"
    result = {
        "ok": True,
        "session_id": session_id,
        "order_id": row.get("order_id", ""),
        "email": "",  # not collected in this flow; add later if needed
        "amount_total": row.get("price", 0),
        "paid": bool(row.get("paid", False)),
        "grant_title": row.get("grant_title", ""),
        "download_path": dl_url,
        "ts": _now_utc(),
    }
    return jsonify(result)

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
        _append_payment_log_row({
            "ts_utc": _now_utc(),
            "order_id": order_id,
            "org": md.get("org", ""),
            "category": md.get("category", ""),
            "amountRequested": float(md.get("amountRequested", 0) or 0),
            "annualBudget": float(md.get("annualBudget", 0) or 0),
            "grant_title": md.get("grant_title", ""),
            "grant_program": md.get("grant_program", ""),
            "session_id": session_id,
            "session_url": "",
            "price": float(md.get("price", 0) or 0),
            "pdf_path": pdf_path,
            "paid": s.get("payment_status") == "paid",
        })
        return send_file(pdf_path, as_attachment=True, download_name=f"{order_id}.pdf", mimetype="application/pdf")

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
        _update_payment_log_by("session_id", session_id, {"pdf_path": pdf_path})

    return send_file(pdf_path, as_attachment=True, download_name=os.path.basename(pdf_path), mimetype="application/pdf")


# ------------- main (optional local run) -------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
