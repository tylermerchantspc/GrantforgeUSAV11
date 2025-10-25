# server.py — GrantForgeUSA v11.2 (TEST MODE)
# API: health, find-grants (money match), Stripe (test), success/cancel

import os, json
from datetime import datetime
from typing import Any, Dict, List

from flask import Flask, request, jsonify
from flask_cors import CORS
import stripe

# ---------------- Config ----------------
# Stripe success/cancel MUST return to BACKEND to avoid Vercel 404
REDIRECT_BASE = os.getenv("REDIRECT_BASE", "https://grantforgeusa-v11-backend.onrender.com")
FRONTEND_URL  = os.getenv("FRONTEND_URL",  "https://grantforge-usav-11.vercel.app")

stripe.api_key   = os.getenv("STRIPE_SECRET_KEY")      # sk_test_...
PUBLISHABLE_KEY  = os.getenv("STRIPE_PUBLISHABLE_KEY") # pk_test_...

# Per-draft pricing
TEACHER_PRICE = 9.99
SMALL_PRICE   = 49.99     # ≤ $500k
MEDIUM_PRICE  = 99.99     # $500k–$2M
LARGE_PRICE   = 199.99    # > $2M

DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "grants.json")

# ---------------- App ----------------
app = Flask(__name__)
CORS(app, origins="*")  # OK for private beta; tighten later

# ---------------- Data ----------------
def _fallback() -> List[Dict[str, Any]]:
    return [
        {
            "title": "STEM Classroom Boost",
            "program_url": "https://example.org/stem-class",
            "deadline": "2026-01-31",
            "min_amount": 1000,
            "max_amount": 15000,
            "eligible_types": ["teacher","school"],
            "tags": ["STEM","classroom","supplies","robotics"],
            "requires_match_percent": 0
        },
        {
            "title": "Community Support Microgrant",
            "program_url": "https://example.org/csm",
            "deadline": "2025-12-31",
            "min_amount": 1000,
            "max_amount": 5000,
            "eligible_types": ["501c3","church","school","small_business","city"],
            "tags": ["community","outreach","equipment"],
            "requires_match_percent": 0
        },
        {
            "title": "Small Business Innovation Seed",
            "program_url": "https://example.org/sbi",
            "deadline": "2026-03-15",
            "min_amount": 5000,
            "max_amount": 25000,
            "eligible_types": ["small_business","medium_business"],
            "tags": ["equipment","innovation","manufacturing","R&D"],
            "requires_match_percent": 25
        },
        {
            "title": "Faith & Neighborhood Microgrant",
            "program_url": "https://example.org/fnm",
            "deadline": "2026-02-28",
            "min_amount": 1000,
            "max_amount": 7500,
            "eligible_types": ["church","501c3"],
            "tags": ["outreach","food","shelter"],
            "requires_match_percent": 0
        }
    ]

def load_grants() -> List[Dict[str, Any]]:
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else data.get("grants", _fallback())
    except Exception:
        return _fallback()

GRANTS = load_grants()

# ---------------- Utils ----------------
WHO_TO_KEY = {
    "Teacher (Classroom)": "teacher",
    "School (Public/Private)": "school",
    "501(c)(3) Nonprofit": "501c3",
    "Church / Faith-based": "church",
    "Small Business (≤ $500k)": "small_business",
    "Medium Business ($500k–$2M)": "medium_business",
    "Large Organization ($2M+)": "large_org",
    "City / Municipality": "city",
    "Community Club / Civic Group": "community",
}

def price_for(who: str, annual_budget: float) -> float:
    if who == "Teacher (Classroom)": return TEACHER_PRICE
    b = float(annual_budget or 0)
    if b <= 500000:  return SMALL_PRICE
    if b <= 2000000: return MEDIUM_PRICE
    return LARGE_PRICE

def score(grant: Dict[str, Any], who_key: str, kw_list: List[str], requested: float) -> float:
    # hard eligibility
    if who_key and grant.get("eligible_types") and who_key not in grant["eligible_types"]:
        return 0.0
    # keyword overlap
    tags = set(t.lower() for t in grant.get("tags", []))
    kws  = set(k.strip().lower() for k in kw_list if k.strip())
    kw_score = (len(tags & kws) / max(1, len(kws))) if kws else 0.6

    # amount fit
    req   = float(requested or 0)
    min_a = float(grant.get("min_amount") or 0)
    max_a = float(grant.get("max_amount") or 0)
    if req and (min_a or max_a):
        if min_a <= req <= max_a:
            money = 1.0
        else:
            span = max(1.0, (max_a - min_a) or max_a or min_a)
            diff = abs((req - max_a) if req > max_a else (min_a - req))
            money = max(0.0, 1.0 - (diff / span))
    else:
        money = 0.7

    # required cash match is informative only in this stub (not a hard fail)
    return max(0.0, min(1.0, 0.55*kw_score + 0.45*money))

# ---------------- Routes ----------------
@app.get("/")
def home():
    return "<h2>GrantForgeUSA v11.2 Backend</h2><p>Status: OK</p>"

@app.get("/get/health")
def get_health():
    return jsonify(ok=True, ts=datetime.utcnow().isoformat()+"Z",
                   frontendUrl=FRONTEND_URL, redirectBase=REDIRECT_BASE,
                   publishableKey=bool(PUBLISHABLE_KEY), grants=len(GRANTS))

@app.post("/find-grants")
def find_grants():
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify(ok=False, error="Invalid JSON"), 400

    who = (data.get("who") or data.get("category") or "").strip()
    who_key = WHO_TO_KEY.get(who, "")
    keywords = data.get("keywords") or ""
    kw_list = [k.strip() for k in keywords.split(",")] if isinstance(keywords, str) else (keywords or [])
    requested = float(data.get("amountRequested") or 0)

    results = []
    for g in GRANTS:
        s = score(g, who_key, kw_list, requested)
        if s <= 0:  # not eligible or no fit
            continue
        item = dict(g)
        item["fit"] = round(s*100)
        results.append(item)

    # sort by fit desc, then nearest deadline
    def _dl(d):
        try:
            return datetime.fromisoformat(d)
        except Exception:
            return datetime.max
    results.sort(key=lambda r: (-r.get("fit",0), _dl(r.get("deadline","9999-12-31"))))
    return jsonify(ok=True, results=results[:10])

# Back-compat for older FE posting to /questionnaire
@app.post("/questionnaire")
def questionnaire_alias():
    return find_grants()

@app.post("/create-checkout-session")
def create_checkout_session():
    if not (stripe.api_key and PUBLISHABLE_KEY):
        return jsonify(ok=False, error="Stripe test keys are not configured"), 400
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify(ok=False, error="Invalid JSON"), 400

    name       = (data.get("name") or "Client").strip()
    who        = (data.get("category") or data.get("who") or "General").strip()
    is_teacher = bool(data.get("isTeacher"))
    annual     = float(data.get("annualBudget") or 0.0)
    price      = TEACHER_PRICE if is_teacher else price_for(who, annual)

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
                    "product_data": {"name": f"Grant Draft — {who}"},
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
    sid = request.args.get("session_id", "")
    return (
        "<h3>✅ Payment Success!</h3>"
        f"<p>Session ID: {sid}</p>"
        "<p>You may close this tab and return to the app.</p>"
    )

@app.get("/cancel")
def cancel():
    return "<h3>❌ Payment Cancelled</h3><p>No charge was made.</p>"

@app.get("/session")
def session_status():
    sid = request.args.get("id")
    if not sid:
        return jsonify(ok=False, error="missing id"), 400
    try:
        s = stripe.checkout.Session.retrieve(sid)
        return jsonify(ok=True, status=s.status, payment_status=s.payment_status)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 400

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
