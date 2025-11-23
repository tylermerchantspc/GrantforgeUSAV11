# GrantforgeUSA — v11.2 backend (TEST/LIVE READY)
# Purpose: shortlist w/ real matching + fraud checks, Stripe checkout,
#          REAL narrative draft generation, reliable PDF download
#          (eager + webhook), contextual previews, and debug utilities.

import os, json, glob
from datetime import datetime, date
from typing import Dict, Any, List, Optional, Tuple

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import stripe
from dotenv import load_dotenv

# PDF / data helpers
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import pandas as pd

# ---------------- bootstrap env ----------------
load_dotenv()

FRONTEND_URL = os.getenv("FRONTEND_URL", "https://grantforge-usav-11.vercel.app")
FRONTEND_THANKS_URL = os.getenv("FRONTEND_THANKS_URL", f"{FRONTEND_URL}/thanks")

# Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")            # sk_test_... / sk_live_...
PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")      # pk_test_... / pk_live_...
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "") # whsec_...

APP_MODE = os.getenv("APP_MODE", "test").lower()  # "test" | "live"

# ===== Writable storage (Render dynos can only write to /tmp) =====
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "/tmp/grantforge_v11")
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

# Env-configurable CORS:
# - default: "*" (easy testing)
# - set CORS_ORIGINS="https://yourlivefrontend.com" for locked-down live
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")
if CORS_ORIGINS == "*":
    CORS(app, origins="*")
else:
    CORS(app, origins=[o.strip() for o in CORS_ORIGINS.split(",") if o.strip()])


# ---------------- helpers ----------------
def cents(x: float) -> int:
    return int(round(float(x) * 100))


def _now_utc() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _read_json(path: str) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _norm_words(s: str) -> List[str]:
    return [w.strip().lower() for w in (s or "").replace(",", " ").split() if w.strip()]


def _safe_float(x, default=0.0) -> float:
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


def _is_expired(deadline_str: str) -> bool:
    try:
        d = date.fromisoformat(deadline_str)
        return d < date.today()
    except Exception:
        return False


def fallback_grants_gov_url(title: str, tags: List[str]) -> str:
    # robust Grants.gov search endpoint
    q = "+".join(_norm_words(title)[:6] + [t.lower() for t in (tags or [])][:4])
    return f"https://www.grants.gov/search-grants?keywords={q}"


# -------- URL normalizer (force Grants.gov or fallback to its search) --------
def _ensure_http_url(url: str, title: str, tags: List[str]) -> str:
    if isinstance(url, str) and url.startswith(("http://", "https://")) and "grants.gov" in url:
        return url
    return fallback_grants_gov_url(title or "", tags or [])


def _pdf_header_mode_note() -> str:
    return "TEST MODE" if APP_MODE != "live" else "LIVE"


def _wrap_draw_line(c: canvas.Canvas, text: str, start_x: int, y: int, width_chars: int = 110) -> int:
    """
    Draw a long line with naive wrapping; returns new y.
    """
    line = text
    while len(line) > width_chars:
        c.drawString(start_x, y, line[:width_chars])
        line = line[width_chars:]
        y -= 14
    c.drawString(start_x, y, line)
    return y - 14


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
    limits: List[Tuple[str, bool]] = []

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
    fit_notes: List[str] = []

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
    include_expired = bool(payload.get("includeExpired"))  # default hides expired

    rows = []
    for gr in grants:
        # hide expired unless explicitly requested
        if not include_expired and _is_expired(gr.get("deadline", "")):
            continue

        s = score_grant(gr, category, kws, amount, state)
        if s["fit"] == "Low":
            continue

        url = _ensure_http_url(gr.get("program_url", ""), gr.get("title", ""), gr.get("tags", []))
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
            "tags": gr.get("tags", []),
        })

    rows.sort(key=lambda r: (0 if r["fit"] == "High" else 1, -_safe_float(r.get("max_amount"), 0)))
    return rows[:3]  # top 3 for concise UI


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


# -------- contextual preview helpers --------
def _mk_objectives_from_keywords(kws: List[str], audience: str) -> List[str]:
    # turn user keywords into concrete, de-duplicated objectives
    uniq = []
    for k in kws:
        if k and k not in uniq:
            uniq.append(k)
    out = []
    if not uniq:
        return out
    # map common terms -> concrete actions
    for k in uniq[:4]:
        if k in ("stem", "robotics", "technology", "tech"):
            out.append(f"Purchase starter robotics/tech kits and integrate weekly {k.upper()} labs for {audience or 'participants'}.")
        elif k in ("equipment", "supplies"):
            out.append("Acquire durable classroom equipment and consumable supplies required to deliver activities.")
        elif k in ("training", "workshop", "professional", "professional development", "pd"):
            out.append("Provide teacher/staff PD workshops to ensure safe, effective program delivery.")
        elif k in ("after-school", "afterschool", "tutoring"):
            out.append("Launch a structured after-school tutoring/enrichment block with pre/post skill checks.")
        elif k in ("cte", "workforce"):
            out.append("Align activities to CTE/workforce competencies with employer input and mock assessments.")
        else:
            out.append(f"Implement targeted activities related to “{k}” with measurable outputs.")
    return out


def _mk_evaluation_lines(audience: str) -> List[str]:
    who = audience or "participants"
    return [
        f"Track attendance and dosage for all {who}.",
        "Use short pre/post assessments tied to lesson objectives.",
        "Collect teacher/facilitator observations and student feedback.",
    ]


def build_draft_text(intake: Dict[str, Any], grant: Dict[str, Any]) -> str:
    """
    Build a structured narrative draft from intake + grant.
    Used for both preview (shortened) and full paid draft PDF.
    """
    org = (intake.get("organization") or "Your Organization").strip()
    proj_title = (intake.get("projectTitle") or "Proposed initiative").strip()
    audience = (intake.get("audience") or "").strip() or "participants"
    timeline = (intake.get("timeline") or "TBA").strip()
    notes = (intake.get("notes") or "").strip()
    category = (intake.get("category") or intake.get("who") or "organization").strip()

    amount = _safe_float(intake.get("amountRequested"))
    annual_budget = _safe_float(intake.get("annualBudget"), 0)
    keywords_str = (intake.get("keywords") or "").strip()
    kws = _norm_words(keywords_str)

    g_title = grant.get("title") or "Selected opportunity"
    g_deadline = grant.get("deadline") or "TBA"
    g_match = int(grant.get("requires_match_percent", 0) or 0)
    g_max = _safe_float(grant.get("max_amount"), 0)
    g_tags = grant.get("tags", []) or []

    if amount > 0:
        req_str = f"approximately ${amount:,.0f}"
    else:
        req_str = "a competitive grant amount aligned with program guidance"

    if annual_budget > 0:
        budget_str = f"with an estimated annual operating budget of ${annual_budget:,.0f}."
    else:
        budget_str = "with a modest operating budget and clear stewardship of funds."

    focus_str = keywords_str or "addressing clearly documented local needs"
    tag_phrase = ", ".join(g_tags[:4]) if g_tags else "the funder’s stated priorities"

    # Objectives & evaluation
    objectives = _mk_objectives_from_keywords(kws, audience)
    evaluation = _mk_evaluation_lines(audience)

    # 1) Project Summary
    p1 = (
        f"{org} proposes “{proj_title}” to support {audience} through activities focused on {focus_str}. "
        f"The project will request {req_str} under the {g_title} opportunity, "
        f"with an implementation timeline of {timeline}. "
        f"The applicant currently operates as {category} {budget_str}"
    )

    # 2) Need Statement
    if notes:
        need_body = notes
    else:
        need_body = (
            f"The target population faces barriers related to limited access to high-quality resources, "
            f"programming, and supports. Without targeted investment, {audience} are less likely to "
            f"receive consistent, structured services that improve outcomes over time."
        )
    p2 = (
        "There is a clear documented need for this project. "
        + need_body
    )

    # 3) Objectives
    if not objectives:
        objectives = [
            "Increase access to high-quality programming connected to the grant’s priorities.",
            "Improve participant engagement and measurable outcomes over the project period.",
            "Strengthen the applicant’s capacity to sustain successful activities beyond the grant term.",
        ]

    obj_lines = []
    for i, line in enumerate(objectives, 1):
        obj_lines.append(f"{i}. {line}")
    p3 = "Project Objectives:\n" + "\n".join(obj_lines)

    # 4) Key Activities
    act_lines = [
        "Design and deliver structured sessions aligned to clear lesson or activity plans.",
        "Coordinate staffing, scheduling, and communication with participating stakeholders.",
        "Integrate family, community, or partner engagement where appropriate.",
    ]
    if "after-school" in keywords_str.lower() or "afterschool" in keywords_str.lower():
        act_lines.append("Offer after-school programming with safe supervision, enrichment, and academic support.")
    if "stem" in keywords_str.lower() or "robotics" in keywords_str.lower():
        act_lines.append("Implement hands-on STEM/robotics activities that build problem-solving and teamwork skills.")
    p4 = "Key Activities & Approach:\n" + "\n".join(f"- {l}" for l in act_lines)

    # 5) Budget Summary
    budget_lines = [
        "Grant funds will be used for allowable costs such as materials, supplies, limited equipment, and staffing.",
        "The applicant will follow all federal, state, and local procurement and fiscal accountability requirements.",
    ]
    if g_match > 0:
        budget_lines.append(
            f"The applicant will meet the required {g_match}% match through eligible in-kind or cash contributions."
        )
    if g_max > 0 and amount > 0:
        budget_lines.append(
            f"The requested amount of {req_str} falls within the program’s published range (up to ${g_max:,.0f}, as applicable)."
        )
    p5 = "Budget Summary:\n" + "\n".join(f"- {l}" for l in budget_lines)

    # 6) Evaluation Plan
    eval_lines = []
    for i, line in enumerate(evaluation, 1):
        eval_lines.append(f"{i}. {line}")
    p6 = "Evaluation Plan:\n" + "\n".join(eval_lines)

    # 7) Alignment with Funder Priorities
    align_text = (
        f"This project aligns with {g_title} by advancing activities related to {tag_phrase}. "
        f"All proposed activities and costs will adhere to program guidance, applicable regulations, "
        f"and ethical standards. The applicant understands that this draft is a starting point and will "
        f"review, refine, and customize language prior to any final submission."
    )
    deadline_note = f"The current anticipated deadline is {g_deadline}."
    p7 = align_text + " " + deadline_note

    return "\n\n".join([p1, p2, p3, p4, p5, p6, p7])


def make_pdf(order_id: str, payload: Dict[str, Any]) -> str:
    """
    Generate a PDF from the given payload.
    If 'draft_body' is present, render a structured narrative + order details.
    Otherwise, fall back to key/value listing (legacy).
    """
    os.makedirs(PDF_DIR, exist_ok=True)  # ensure exists at write time
    pdf_path = os.path.join(PDF_DIR, f"{order_id}.pdf")
    c = canvas.Canvas(pdf_path, pagesize=letter)

    # Header
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, 770, f"GrantforgeUSA | Draft ({_pdf_header_mode_note()})")
    c.setFont("Helvetica", 10)
    c.drawString(50, 755, f"Order: {order_id}")
    c.drawString(50, 742, f"Created: {_now_utc()}")

    # Body
    y = 720
    c.setFont("Helvetica", 10)

    draft_body = payload.get("draft_body")
    if isinstance(draft_body, str) and draft_body.strip():
        # Narrative first
        c.setFont("Helvetica-Bold", 11)
        y = _wrap_draw_line(c, "Draft Narrative", 50, y)
        c.setFont("Helvetica", 10)

        for para in draft_body.split("\n\n"):
            for line in para.split("\n"):
                if y < 60:
                    c.showPage()
                    y = 770
                    c.setFont("Helvetica", 10)
                y = _wrap_draw_line(c, line, 50, y)
            y -= 6  # small extra spacing between paragraphs

        # Order details
        if y < 80:
            c.showPage()
            y = 770
            c.setFont("Helvetica", 10)

        c.setFont("Helvetica-Bold", 11)
        y = _wrap_draw_line(c, "Order Details", 50, y)
        c.setFont("Helvetica", 10)

        for k in sorted(payload.keys()):
            if k == "draft_body":
                continue
            v = payload[k]
            if y < 60:
                c.showPage()
                y = 770
                c.setFont("Helvetica", 10)
            y = _wrap_draw_line(c, f"{k}: {v}", 50, y)
    else:
        # Legacy: just dump payload keys (should be rare now)
        for k in sorted(payload.keys()):
            v = payload[k]
            if y < 60:
                c.showPage()
                y = 770
                c.setFont("Helvetica", 10)
            y = _wrap_draw_line(c, f"{k}: {v}", 50, y)

    # Footer
    if y < 80:
        c.showPage()
        y = 770
        c.setFont("Helvetica", 10)

    c.setFont("Helvetica-Oblique", 9)
    c.drawString(50, 50, "Psalm 127:1 — Built with Faith. AI-generated draft; not an award or guarantee.")
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
    return jsonify(ok=True, offline=False, ts=_now_utc())


@app.get("/get/debug-paths")
def get_debug_paths():
    """
    Diagnostics to verify file locations on Render and confirm PDF existence.
    """
    try:
        pdf_files = sorted(glob.glob(os.path.join(PDF_DIR, "*.pdf")), key=os.path.getmtime, reverse=True)
        pdf_tail = [os.path.basename(p) for p in pdf_files[:10]]

        log_exists = os.path.exists(LOG_PATH)
        log_size = os.path.getsize(LOG_PATH) if log_exists else 0

        return jsonify(
            ok=True,
            outputDir=OUTPUT_DIR,
            pdfDir=PDF_DIR,
            pdfDirExists=os.path.isdir(PDF_DIR),
            pdfTail=pdf_tail,
            logPath=LOG_PATH,
            logExists=log_exists,
            logSize=log_size,
            grantsPath=GRANTS_PATH,
            ts=_now_utc(),
        )
    except Exception as e:
        return jsonify(ok=False, error=str(e), ts=_now_utc()), 500


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


@app.post("/search")
def search():
    return questionnaire()


# ---------------- contextual preview ----------------
@app.post("/preview")
def preview():
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify(ok=False, error="Invalid JSON"), 400

    grant = data.get("grant") or {}
    if not grant:
        short = shortlist(data)
        if short:
            grant = short[0]

    # Build full draft, then shorten for preview
    full_draft = build_draft_text(data, grant)
    paras = full_draft.split("\n\n")
    preview_text = "\n\n".join(paras[:4])  # first few sections only

    return jsonify(ok=True, summary=preview_text)


# ---------------- Stripe Checkout ----------------
@app.post("/create-checkout-session")
def create_checkout_session():
    if not (stripe.api_key and PUBLISHABLE_KEY):
        return jsonify(ok=False, error="Stripe keys are not configured"), 400

    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify(ok=False, error="Invalid JSON"), 400

    org = (data.get("organization") or "Customer").strip()
    category = (data.get("category") or data.get("who") or "Other").strip()
    amount_req = _safe_float(data.get("amountRequested"))
    annual_budget = _safe_float(data.get("annualBudget"), 0)
    grant = data.get("grant") or {}

    chk = fraud_check(category, amount_req)
    if not chk["ok"]:
        return jsonify(ok=False, error=chk["msg"]), 400

    max_amt = _safe_float(grant.get("max_amount"), 0)
    if max_amt and amount_req > max_amt:
        return jsonify(
            ok=False,
            error=f"Requested ${amount_req:,.0f} exceeds this program’s maximum (${max_amt:,.0f})."
        ), 400

    price = price_for(category, annual_budget)
    product_name = f"Grant Draft — {category}"

    order_id = datetime.utcnow().strftime("ORD-%Y%m%d-%H%M%S-%f")

    # Build narrative draft now so PDF is ready immediately after checkout
    draft_body = build_draft_text(data, grant)

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
        "pdf_path": "",
        "paid": False,
        "draft_body": draft_body,
    }
    _append_payment_log_row(row)

    # eager PDF (from metadata + draft_body)
    try:
        pdf_payload = dict(metadata)
        pdf_payload["draft_body"] = draft_body
        pdf_path = make_pdf(order_id, pdf_payload)
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

    if event["type"] == "checkout.session.completed":
        session_obj = event["data"]["object"]
        session_id = session_obj.get("id")
        md = session_obj.get("metadata") or {}

        # If we already generated a PDF at checkout, just mark as paid
        row = find_log_by_session(session_id)
        if row and row.get("pdf_path") and os.path.exists(row["pdf_path"]):
            _update_payment_log_by("session_id", session_id, {"paid": True})
        else:
            # Fallback: generate a basic PDF from metadata + payment info
            order_id = md.get("order_id") or datetime.utcnow().strftime("ORD-%Y%m%d-%H%M%S-%f")
            payload_for_pdf = dict(md)
            payload_for_pdf.update({
                "stripe_session_id": session_id,
                "payment_status": session_obj.get("payment_status"),
                "amount_total": session_obj.get("amount_total"),
                "currency": session_obj.get("currency"),
                "mode": session_obj.get("mode"),
            })
            try:
                pdf_path = make_pdf(order_id, payload_for_pdf)
                _update_payment_log_by("session_id", session_id, {"pdf_path": pdf_path, "paid": True})
            except Exception:
                pass

    return jsonify(ok=True)


# ---------------- Receipt / Download ----------------
@app.get("/receipt")
def receipt():
    session_id = request.args.get("session_id") or request.args.get("sid")
    if not session_id:
        return jsonify(ok=False, error="missing session_id"), 400

    row = find_log_by_session(session_id)
    if not row:
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

    dl_url = f"/download-by-session?session_id={session_id}"
    return jsonify({
        "ok": True,
        "session_id": session_id,
        "order_id": row.get("order_id", ""),
        "email": "",
        "amount_total": row.get("price", 0),
        "paid": bool(row.get("paid", False)),
        "grant_title": row.get("grant_title", ""),
        "download_path": dl_url,
        "ts": _now_utc(),
    })


# ---------------- Hardened download-by-session (never 500) ----------------
@app.get("/download-by-session")
def download_by_session():
    try:
        session_id = request.args.get("session_id")
        if not session_id:
            return jsonify(ok=False, error="missing session_id"), 400

        def _safe_send(path, order_id_fallback="draft"):
            try:
                if not (path and os.path.exists(path)):
                    return jsonify(ok=False, error="PDF not found yet; try again in a moment."), 404
                name = os.path.basename(path) or f"{order_id_fallback}.pdf"
                return send_file(path, as_attachment=True, download_name=name, mimetype="application/pdf")
            except Exception as e:
                return jsonify(ok=False, error=f"send_file failed: {e}"), 400

        # 1) try log
        row = find_log_by_session(session_id)
        if row and row.get("pdf_path") and os.path.exists(row["pdf_path"]):
            return _safe_send(row["pdf_path"], row.get("order_id", "draft"))

        # 2) rebuild from Stripe metadata
        try:
            s = stripe.checkout.Session.retrieve(session_id)
            md = s.metadata or {}
        except Exception as e:
            return jsonify(ok=False, error=f"Stripe lookup failed: {e}"), 400

        order_id = (row.get("order_id") if row else None) or md.get("order_id") or datetime.utcnow().strftime("ORD-%Y%m%d-%H%M%S-%f")
        try:
            pdf_path = make_pdf(order_id, dict(md))
        except Exception as e:
            return jsonify(ok=False, error=f"PDF generation failed: {e}"), 400

        _update_payment_log_by("session_id", session_id, {
            "order_id": order_id,
            "pdf_path": pdf_path,
            "paid": s.get("payment_status") == "paid"
        })
        return _safe_send(pdf_path, order_id)

    except Exception as e:
        return jsonify(ok=False, error=f"download route error: {e}"), 400


# ------------- main (optional local run) -------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
