# server.py — GrantforgeUSA v11 (TEST MODE)
# Flask API: health, shortlist with money-match scoring, Stripe (test), success/cancel pages

import os
import json
from datetime import datetime
from typing import List, Dict, Any

from flask import Flask, request, jsonify
from flask_cors import CORS
import stripe

# ----------------------------- CONFIG -----------------------------

# Where to redirect after Stripe checkout.
# IMPORTANT: point this to the BACKEND so you don't hit Vercel 404s.
REDIRECT_BASE = os.getenv("REDIRECT_BASE", "https://grantforgeusa-v11-backend.onrender.com")

# Your static frontend (only used for metadata/health display if you want it)
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://grantforge-usav-11.vercel.app")

# Stripe test keys (ok to be missing during shortlist tests; required for checkout)
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")            # sk_test_...
PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")      # pk_test_...

# Draft pricing rules (per-draft)
TEACHER_PRICE = 9.99
SMALL_PRICE = 49.99        # ≤ $500k annual budget
MEDIUM_PRICE = 99.99       # $500k–$2M
LARGE_PRICE = 199.99       # > $2M

# Data file (grants library)
DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "grants.json")

# ----------------------------- APP -----------------------------

app = Flask(__name__)
# Wide open for private beta; tighten later:
# CORS(app, origins=["https://grantforge-usav-11.vercel.app"])
CORS(app, origins="*")

# ----------------------------- DATA -----------------------------

def _fallback_grants() -> List[Dict[str, Any]]:
    """A tiny backup library if data/grants.json isn't found."""
    return [
        {
            "title": "Community Support Microgrant",
            "program_url": "https://example.org/csm",
            "deadline": "2025-12-31",
            "min_amount": 1000,
            "max_amount": 5000,
            "eligible_types": ["501c3", "church", "school", "small_business", "city"],
            "tags": ["community", "outreach", "equipment"],
            "requires_match_percent": 0,
            "geo_scope": "US",
        },
        {
            "title": "Career & Technical Education Tools",
            "program_url": "https://example.org/cte",
            "deadline": "2025-11-30",
            "min_amount": 2500,
            "max_amount": 25000,
            "eligible_types": ["school", "teacher"],
            "tags": ["STEM", "CTE", "equipment", "classroom", "robotics"],
            "requires_match_percent": 0,
            "geo_scope": "US",
        },
        {
            "title": "Neighborhood Outreach Mini-Grant",
            "program_url": "https://example.org/neigh",
            "deadline": "2026-02-28",
            "min_amount": 500,
            "max_amount": 2500,
            "eligible_types": ["church", "501c3"],
            "tags": ["outreach", "shelter", "food"],
            "requires_match_percent": 0,
            "geo_scope": "US",
        },
        {
            "title": "Small Business Innovation Seed",
            "program_url": "https://example.org/sbi",
            "deadline": "2025-12-15",
            "min_amount": 5000,
            "max_amount": 15000,
            "eligible_types": ["small_business", "medium_business"],
            "tags": ["equipment", "innovation", "manufacturing", "R&D"],
            "requires_match_percent": 25,
            "geo_scope": "US",
        },
    ]

def load_grants() -> List[Dict[str, Any]]:
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "grants" in data:
                return data["grants"]
    except Exception:
        pass
    return _fallback_grants()

GRANTS = load_grants()

# ----------------------------- UTILS -----------------------------

# Normalize UI "who" categories into machine keys used by grants JSON
WHO_TO_KEY = {
    "Teacher (Classroom)": "teacher",
    "School (Public/Private)": "school",
    "501(c)(3) Nonprofit": "501c3",
    "Church / Faith-based": "church",
    "Small Business (≤ $500k)": "small_business",
    "Medium Business ($500k–$2M)": "medium_business",
    "Large Organization ($2M+)": "large_org",
    "City / Municipality": "city",
}

def compute_price(who: str, annual_budget: float) -> float:
    if who == "Teacher (Classroom)":
        return TEACHER_PRICE
    try:
        b = float(annual_budget or 0)
    except Exception:
        b = 0
    if b <= 500000:
        return SMALL_PRICE
    if b <= 2000000:
        return MEDIUM_PRICE
    return LARGE_PRICE

def score_match(
    grant: Dict[str, Any],
    who_key: str,
    keywords: List[str],
    requested: float,
    requires_cash: float | None,
) -> float:
    """
    0..1 score. Combines:
      - eligibility type (hard gate: if not eligible => 0)
      - keyword overlap (simple Jaccard-like)
      - requested amount sanity (within min/max => boost)
      - cash match feasibility (if grant requires match, penalize if none stated)
    """
    # Hard eligibility check
    elig = grant.get("eligible_types", [])
    if elig and who_key and (who_key not in elig):
        return 0.0

    # Keyword overlap
    tags = [t.lower() for t in grant.get("tags", [])]
    kws = [k.strip().lower() for k in keywords if k.strip()]
    kw_score = 0.0
    if kws:
        overlap = len(set(kws) & set(tags))
        kw_score = overlap / max(1, len(set(kws)))

    # Amount sanity
    req = float(requested or 0)
    min_amt = float(grant.get("min_amount") or 0)
    max_amt = float(grant.get("max_amount") or 0)
    amt_score = 0.0
    if req > 0 and (min_amt > 0 or max_amt > 0):
        if min_amt <= req <= max_amt:
            amt_score = 1.0
        elif max_amt > 0:
            # decay if above max or below min
            diff = abs(req - max_amt if req > max_amt else min_amt - req)
            span = max(1.0, (max_amt - min_amt) or max_amt or min_amt)
            amt_score = max(0.0, 1.0 - (diff / span))
        else:
            amt_score = 0.5  # unknown range

    # Cash match handling
    required_match = grant.get("requires_match_percent", 0)
    match_score = 1.0
    if isinstance(required_match, (int, float)) and required_match > 0:
        # If user didn't provide a cash match % (requires_cash is None), penalize
        if requires_cash is None:
            match_score = 0.6
        else:
            # If provided cash% >= required%, good. Otherwise proportional penalty.
            rp = float(requires_cash or 0)
            match_ratio = min(1.0, rp / float(required_match))
            match_score = 0.6 + 0.4 * match_ratio  # between 0.6 and 1.0

    # Weighted sum
    # eligibility gate applied already; now combine soft factors
    score = (0.55 * kw_score) + (0.35 * amt_score) + (0.10 * match_score)
    return max(0.0, min(1.0, score))

# ----------------------------- ROUTES -----------------------------

@app.get("/")
def home():
    return "<h2>GrantforgeUSA v11 Backend</h2><p>Status: OK</p>"

@app.get("/get/health")
def get_health():
    return jsonify(
        ok=True,
        ts=datetime.utcnow().isoformat() + "Z",
        frontendUrl=FRONTEND_URL,
        redirectBase=REDIRECT_BASE,
        publishableKey=bool(PUBLISHABLE_KEY),
        grants=len(GRANTS),
    )

@app.post("/find-grants")
def find_grants():
    """
    Request JSON:
    {
      "organization": "...",
      "who": "Teacher (Classroom)" | "...",
      "keywords": "comma, list",
      "amountRequested": 2500,
      "annualBudget": 60000,
      "projectTitle": "...",
      "timeline": "...",
      "audience": "...",
      "notes": "...",
      "cashMatchPercent": 10    # optional numeric % available from client
    }
    """
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify(ok=False, error="Invalid JSON"), 400

    who = (data.get("who") or "").strip()
    who_key = WHO_TO_KEY.get(who, "")
    keywords = (data.get("keywords") or "")
    kw_list = [k.strip() for k in keywords.split(",")] if isinstance(keywords, str) else (keywords or [])

    requested = float(data.get("amountRequested") or 0)
    cash_match_percent = data.get("cashMatchPercent")  # may be None

    results = []
    for g in GRANTS:
        s = score_match(g, who_key, kw_list, requested, cash_match_percent)
        if s <= 0:
            continue
        item = dict(g)
        item["match_score"] = round(float(s), 4)
        results.append(item)

    # Sort by match_score desc, then nearest deadline
    def _deadline_key(d):
        try:
            return datetime.fromisoformat(d)
        except Exception:
            return datetime.max

    results.sort(key=lambda r: (-r.get("match_score", 0.0), _deadline_key(r.get("deadline", "9999-12-31"))))
    return jsonify(ok=True, results=results[:10])

@app.post("/create-checkout-session")
def create_checkout_session():
    """Start a Stripe Checkout (test mode)."""
    if not (stripe.api_key and PUBLISHABLE_KEY):
        return jsonify(ok=False, error="Stripe test keys are not configured"), 400

    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify(ok=False, error="Invalid JSON"), 400

    name = (data.get("name") or "Client").strip()
    who = (data.get("category") or data.get("who") or "General").strip()
    is_teacher = bool(data.get("isTeacher"))
    annual_budget = float(data.get("annualBudget") or 0)

    # Derive price
    price = TEACHER_PRICE if is_teacher else compute_price(who, annual_budget)
    product_name = f"Grant Draft — {who}"

    order_id = datetime.utcnow().strftime("ORD-%Y%m%d-%H%M%S-%f")
    metadata = {
        "order_id": order_id,
        "name": name,
        "category": who,
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
                    "unit_amount": int(round(price * 100)),
                },
                "quantity": 1,
            }],
            success_url=f"{REDIRECT_BASE}/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{REDIRECT_BASE}/cancel",
            metadata=metadata,
        )
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 400

    return jsonify(ok=True, url=session.url, sessionId=session.id, publishableKey=PUBLISHABLE_KEY)

@app.get("/success")
def success():
    session_id = request.args.get("session_id", "")
    return (
        "<h3>✅ Payment Success!</h3>"
        f"<p>Session ID: {session_id}</p>"
        "<p>You may close this tab and return to GrantForgeUSA.</p>"
    )

@app.get("/cancel")
def cancel():
    return "<h3>❌ Payment Cancelled</h3><p>No charge was made.</p>"

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

# ----------------------------- MAIN -----------------------------

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
