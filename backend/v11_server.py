# GrantforgeUSA — v11.4 backend (launch path)
# Purpose: shortlist w/ real matching + fraud checks, Stripe checkout,
#          REAL narrative draft generation, reliable PDF download
#          (eager + webhook), contextual previews, and debug utilities.

import os, json, glob, re, secrets, threading, time
from datetime import datetime, date, timedelta
from collections import defaultdict, deque
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

APP_MODE = os.getenv("APP_MODE", "test").lower()  # keep for environment-level behavior only

# ===== Writable storage (Render dynos can only write to /tmp) =====
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "/tmp/grantforge_v11")
PROTECTED_DIR = os.path.join(OUTPUT_DIR, "protected")
PDF_DIR = os.path.join(PROTECTED_DIR, "pdfs")
LOG_PATH = os.path.join(PROTECTED_DIR, "payments_log.csv")

DATA_DIR = os.getenv("DATA_DIR", "backend/data")
GRANTS_PATH = os.path.join(DATA_DIR, "grants.json")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(PROTECTED_DIR, exist_ok=True)
os.makedirs(PDF_DIR, exist_ok=True)

# Pricing
FLAT_PRICE = 2500.00
TOKEN_TTL_SECONDS = int(os.getenv("DOWNLOAD_TOKEN_TTL_SECONDS", str(24 * 60 * 60)))

RATE_LIMITS = {
    "/questionnaire": (20, 60),
    "/preview": (10, 60),
    "/create-checkout-session": (8, 60),
}
_RATE_BUCKETS: Dict[str, deque] = defaultdict(deque)
_RATE_LOCK = threading.Lock()

_TOKEN_STORE: Dict[str, Dict[str, Any]] = {}
_TOKEN_LOCK = threading.Lock()

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
    return [w.strip().lower() for w in re.split(r"[,;\n]", (s or "")) if w.strip()]


INTAKE_TYPE_MAP = {
    "teacher (classroom)": "EDU",
    "school / district": "EDU",
    "church / faith org": "NONPROFIT",
    "501c3 nonprofit": "NONPROFIT",
    "small business": "SMALL_BUSINESS",
    "city / municipality": "GOV_LOCAL",
    "other": "NONPROFIT",
}


def normalize_applicant_type(category: str) -> str:
    c = (category or "").strip().lower()
    return INTAKE_TYPE_MAP.get(c, "NONPROFIT")


def _normalize_keyword_token(token: str) -> str:
    t = (token or "").strip().lower()
    if not t:
        return ""
    t = re.sub(r"\btitle\s*(?:i|1)\b", "titlei", t)
    t = re.sub(r"\bk\s*[- ]?\s*12\b", "k12", t)
    t = re.sub(r"\bstem\b", "stem", t)
    t = re.sub(r"\btechnology\s+training\b", "technology", t)
    t = re.sub(r"\bell\b", "englishlearners", t)
    t = re.sub(r"\bsped\b", "specialeducation", t)
    t = t.replace("-", " ")
    t = " ".join(t.split())
    return t


def normalized_keywords(raw_keywords: str) -> List[str]:
    normalized = []
    for w in _norm_words(raw_keywords or ""):
        n = _normalize_keyword_token(w)
        if n and n not in normalized:
            normalized.append(n)
    return normalized


def normalized_tags(raw_tags: List[str]) -> List[str]:
    tokens: List[str] = []
    for t in (raw_tags or []):
        n = _normalize_keyword_token(str(t))
        if n and n not in tokens:
            tokens.append(n)
    return tokens


def _organization_name(payload: Dict[str, Any], default: str = "Your Organization") -> str:
    return (
        payload.get("organization")
        or payload.get("organization_name")
        or payload.get("org")
        or default
    ).strip()


def _safe_float(x, default=0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _csv_safe(value: Any) -> Any:
    if value is None:
        return ""
    text = str(value)
    if text and text[0] in ("=", "+", "-", "@"):
        return "'" + text
    return text


def _sanitize_log_row(row: Dict[str, Any]) -> Dict[str, Any]:
    cleaned: Dict[str, Any] = {}
    for k, v in (row or {}).items():
        if k in ("draft_body", "notes", "narrative", "summary"):
            continue
        cleaned[k] = _csv_safe(v)
    return cleaned


def _client_ip() -> str:
    xff = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    return xff or (request.remote_addr or "unknown")


def _rate_limit_exceeded(route_key: str) -> bool:
    cfg = RATE_LIMITS.get(route_key)
    if not cfg:
        return False
    max_hits, window_sec = cfg
    key = f"{route_key}:{_client_ip()}"
    now = time.time()
    with _RATE_LOCK:
        bucket = _RATE_BUCKETS[key]
        while bucket and bucket[0] <= now - window_sec:
            bucket.popleft()
        if len(bucket) >= max_hits:
            return True
        bucket.append(now)
    return False


def _mint_download_token(session_id: str) -> str:
    token = secrets.token_urlsafe(32)
    with _TOKEN_LOCK:
        _TOKEN_STORE[token] = {
            "session_id": session_id,
            "expires_at": datetime.utcnow() + timedelta(seconds=TOKEN_TTL_SECONDS),
            "used": False,
        }
    return token


def _consume_token(token: str) -> Optional[str]:
    if not token:
        return None
    with _TOKEN_LOCK:
        rec = _TOKEN_STORE.get(token)
        if not rec:
            return None
        if rec.get("used"):
            return None
        if rec.get("expires_at") < datetime.utcnow():
            _TOKEN_STORE.pop(token, None)
            return None
        rec["used"] = True
        return rec.get("session_id")


def _peek_token_session(token: str) -> Optional[str]:
    with _TOKEN_LOCK:
        rec = _TOKEN_STORE.get(token)
        if not rec:
            return None
        if rec.get("expires_at") < datetime.utcnow() or rec.get("used"):
            return None
        return rec.get("session_id")


def _stripe_session_paid(session_id: str) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    try:
        s = stripe.checkout.Session.retrieve(session_id)
        paid = str(s.get("payment_status", "")).lower() == "paid"
        return paid, s, ""
    except Exception as e:
        return False, None, str(e)



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
    """Fallback to Grants.gov listings page when no direct opportunity ID is available."""
    q = " ".join([title] + list(tags or [])).strip() or "federal grants"
    return f"https://www.grants.gov/search-grants?keywords={q.replace(' ', '%20')}"


def _safe_grants_url(url: str, title: str, tags: List[str]) -> str:
    """Only allow modern Grants.gov links; otherwise use search fallback."""
    if isinstance(url, str) and url.startswith(("http://", "https://")) and "grants.gov" in url:
        lowered = url.lower()
        if "apply07.grants.gov" in lowered or "grantsws/rest/opportunities/details" in lowered:
            return fallback_grants_gov_url(title, tags)
        return url
    return fallback_grants_gov_url(title, tags)


# -------- URL normalizer (force Grants.gov or fallback to its search) --------
def _ensure_http_url(url: str, title: str, tags: List[str]) -> str:
    return _safe_grants_url(url, title or "", tags or [])


def grant_display_url(gr: Dict[str, Any]) -> str:
    """
    Prefer direct Grants.gov opportunity links when possible.
    Fallback order:
      1) official_url if valid modern grants.gov URL
      2) funding_url/program_url if valid modern grants.gov URL
      3) grants.gov search URL
    """
    opp_id = str(
        gr.get("opportunity_id")
        or gr.get("oppId")
        or gr.get("opp_id")
        or gr.get("program_id")
        or ""
    ).strip()
    opp_number = str(
        gr.get("opportunity_number")
        or gr.get("oppNumber")
        or gr.get("opp_number")
        or ""
    ).strip()

    official_url = (gr.get("official_url") or "").strip()
    if official_url:
        return _ensure_http_url(official_url, gr.get("title", ""), gr.get("tags", []) or [])

    raw = gr.get("funding_url") or gr.get("program_url") or ""
    if raw:
        return _safe_grants_url(raw, gr.get("title", ""), gr.get("tags", []) or [])

    if opp_id or opp_number:
        q = " ".join([gr.get("title", ""), opp_id, opp_number]).strip()
        return fallback_grants_gov_url(q, gr.get("tags", []) or [])

    return fallback_grants_gov_url(gr.get("title", ""), gr.get("tags", []) or [])


def _pdf_header_mode_note() -> str:
    return "Production"


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
    return FLAT_PRICE


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


def score_grant(gr: Dict[str, Any], category: str, kws: List[str], amount: float) -> Dict[str, Any]:
    """
    Compute a score + qualitative fit and human-readable notes.
    Goal: more 'true' shortlisting based on your internal grants.json.
    """
    score = 0
    fit_notes: List[str] = []
    applicant_type = normalize_applicant_type(category)
    grant_sector = (gr.get("sector") or "").lower()
    requested_sector = infer_client_sector(kws)

    # 1) eligibility (already gated, but weighted highest)
    score += 100
    fit_notes.append(f"Eligibility matched for {applicant_type}.")

    # 2) sector relevance (after eligibility gate)
    if requested_sector and grant_sector:
        if requested_sector == grant_sector:
            score += 35
            fit_notes.append(f"Sector aligned: {requested_sector}.")
        else:
            score -= 45
            fit_notes.append(f"Sector mismatch: client {requested_sector}, program {grant_sector}.")

    # 3) keyword overlap
    tags = normalized_tags(gr.get("tags", []))
    summary_tokens = normalized_tags(_norm_words(gr.get("summary", "")))
    keyword_terms = set()
    for token in kws:
        keyword_terms.update([w for w in token.split() if len(w) > 2])
    grant_terms = set()
    for token in (tags + summary_tokens):
        grant_terms.update([w for w in token.split() if len(w) > 2])
    overlap = (set(kws) & (set(tags) | set(summary_tokens))) | (keyword_terms & grant_terms)
    if overlap:
        score += min(len(overlap), 5) * 8
        fit_notes.append("Keyword overlap: " + ", ".join(sorted(overlap)) + ".")
    else:
        score -= 25
        fit_notes.append("Weak keyword overlap with this opportunity.")

    # 4) funding fit
    min_amt = _safe_float(gr.get("min_amount"), 0.0)
    max_amt = _safe_float(gr.get("max_amount"), 10**12)
    if amount < min_amt:
        score -= 12
        fit_notes.append(f"Ask (${amount:,.0f}) is below minimum (${min_amt:,.0f}).")
    elif amount > max_amt:
        over_ratio = (amount / max_amt) if max_amt > 0 else 2
        if over_ratio >= 1.75:
            score -= 55
        elif over_ratio >= 1.25:
            score -= 35
        else:
            score -= 18
        fit_notes.append(f"Ask (${amount:,.0f}) exceeds maximum (${max_amt:,.0f}).")
    else:
        score += 12

    # deadline
    # 5) deadline validity
    if _deadline_ok(gr.get("deadline", "")):
        score += 6
    else:
        score -= 30
        fit_notes.append("Deadline has passed.")

    # match % note
    req_match = int(gr.get("requires_match_percent", 0) or 0)
    if req_match > 0:
        fit_notes.append(f"Requires approximately {req_match}% local match (cash or in-kind).")

    fit = "Strong Match" if score >= 130 else "Possible Match" if score >= 95 else "Low Match"
    return {"score": score, "fit": fit, "fit_notes": " ".join(fit_notes)}


def infer_client_sector(kws: List[str]) -> str:
    keyword_blob = " ".join(kws)
    sector_rules = [
        ("telehealth / healthcare", ["telehealth", "health", "healthcare", "patient", "clinic", "elderly", "remote monitoring", "digital health"]),
        ("workforce development", ["workforce", "apprenticeship", "credential", "certification", "skilled trades", "manufacturing", "upskilling"]),
        ("education / STEM", ["education", "school", "classroom", "teacher", "stem", "student", "after school"]),
        ("housing / community development", ["housing", "community development", "revitalization", "homeless", "neighborhood"]),
        ("public safety / emergency management", ["public safety", "emergency", "flood", "disaster", "mitigation", "response"]),
        ("conservation / environment", ["conservation", "wetlands", "habitat", "ecosystem", "climate", "restoration", "wildlife"]),
        ("arts / culture", ["arts", "culture", "storytelling", "creative", "media", "youth empowerment"]),
        ("entrepreneurship / innovation", ["innovation", "startup", "prototype", "research", "commercialization", "entrepreneurship"]),
    ]
    for sector, needles in sector_rules:
        if any(n in keyword_blob for n in needles):
            return sector
    return ""


def _is_eligible_for_applicant(gr: Dict[str, Any], applicant_type: str) -> bool:
    title = (gr.get("title") or "").lower()
    tags = " ".join(normalized_tags(gr.get("tags", [])))
    haystack = f"{title} {tags}"

    # hard gating rules before scoring
    if "sbir" in haystack:
        return applicant_type == "SMALL_BUSINESS"
    if "cdbg" in haystack:
        return applicant_type == "GOV_LOCAL"
    if any(k in haystack for k in ["classroom", "school", "district", "titlei", "stem", "robotics", "perkins", "teacher"]):
        return applicant_type == "EDU"
    if any(k in haystack for k in ["city", "municipality", "public safety", "hazard mitigation", "cdbg", "bric"]):
        return applicant_type == "GOV_LOCAL"
    if any(k in haystack for k in ["apprenticeship", "manufacturing workforce", "skilled trades"]):
        return applicant_type in ("SMALL_BUSINESS", "NONPROFIT")

    if applicant_type == "NONPROFIT" and any(k in haystack for k in ["telecom", "telecommunications", "broadband", "fiber"]):
        return False

    elig = " ".join([str(e).lower() for e in gr.get("eligible_types", [])])
    if applicant_type == "SMALL_BUSINESS":
        return any(t in elig for t in ["small business", "startup", "for-profit", "smb", "microenterprise"])
    if applicant_type == "GOV_LOCAL":
        return any(t in elig for t in ["municipality", "city", "county", "local government", "tribal"])
    if applicant_type == "EDU":
        return any(t in elig for t in ["school", "district", "teacher", "educator", "k12", "classroom"])
    return any(t in elig for t in ["501", "nonprofit", "community", "community-based organization", "health network"])


def shortlist(payload: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], bool]:
    """
    Turn intake into 0–3 strong matches from backend/data/grants.json.
    Data quality lives in grants.json; logic lives here.
    """
    payload = dict(payload or {})
    payload.pop("state", None)
    payload.pop("eligible_state", None)

    grants = _read_json(GRANTS_PATH) or []
    category = payload.get("category") or payload.get("who") or ""
    amount = _safe_float(payload.get("amountRequested"))
    applicant_type = normalize_applicant_type(category)
    kws = normalized_keywords(payload.get("keywords", ""))
    include_expired = bool(payload.get("includeExpired"))

    rows = []
    expired_rows = []

    for gr in grants:
        # hide expired unless explicitly requested
        close_date = gr.get("close_date") or gr.get("deadline") or ""
        is_expired = _is_expired(close_date)
        if not include_expired and is_expired:
            continue

        if not _is_eligible_for_applicant(gr, applicant_type):
            continue

        s = score_grant(gr, category, kws, amount)
        if s["score"] < 95:
            continue

        url = grant_display_url(gr)
        row = {
            "title": gr.get("title"),
            "program": gr.get("program") or gr.get("program_id") or gr.get("program_url") or "unknown",
            "program_url": url,  # not shown on free UI, used in paid PDF
            "program_id": gr.get("program_id", ""),
            "opp_id": gr.get("opp_id") or gr.get("opportunity_id") or "",
            "opp_number": gr.get("opp_number") or gr.get("opportunity_number") or "",
            "official_url": grant_display_url(gr),
            "amount": f"${int(_safe_float(gr.get('max_amount'), 0)):,.0f}",
            "deadline": close_date or "TBA",
            "fit": s["fit"],
            "score": s["score"],
            "fit_notes": s["fit_notes"],
            "requires_match_percent": gr.get("requires_match_percent", 0),
            "max_amount": _safe_float(gr.get("max_amount"), 0),
            "tags": gr.get("tags", []),
            "sector": gr.get("sector", ""),
            "summary": gr.get("summary", ""),
            "level": "Federal",
        }
        if is_expired and not include_expired:
            expired_rows.append(row)
        else:
            rows.append(row)

    rows.sort(key=lambda r: (_safe_float(r.get("score"), 0), _safe_float(r.get("max_amount"), 0)), reverse=True)

    strong_rows = [r for r in rows if r.get("fit") in ("Strong Match", "Possible Match")]
    has_strong_matches = len(strong_rows) > 0
    if len(strong_rows) >= 3:
        federal_rows = strong_rows[:3]
    else:
        federal_rows = rows[:3]

    return federal_rows, has_strong_matches


def _append_payment_log_row(row: Dict[str, Any]) -> None:
    try:
        safe_row = _sanitize_log_row(row)
        if os.path.exists(LOG_PATH):
            df = pd.read_csv(LOG_PATH)
            df = pd.concat([df, pd.DataFrame([safe_row])], ignore_index=True)
        else:
            df = pd.DataFrame([safe_row])
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
            for k, v in _sanitize_log_row(patch).items():
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
        display_k = {
            "titlei": "Title I",
            "k12": "K-12",
            "englishlearners": "English Learners",
            "specialeducation": "Special Education",
        }.get(k, k)
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
            out.append(f"Implement targeted activities related to “{display_k}” with measurable outputs.")
    return out


def _mk_evaluation_lines(audience: str) -> List[str]:
    who = audience or "participants"
    return [
        f"Track attendance and dosage for all {who}.",
        "Use short pre/post assessments tied to lesson objectives.",
        "Collect teacher/facilitator observations and student feedback.",
    ]


def build_draft_text(intake: Dict[str, Any], grant: Dict[str, Any]) -> str:
    """Build a polished, consultant-style narrative draft with structured sections."""
    intake = dict(intake or {})
    intake.pop("state", None)
    intake.pop("eligible_state", None)

    org = _organization_name(intake)
    proj_title = (intake.get("projectTitle") or "Proposed initiative").strip()
    category = (intake.get("category") or intake.get("who") or "organization").strip()
    audience = (intake.get("audience") or "participants").strip().rstrip(".")
    timeline = (intake.get("timeline") or "12 months").strip().rstrip(".")
    notes = (intake.get("notes") or "").strip()
    stated_need = (intake.get("need") or "").strip()

    amount = _safe_float(intake.get("amountRequested"))
    annual_budget = _safe_float(intake.get("annualBudget"), 0)
    keywords_str = (intake.get("keywords") or "").strip()
    kws = normalized_keywords(keywords_str)
    client_sector = infer_client_sector(kws) or "community impact"

    g_title = grant.get("title") or "Selected federal opportunity"
    g_deadline = grant.get("deadline") or "TBA"
    g_match = int(grant.get("requires_match_percent", 0) or 0)
    g_max = _safe_float(grant.get("max_amount"), 0)
    g_url = grant_display_url(grant) if grant else ""

    req_str = f"${amount:,.0f}" if amount > 0 else "a competitive request amount"
    aligned_request = min(amount, g_max) if (amount > 0 and g_max > 0) else amount
    aligned_req_str = f"${aligned_request:,.0f}" if aligned_request > 0 else req_str

    budget_context = (
        f"The organization currently operates with an estimated annual budget of ${annual_budget:,.0f}, which provides sufficient financial infrastructure to manage reimbursable and performance-based grant activities."
        if annual_budget > 0 else
        "The organization maintains financial controls, procurement standards, and board-level oversight to support federal grants management and audit readiness."
    )

    need_context = stated_need or notes or (
        "The project addresses access barriers, service coordination gaps, and uneven resource distribution that limit outcomes for the intended population."
    )

    objectives = _mk_objectives_from_keywords(kws, audience)
    if not objectives:
        objectives = [
            "Deliver high-quality services through a structured program model tied to measurable milestones.",
            "Increase participation and retention among the intended audience across the implementation period.",
            "Demonstrate measurable outcomes using consistent performance monitoring and continuous improvement.",
        ]

    sections = []
    sections.append(
        "Executive Summary\n"
        f"{org} respectfully submits this proposal foundation for the {g_title} opportunity to advance '{proj_title}' for {audience}. "
        f"The proposed request is {req_str}, designed around a practical implementation strategy in the {client_sector} sector. "
        f"The initiative responds to documented local barriers and will deploy targeted interventions over {timeline} with clear management milestones, partner accountability, and measurable deliverables. "
        f"As a {category}, {org} is positioned to execute responsibly, align spending to allowable costs, and report outcomes in a reviewer-friendly format. "
        f"The project combines direct service delivery, infrastructure support, and evaluation activities so that the funded work produces immediate impact while building sustainable long-term capacity."
    )
    sections.append(
        "Statement of Need\n"
        f"The need for this project is immediate and well documented: {need_context} "
        f"Current conditions affecting {audience} include inconsistent access, delayed service engagement, and preventable outcomes that could be improved through earlier, coordinated intervention. "
        f"Community stakeholders have repeatedly identified priority issues connected to {keywords_str or 'core community needs'}, and existing resources are not sufficient to close these gaps at the speed or scale required. "
        "Without investment, the target population is likely to continue experiencing fragmented support and avoidable harm. "
        "This proposal is intentionally designed to close those gaps through a focused, evidence-informed model that pairs operational discipline with participant-centered delivery."
    )
    sections.append(
        "Program Design\n"
        "The proposed program design translates strategy into execution by combining staffing, service protocols, and practical tools that address the root barriers described above. "
        f"Project activities will include: (1) direct program services for {audience}; (2) deployment of project resources and equipment needed for reliable delivery; and (3) structured care and coordination workflows that improve continuity and follow-through. "
        "The design uses phased implementation to ensure that the first months establish quality standards, compliance controls, and partner expectations before full-scale rollout. "
        f"Operationally, the project will focus on {keywords_str or 'priority service areas'} while maintaining flexibility to adjust delivery methods based on monthly performance data. "
        "All program components are built to satisfy federal grant standards for eligibility, documentation, and measurable outcomes."
    )
    sections.append(
        "Target Population\n"
        f"The target population for this initiative is {audience}. "
        "Recruitment and engagement will prioritize individuals and households that face the highest barriers to access, including transportation constraints, digital access limitations, unstable income, or limited availability of local services. "
        "Program communications will be delivered through trusted institutions and community partners to reduce participation friction and improve retention over time. "
        "Service delivery protocols will emphasize cultural responsiveness, language accessibility where needed, and practical scheduling that reflects participant realities. "
        "By aligning outreach, enrollment, and service cadence to the lived conditions of the target population, the project is expected to improve both participation quality and outcome durability."
    )
    sections.append(
        "Implementation Plan\n"
        f"Implementation will proceed over {timeline} with a milestone-based structure. "
        "Month 1 will focus on startup activities, partner onboarding, baseline metrics, and procurement setup. "
        "Months 2 through 9 will focus on full service delivery, case coordination, and monthly quality-improvement reviews. "
        "Final months will emphasize performance validation, sustainability transition steps, and closeout readiness. "
        "Leadership will conduct routine implementation reviews and maintain auditable records for spending, outputs, and participant outcomes. "
        "Key objectives include: " + " ".join([f"({i+1}) {obj}" for i, obj in enumerate(objectives[:4])])
    )
    sections.append(
        "Expected Outcomes\n"
        f"Expected outcomes include improved access, higher engagement consistency, and measurable gains for {audience}. "
        "The project will track both output and outcome indicators, including participation volume, service completion rates, timeliness, and targeted performance benchmarks tied to the core intervention model. "
        "Management will review monthly dashboards and implement corrective actions when indicators fall below target thresholds. "
        "By the end of the grant period, the organization expects to demonstrate a replicable model with stronger participant outcomes, improved operational reliability, and clear evidence of return on public investment."
    )
    sections.append(
        "Organizational Capacity\n"
        f"{org} has the leadership structure and operational maturity to manage this grant effectively. "
        f"{budget_context} "
        "Program governance includes defined responsibilities for executive oversight, fiscal management, procurement, and performance reporting. "
        "Internal controls include expenditure documentation, segregation of duties, and regular management review of deliverables and compliance milestones. "
        "The organization also maintains community partnerships that support referrals, implementation coordination, and continuity of services beyond the grant period."
    )

    budget_alignment_clause = ""
    if g_max > 0 and amount > g_max:
        budget_alignment_clause = (
            f" Because the current request exceeds the published award ceiling, this draft aligns the proposed budget narrative to an allowable amount of approximately {aligned_req_str} while preserving core project outcomes through phased implementation."
        )
    match_clause = f" The budget also includes a strategy to satisfy the required {g_match}% match through eligible cash and in-kind contributions." if g_match > 0 else ""
    sections.append(
        "Budget Use\n"
        f"Requested funds ({req_str}) will be allocated to allowable categories such as personnel, program supplies, technology/equipment, participant supports, data and evaluation, and grant administration required for compliant delivery. "
        "Each budget category will be tied directly to implementation milestones and documented outputs to ensure transparent use of funds. "
        f"The spending plan is designed for fiscal discipline and audit readiness, with monthly reconciliation and variance review.{budget_alignment_clause}{match_clause} "
        "No unsupported or non-allowable costs are assumed in this draft framework, and final line-item detail should be refined against the selected opportunity guidance before submission."
    )
    sections.append(
        "Sustainability\n"
        "Sustainability planning begins at project launch rather than at closeout. "
        "The organization will document successful workflows, integrate high-performing practices into routine operations, and formalize partner commitments that can continue beyond the initial award period. "
        "Performance findings will be used to inform future applications, braided funding strategies, and strategic budgeting decisions that protect service continuity for the target population. "
        f"Prior to submission, leadership should re-verify eligibility, deadlines, and compliance details for {g_title} (deadline: {g_deadline})."
        + (f" Official opportunity details: {g_url}." if g_url else "")
        + " Review and edit all draft materials before submission."
    )

    return "\n\n".join(sections)


def make_pdf(order_id: str, payload: Dict[str, Any]) -> str:
    """
    Generate a PDF from the given payload.
    If 'draft_body' is present, render a structured narrative + order details.
    Otherwise, fall back to key/value listing (legacy).
    """
    os.makedirs(PDF_DIR, exist_ok=True)  # ensure exists at write time
    pdf_path = os.path.join(PDF_DIR, f"{order_id}.pdf")
    c = canvas.Canvas(pdf_path, pagesize=letter)

    left_margin = 54
    right_margin = 558
    top_y = 770
    body_top_y = 720
    bottom_margin = 60
    line_width_chars = 98

    created_at = _now_utc()
    page_num = 1

    def draw_header() -> int:
        c.setFont("Helvetica-Bold", 14)
        c.drawString(left_margin, top_y, "GrantforgeUSA | Proposal Draft")
        c.setFont("Helvetica", 10)
        c.drawString(left_margin, top_y - 15, f"Order: {order_id}")
        c.drawString(left_margin, top_y - 28, f"Created: {created_at}")
        return body_top_y

    def draw_footer():
        c.setFont("Helvetica-Oblique", 9)
        c.drawString(
            left_margin,
            bottom_margin - 12,
            "Review and edit all draft materials before submission. All sales final. No refunds.",
        )
        c.drawRightString(right_margin, bottom_margin - 12, f"Page {page_num}")

    def new_page() -> int:
        nonlocal page_num
        draw_footer()
        c.showPage()
        page_num += 1
        return draw_header()

    y = draw_header()
    c.setFont("Helvetica", 10)

    def draw_section_header(title: str) -> int:
        c.setFont("Helvetica-Bold", 11)
        new_y = _wrap_draw_line(c, title, left_margin, y, width_chars=line_width_chars)
        c.setFont("Helvetica", 10)
        return new_y

    def draw_line(text: str) -> int:
        return _wrap_draw_line(c, text, left_margin, y, width_chars=line_width_chars)

    draft_body = payload.get("draft_body")
    if isinstance(draft_body, str) and draft_body.strip():
        y = draw_section_header("Draft Narrative")

        for para in draft_body.split("\n\n"):
            for line in para.split("\n"):
                if y < bottom_margin:
                    y = new_page()
                if line.strip().endswith(":"):
                    c.setFont("Helvetica-Bold", 10)
                    y = _wrap_draw_line(c, line.strip(), left_margin, y, width_chars=line_width_chars)
                    c.setFont("Helvetica", 10)
                else:
                    y = _wrap_draw_line(c, line, left_margin, y, width_chars=line_width_chars)
            y -= 8

        if y < bottom_margin + 20:
            y = new_page()

        y = draw_section_header("Order Details")

        summary_lines = [
            f"Project title: {payload.get('projectTitle', '')}",
            f"Applicant type: {payload.get('category', '')}",
            f"Requested amount: ${_safe_float(payload.get('amountRequested'), 0):,.2f}",
            f"Recommended opportunity: {payload.get('grant_title', '')}",
        ]
        for line in summary_lines:
            if y < bottom_margin:
                y = new_page()
            y = draw_line(line)

        for k in sorted(payload.keys()):
            if k == "draft_body":
                continue
            v = payload[k]
            if y < bottom_margin:
                y = new_page()
            y = draw_line(f"{k}: {v}")
    else:
        for k in sorted(payload.keys()):
            v = payload[k]
            if y < bottom_margin:
                y = new_page()
            y = draw_line(f"{k}: {v}")

    draw_footer()
    c.save()
    return pdf_path


@app.before_request
def _apply_rate_limit():
    if request.method == "OPTIONS":
        return None
    route = request.path
    if route in RATE_LIMITS and _rate_limit_exceeded(route):
        return jsonify(ok=False, error="Rate limit exceeded. Please try again shortly."), 429
    return None


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
    debug_enabled = os.getenv("DEBUG", "false").lower() == "true"
    trusted_ip = os.getenv("TRUSTED_DEBUG_IP", "127.0.0.1")
    if not debug_enabled or _client_ip() != trusted_ip:
        return jsonify(ok=False, error="Not found"), 404

    try:
        pdf_files = sorted(glob.glob(os.path.join(PDF_DIR, "*.pdf")), key=os.path.getmtime, reverse=True)
        pdf_tail = [os.path.basename(p) for p in pdf_files[:10]]
        return jsonify(ok=True, pdfTail=pdf_tail, ts=_now_utc())
    except Exception as e:
        return jsonify(ok=False, error=str(e), ts=_now_utc()), 500


# ---------------- shortlist/search ----------------
@app.post("/questionnaire")
def questionnaire():
    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify(ok=False, error="Invalid JSON"), 400

    org = _organization_name(data)
    results, has_strong_matches = shortlist(data)
    notice = ""
    if not has_strong_matches and results:
        notice = "No direct federal matches found. Showing closest opportunities."
    return jsonify(ok=True, organization=org, results=results, notice=notice)


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
        short, _ = shortlist(data)
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

    data = dict(data or {})
    data.pop("state", None)
    data.pop("eligible_state", None)

    org = _organization_name(data, default="Customer")
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

    grant_url = grant_display_url(grant) if grant else ""

    metadata = {
        "order_id": order_id,
        "org": org,
        "organization": org,
        "organization_name": org,
        "category": category,
        "amountRequested": f"{amount_req:.2f}",
        "annualBudget": f"{annual_budget:.2f}",
        "grant_title": grant.get("title", ""),
        "grant_program": grant.get("program", ""),
        "grant_deadline": grant.get("deadline", ""),
        "grant_url": grant_url,
        "projectTitle": (data.get("projectTitle") or "").strip(),
        "keywords": (data.get("keywords") or "").strip(),
        "price": f"{price:.2f}",
        "refund_policy": "All sales final. No refunds.",
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
        "organization_name": org,
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
@app.post("/create-download-token")
def create_download_token():
    session_id = request.args.get("session_id") or (request.get_json(silent=True) or {}).get("session_id")
    if not session_id:
        return jsonify(ok=False, error="missing session_id"), 400

    paid, _s, err = _stripe_session_paid(session_id)
    if err:
        return jsonify(ok=False, error=f"Stripe lookup failed: {err}"), 400
    if not paid:
        return jsonify(ok=False, error="payment not completed"), 402

    token = _mint_download_token(session_id)
    _update_payment_log_by("session_id", session_id, {"paid": True})
    return jsonify(ok=True, token=token, expires_in=TOKEN_TTL_SECONDS)


@app.get("/receipt")
def receipt():
    token = request.args.get("token")
    if not token:
        return jsonify(ok=False, error="missing token"), 400

    session_id = _peek_token_session(token)
    if not session_id:
        return jsonify(ok=False, error="invalid or expired token"), 400

    paid, s, err = _stripe_session_paid(session_id)
    if err:
        return jsonify(ok=False, error=f"Stripe lookup failed: {err}"), 400
    if not paid:
        return jsonify(ok=False, error="payment not completed"), 402

    row = find_log_by_session(session_id)
    if not row:
        md = s.metadata or {}
        order_id = md.get("order_id") or datetime.utcnow().strftime("ORD-%Y%m%d-%H%M%S-%f")
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
            "price": float(md.get("price", FLAT_PRICE) or FLAT_PRICE),
            "pdf_path": "",
            "paid": True,
        })
        row = find_log_by_session(session_id)

    return jsonify({
        "ok": True,
        "order_id": row.get("order_id", ""),
        "amount_total": row.get("price", FLAT_PRICE),
        "paid": True,
        "grant_title": row.get("grant_title", ""),
        "download_path": f"/download-by-session?token={token}",
        "ts": _now_utc(),
    })


@app.get("/download-by-session")
def download_by_session():
    try:
        token = request.args.get("token")
        if not token:
            return jsonify(ok=False, error="missing token"), 400

        session_id = _consume_token(token)
        if not session_id:
            return jsonify(ok=False, error="invalid, expired, or already-used token"), 400

        paid, s, err = _stripe_session_paid(session_id)
        if err:
            return jsonify(ok=False, error=f"Stripe lookup failed: {err}"), 400
        if not paid:
            return jsonify(ok=False, error="payment not completed"), 402

        row = find_log_by_session(session_id)
        md = (s.metadata or {}) if s else {}
        order_id = (row.get("order_id") if row else None) or md.get("order_id") or datetime.utcnow().strftime("ORD-%Y%m%d-%H%M%S-%f")

        pdf_path = row.get("pdf_path") if row else ""
        if not (pdf_path and os.path.exists(pdf_path)):
            pdf_payload = dict(md)
            if not pdf_payload.get("draft_body") and row and row.get("draft_body"):
                pdf_payload["draft_body"] = row.get("draft_body")
            pdf_path = make_pdf(order_id, pdf_payload)
            _update_payment_log_by("session_id", session_id, {
                "order_id": order_id,
                "pdf_path": pdf_path,
                "paid": True,
            })

        if not (pdf_path and os.path.exists(pdf_path)):
            return jsonify(ok=False, error="PDF not found yet; try again in a moment."), 404

        name = os.path.basename(pdf_path) or f"{order_id}.pdf"
        return send_file(pdf_path, as_attachment=True, download_name=name, mimetype="application/pdf")
    except Exception as e:
        return jsonify(ok=False, error=f"download route error: {e}"), 400


# ------------- main (optional local run) -------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
