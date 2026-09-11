# GrantforgeUSA — v11.4 backend (launch path)
# Purpose: shortlist w/ real matching + fraud checks, Stripe checkout,
#          REAL narrative draft generation, reliable PDF download
#          (eager + webhook), contextual previews, and debug utilities.

import os, sys, json, re, secrets, threading, time
from datetime import datetime, date, timedelta
from collections import defaultdict, deque
from typing import Dict, Any, List, Optional, Tuple

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import stripe
from dotenv import load_dotenv

CURRENT_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.dirname(CURRENT_DIR)
if ROOT_DIR and ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from runtime_config import load_runtime_settings
from backend.grantsgov_live import fetch_live_grant, search_live_grants

# PDF / data helpers
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, Spacer, SimpleDocTemplate
import pandas as pd

# ---------------- bootstrap env ----------------
load_dotenv()
SETTINGS = load_runtime_settings()

FRONTEND_URL = os.getenv("FRONTEND_URL", "https://grantforge-usav-11.vercel.app")
FRONTEND_THANKS_URL = os.getenv("FRONTEND_THANKS_URL", f"{FRONTEND_URL}/thanks")

# Stripe
stripe.api_key = SETTINGS.stripe_secret_key
PUBLISHABLE_KEY = SETTINGS.stripe_publishable_key
STRIPE_WEBHOOK_SECRET = SETTINGS.stripe_webhook_secret

APP_MODE = SETTINGS.app_mode

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

# Public per-draft pricing: one flat fee regardless of applicant type or grant size.
FLAT_DRAFT_PRICE = float(os.getenv("GRANT_DRAFT_PRICE", "49.99"))
TOKEN_TTL_SECONDS = int(os.getenv("DOWNLOAD_TOKEN_TTL_SECONDS", str(24 * 60 * 60)))

RATE_LIMITS = {
    "/questionnaire": (20, 60),
    "/preview": (10, 60),
    "/create-checkout-session": (8, 60),
    "/create-download-token": (20, 60),
    "/download-by-session": (20, 60),
}
_RATE_BUCKETS: Dict[str, deque] = defaultdict(deque)
_RATE_LOCK = threading.Lock()

_TOKEN_STORE: Dict[str, Dict[str, Any]] = {}
_TOKEN_LOCK = threading.Lock()
_COMPLETED_DOWNLOADS: set[str] = set()
_COMPLETED_DOWNLOADS_LOCK = threading.Lock()
_CHECKOUT_REF_STORE: Dict[str, Dict[str, Any]] = {}
_CHECKOUT_REF_LOCK = threading.Lock()
_DRAFT_STORE: Dict[str, Dict[str, Any]] = {}
_DRAFT_LOCK = threading.Lock()
DEBUG_ENDPOINTS_ENABLED = os.getenv("ENABLE_DEBUG_ENDPOINTS", "false").lower() == "true"
LOG_RETENTION_DAYS = int(os.getenv("LOG_RETENTION_DAYS", "30"))

# ---------------- Flask app ----------------
app = Flask(__name__)

# Env-configurable CORS:
# - default: "*" (easy local use)
# - set CORS_ORIGINS="https://yourlivefrontend.com" for locked-down live
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")
if CORS_ORIGINS == "*":
    CORS(app, origins="*")
else:
    CORS(app, origins=[o.strip() for o in CORS_ORIGINS.split(",") if o.strip()])


@app.after_request
def _set_security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    resp.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    if request.headers.get("X-Forwarded-Proto", "http") == "https":
        resp.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    return resp


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


def _tokenize_text(s: str) -> List[str]:
    return [
        tok for tok in re.split(r"[^a-zA-Z0-9]+", (s or "").lower()) if len(tok) > 2
    ]


INTAKE_TYPE_MAP = {
    "k-12 school / district / educator": "EDU_K12",
    "public college / university": "HIGHER_ED_PUBLIC",
    "private college / university": "HIGHER_ED_PRIVATE",
    "research institution / university research foundation": "RESEARCH_INSTITUTION",
    "college / university / research institution": "HIGHER_ED",
    "church / faith organization": "NONPROFIT",
    "501(c)(3) nonprofit": "NONPROFIT_501C3",
    "nonprofit / community organization": "NONPROFIT",
    "small business": "SMALL_BUSINESS",
    "for-profit organization": "FOR_PROFIT",
    "city / county / local government": "GOV_LOCAL",
    "state government / agency": "GOV_STATE",
    "tribal government / organization": "TRIBAL",
    "public housing authority": "HOUSING",
    "individual / independent applicant": "INDIVIDUAL",
    "other eligible applicant": "OTHER",
    "teacher (classroom)": "EDU_K12",
    "school / district": "EDU_K12",
    "church / faith org": "NONPROFIT",
    "501c3 nonprofit": "NONPROFIT_501C3",
    "city / municipality": "GOV_LOCAL",
    "other": "OTHER",
}


def normalize_applicant_type(category: str) -> str:
    c = (category or "").strip().lower()
    return INTAKE_TYPE_MAP.get(c, "OTHER")


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
    for t in raw_tags or []:
        n = _normalize_keyword_token(str(t))
        if n and n not in tokens:
            tokens.append(n)
    return tokens


def _organization_name(
    payload: Dict[str, Any], default: str = "Your Organization"
) -> str:
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


def _sanitize_text(value: Any, max_len: int = 500) -> str:
    raw = str(value or "")
    cleaned = re.sub(r"<[^>]*>", "", raw)
    cleaned = cleaned.replace("\x00", "")
    cleaned = re.sub(r"[\r\n\t]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:max_len]


def _sanitize_numeric(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", "").strip())
    except Exception:
        return default


def sanitize_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    allowed_text = {
        "organization",
        "organization_name",
        "org",
        "category",
        "who",
        "keywords",
        "projectTitle",
        "timeline",
        "audience",
        "notes",
        "need",
        "session_id",
        "state",
        "eligible_state",
    }
    out: Dict[str, Any] = {}
    for k, v in (data or {}).items():
        if k in ("phone", "phoneNumber"):
            continue
        if k in ("amountRequested", "annualBudget"):
            out[k] = _sanitize_numeric(v, 0.0)
        elif k in ("includeExpired",):
            out[k] = bool(v)
        elif k == "grant" and isinstance(v, dict):
            out[k] = {
                "title": _sanitize_text(v.get("title", ""), 200),
                "program": _sanitize_text(v.get("program", ""), 200),
                "deadline": _sanitize_text(v.get("deadline", ""), 100),
                "program_url": _sanitize_text(v.get("program_url", ""), 500),
                "official_url": _sanitize_text(v.get("official_url", ""), 500),
                "opportunity_number": _sanitize_text(
                    v.get("opportunity_number", ""), 120
                ),
                "opp_number": _sanitize_text(v.get("opp_number", ""), 120),
                "max_amount": _sanitize_numeric(v.get("max_amount", 0), 0.0),
                "tags": [_sanitize_text(t, 80) for t in (v.get("tags") or [])][:20],
                "requires_match_percent": int(
                    _sanitize_numeric(v.get("requires_match_percent", 0), 0)
                ),
                "cost_sharing_required": v.get("cost_sharing_required") if isinstance(v.get("cost_sharing_required"), bool) else None,
                "opp_id": _sanitize_text(v.get("opp_id", ""), 120),
                "opportunity_id": _sanitize_text(v.get("opportunity_id", ""), 120),
                "source": _sanitize_text(v.get("source", ""), 120),
            }
        elif k == "recommendations" and isinstance(v, list):
            out[k] = [
                {
                    "title": _sanitize_text((item or {}).get("title", ""), 200),
                    "program_url": _sanitize_text(
                        (item or {}).get("program_url", ""), 500
                    ),
                    "url": _sanitize_text((item or {}).get("url", ""), 500),
                }
                for item in v[:10]
                if isinstance(item, dict)
            ]
        elif k in allowed_text:
            out[k] = _sanitize_text(v, 500)
        else:
            out[k] = v
    return out


def _validate_required_intake(data: Dict[str, Any]) -> Optional[str]:
    required = {
        "organization": _organization_name(data, default=""),
        "category": (data.get("category") or data.get("who") or "").strip(),
        "keywords": (data.get("keywords") or "").strip(),
        "amountRequested": str(data.get("amountRequested", "")).strip(),
        "annualBudget": str(data.get("annualBudget", "")).strip(),
        "projectTitle": (data.get("projectTitle") or "").strip(),
        "timeline": (data.get("timeline") or "").strip(),
        "audience": (data.get("audience") or "").strip(),
        "state": (data.get("state") or data.get("eligible_state") or "").strip(),
    }
    missing = [k for k, v in required.items() if not v or v == "0.0"]
    if missing:
        labels = {
            "organization": "organization name",
            "category": "category",
            "keywords": "keywords",
            "amountRequested": "amount requested",
            "annualBudget": "annual budget",
            "projectTitle": "project title",
            "timeline": "timeline",
            "audience": "audience",
            "state": "state",
        }
        return "Missing required field(s): " + ", ".join(labels[m] for m in missing)
    return None


def _csv_safe(value: Any) -> Any:
    if value is None:
        return ""
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    if not text:
        return ""
    if not text.startswith("'"):
        return "'" + text
    return text


def _sanitize_log_row(row: Dict[str, Any]) -> Dict[str, Any]:
    cleaned: Dict[str, Any] = {}
    for k, v in (row or {}).items():
        if k in ("draft_body", "notes", "project_notes", "narrative", "summary"):
            continue
        cleaned[k] = _csv_safe(v)
    return cleaned


def _is_internal_request() -> bool:
    ip = _client_ip()
    return ip in ("127.0.0.1", "::1", "localhost")


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


def _mint_checkout_ref(session_id: str) -> str:
    token = secrets.token_urlsafe(24)
    with _CHECKOUT_REF_LOCK:
        _CHECKOUT_REF_STORE[token] = {
            "session_id": session_id,
            "expires_at": datetime.utcnow() + timedelta(seconds=TOKEN_TTL_SECONDS),
            "used": False,
        }
    return token


def _consume_checkout_ref(checkout_ref: str) -> Optional[str]:
    if not checkout_ref:
        return None
    with _CHECKOUT_REF_LOCK:
        rec = _CHECKOUT_REF_STORE.get(checkout_ref)
        if not rec:
            return None
        if rec.get("used"):
            return None
        if rec.get("expires_at") < datetime.utcnow():
            _CHECKOUT_REF_STORE.pop(checkout_ref, None)
            return None
        rec["used"] = True
        return rec.get("session_id")


def _store_draft(
    session_id: str, draft_body: str, recommendations: List[Dict[str, str]]
) -> None:
    with _DRAFT_LOCK:
        _DRAFT_STORE[session_id] = {
            "draft_body": draft_body,
            "recommendations": recommendations,
            "created_at": datetime.utcnow(),
        }


def _load_draft(session_id: str) -> Dict[str, Any]:
    with _DRAFT_LOCK:
        return dict(_DRAFT_STORE.get(session_id) or {})


def _stripe_session_paid(session_id: str) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    try:
        s = stripe.checkout.Session.retrieve(session_id)
        paid = str(s.get("payment_status", "")).lower() == "paid"
        return paid, s, ""
    except Exception as e:
        return False, None, str(e)


def _session_belongs_requester(session_obj: Dict[str, Any]) -> bool:
    metadata = (session_obj or {}).get("metadata") or {}
    expected_ip = (metadata.get("requester_ip") or "").strip()
    if not expected_ip:
        return False
    return expected_ip == _client_ip()


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


def _first_identifier(gr: Dict[str, Any], *keys: str) -> str:
    for k in keys:
        val = str(gr.get(k) or "").strip()
        if val:
            return val
    return ""


def grants_gov_detail_url(identifier: str) -> str:
    clean_id = re.sub(r"\s+", "", (identifier or "").strip())
    if not clean_id:
        return ""
    return f"https://www.grants.gov/opportunity/details/{clean_id}"


def grants_gov_search_url(query: str) -> str:
    clean_query = re.sub(r"\s+", " ", (query or "").strip())
    if not clean_query:
        return ""
    encoded = re.sub(r"\s+", "%20", clean_query)
    return f"https://www.grants.gov/search-results?query={encoded}"


def _safe_grants_url(url: str) -> Optional[str]:
    """Allow only canonical HTTPS Grants.gov URLs."""
    if not isinstance(url, str):
        return None
    candidate = url.strip()
    if not candidate.startswith("https://www.grants.gov"):
        return None
    lowered = candidate.lower()
    if (
        "apply07.grants.gov" in lowered
        or "grantsws/rest/opportunities/details" in lowered
    ):
        return None
    if not (
        lowered.startswith("https://www.grants.gov/opportunity/details/")
        or lowered.startswith("https://www.grants.gov/search-results-detail/")
        or lowered.startswith("https://www.grants.gov/search-results?query=")
    ):
        return None
    return candidate


# -------- URL normalizer --------
def _ensure_http_url(url: str) -> Optional[str]:
    return _safe_grants_url(url)


def grant_display_url(gr: Dict[str, Any]) -> str:
    """Return a validated official Grants.gov URL with direct-link priority."""
    for key in ("official_url", "program_url", "url", "funding_url"):
        candidate = _ensure_http_url(gr.get(key) or "")
        if candidate:
            return candidate

    direct_identifier = _first_identifier(gr, "opp_id", "opportunity_id")
    by_opp_id = _ensure_http_url(grants_gov_detail_url(direct_identifier))
    if by_opp_id:
        return by_opp_id

    opp_number = _first_identifier(gr, "opportunity_number", "opp_number")
    by_opp_number = _ensure_http_url(grants_gov_detail_url(opp_number))
    if by_opp_number:
        return by_opp_number

    return _ensure_http_url(grants_gov_search_url(str(gr.get("title") or ""))) or ""


def _is_session_already_downloaded(session_id: str) -> bool:
    with _COMPLETED_DOWNLOADS_LOCK:
        return session_id in _COMPLETED_DOWNLOADS


def _mark_session_downloaded(session_id: str) -> None:
    with _COMPLETED_DOWNLOADS_LOCK:
        _COMPLETED_DOWNLOADS.add(session_id)


def _pdf_header_mode_note() -> str:
    return "Production"


def _wrap_draw_line(
    c: canvas.Canvas, text: str, start_x: int, y: int, width_chars: int = 110
) -> int:
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
    """Return the single public price for one customized full proposal draft."""
    _ = category, annual_budget
    return FLAT_DRAFT_PRICE


def fraud_check(category: str, amount: float) -> Dict[str, Any]:
    """Basic transaction sanity checks; grant-specific limits belong to the official notice."""
    if amount <= 0:
        return {"ok": False, "msg": "Requested amount must be greater than 0."}
    return {"ok": True, "msg": ""}


US_STATE_NAMES = {
    "AL": "alabama", "AK": "alaska", "AZ": "arizona", "AR": "arkansas",
    "CA": "california", "CO": "colorado", "CT": "connecticut", "DE": "delaware",
    "FL": "florida", "GA": "georgia", "HI": "hawaii", "ID": "idaho",
    "IL": "illinois", "IN": "indiana", "IA": "iowa", "KS": "kansas",
    "KY": "kentucky", "LA": "louisiana", "ME": "maine", "MD": "maryland",
    "MA": "massachusetts", "MI": "michigan", "MN": "minnesota", "MS": "mississippi",
    "MO": "missouri", "MT": "montana", "NE": "nebraska", "NV": "nevada",
    "NH": "new hampshire", "NJ": "new jersey", "NM": "new mexico", "NY": "new york",
    "NC": "north carolina", "ND": "north dakota", "OH": "ohio", "OK": "oklahoma",
    "OR": "oregon", "PA": "pennsylvania", "RI": "rhode island", "SC": "south carolina",
    "SD": "south dakota", "TN": "tennessee", "TX": "texas", "UT": "utah",
    "VT": "vermont", "VA": "virginia", "WA": "washington", "WV": "west virginia",
    "WI": "wisconsin", "WY": "wyoming", "DC": "district of columbia",
}

ARC_STATES = {"AL", "GA", "KY", "MD", "MS", "NY", "NC", "OH", "PA", "SC", "TN", "VA", "WV"}

def _normalize_state(value: str) -> str:
    raw = (value or "").strip().lower()
    if not raw:
        return ""
    for code, name in US_STATE_NAMES.items():
        if raw == code.lower() or raw == name:
            return code
    return raw.upper() if len(raw) == 2 else ""

def _geography_compatible(gr: Dict[str, Any], state_value: str) -> Tuple[bool, str]:
    state = _normalize_state(state_value)
    if not state:
        return False, "State is required to verify geographic eligibility."
    blob = " ".join([
        str(gr.get("title") or ""),
        str(gr.get("program") or ""),
        str(gr.get("agency") or ""),
        str(gr.get("eligibility_text") or ""),
        str(gr.get("summary") or ""),
    ]).lower()
    if "appalachian regional commission" in blob or re.search(r"\barc\b", blob):
        if state not in ARC_STATES:
            return False, "Applicant state is outside the Appalachian Regional Commission service area."

    # Catch common NOFO language that explicitly limits eligibility/service to a named state list.
    # This intentionally prefers a false negative over presenting a geographically impossible grant.
    restrictive_markers = (
        "in the states of", "within the states of", "limited to the states of",
        "eligible states include", "eligible states are", "only in the states of",
        "establish and operate", "available in the following states",
    )
    for marker in restrictive_markers:
        pos = blob.find(marker)
        if pos < 0:
            continue
        segment = blob[pos : pos + 900]
        named_codes = {
            code for code, name in US_STATE_NAMES.items()
            if re.search(rf"\b{re.escape(name)}\b", segment)
        }
        # Require at least two named jurisdictions before treating the passage as a list,
        # avoiding accidental rejection from a single example/location mention.
        if len(named_codes) >= 2 and state not in named_codes:
            return False, "The notice appears limited to named states that do not include the applicant state."
    return True, ""

def _funding_range_compatible(gr: Dict[str, Any], amount: float) -> Tuple[bool, str]:
    minimum = _safe_float(gr.get("min_amount"), 0.0)
    maximum = _safe_float(gr.get("max_amount"), 0.0)
    if minimum > 0 and amount < minimum:
        return False, f"Requested amount (${amount:,.0f}) is below this opportunity's minimum (${minimum:,.0f})."
    if maximum > 0 and amount > maximum:
        return False, f"Requested amount (${amount:,.0f}) exceeds this opportunity's maximum (${maximum:,.0f})."
    return True, ""

def _relevance_compatible(gr: Dict[str, Any], payload: Dict[str, Any], applicant_type: str) -> Tuple[bool, str]:
    """Reject broad-keyword cross-domain matches before they reach a customer."""
    grant_blob = " ".join([
        str(gr.get("title") or ""), str(gr.get("summary") or ""),
        " ".join(str(t) for t in gr.get("tags", [])), str(gr.get("sector") or ""),
    ]).lower()
    client_blob = " ".join([
        str(payload.get("projectTitle") or ""), str(payload.get("keywords") or ""),
        str(payload.get("need") or ""), str(payload.get("notes") or ""),
    ]).lower()

    broad = {
        "project", "program", "support", "services", "community", "federal", "grant",
        "funding", "technology", "equipment", "training", "workforce", "energy",
        "business", "small", "rural", "development", "improve", "improvement",
    }
    client_terms = {
        w for w in re.findall(r"[a-z0-9]+", client_blob)
        if len(w) >= 5 and w not in broad
    }
    grant_terms = set(re.findall(r"[a-z0-9]+", grant_blob))
    distinctive_overlap = client_terms & grant_terms

    # Strong domain conflicts must be explicitly present in the customer's project.
    conflict_terms = {"nuclear", "radioactive", "petroleum", "pipeline"}
    if (conflict_terms & grant_terms) and not (conflict_terms & set(re.findall(r"[a-z0-9]+", client_blob))):
        return False, "Opportunity subject matter conflicts with the submitted project."
    if ("oil" in grant_terms or ("natural" in grant_terms and "gas" in grant_terms)) and not any(x in client_blob for x in ("oil", "natural gas", "petroleum")):
        return False, "Opportunity is focused on oil/gas rather than the submitted project."
    if "tribal" in grant_terms and "tribal" not in client_blob:
        return False, "Opportunity is focused on Tribal programs not identified in the intake."

    # Do not confuse capital/operational improvement projects with research, prototype,
    # emerging-technology, scale-up, or pre-pilot funding simply because both mention
    # manufacturing, energy, equipment, or technology.
    rd_signals = (
        "research and development", "research & development", "r&d", "prototype",
        "pre-pilot", "prepilot", "pre-piloting", "scale-up", "scale up",
        "emerging chemical technolog", "technology demonstration", "proof of concept",
    )
    client_rd_signals = (
        "research", "r&d", "prototype", "pilot", "scale-up", "scale up",
        "chemical technolog", "demonstration", "proof of concept", "commercialization",
    )
    if any(term in grant_blob for term in rd_signals) and not any(term in client_blob for term in client_rd_signals):
        return False, "Opportunity requires an R&D/pilot project not identified in the submitted project."

    # Education and small-business searches are especially vulnerable to broad R&D terms.
    required = 2 if applicant_type in ("EDU_K12", "HIGHER_ED", "HIGHER_ED_PUBLIC", "HIGHER_ED_PRIVATE", "RESEARCH_INSTITUTION", "SMALL_BUSINESS", "FOR_PROFIT") else 1
    if len(distinctive_overlap) < required:
        return False, "Insufficient project-specific overlap after removing broad search terms."
    return True, ""


def _purchaseable_fit(gr: Dict[str, Any]) -> bool:
    return gr.get("fit") in ("Strong Match", "Possible Match") and bool(gr.get("purchasable"))

def _grant_key(gr: Dict[str, Any]) -> str:
    return _first_identifier(gr, "opp_id", "opportunity_id", "opp_number", "opportunity_number") or str(gr.get("title") or "").strip().lower()

def score_grant(
    gr: Dict[str, Any], category: str, kws: List[str], amount: float
) -> Dict[str, Any]:
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
    fit_notes.append(f"Applicant category passed preliminary Grants.gov synopsis screening for {applicant_type}; all additional eligibility conditions still require verification in the official notice.")

    # 2) keyword overlap
    tags = normalized_tags(gr.get("tags", []))
    summary_tokens = normalized_tags(_tokenize_text(gr.get("summary", "")))
    keyword_terms = set()
    for token in kws:
        keyword_terms.update([w for w in token.split() if len(w) > 2])
    grant_terms = set()
    for token in tags + summary_tokens:
        grant_terms.update([w for w in token.split() if len(w) > 2])
    title_terms = normalized_tags(_tokenize_text(gr.get("title", "")))
    program_terms = normalized_tags(_tokenize_text(gr.get("program", "")))
    overlap = (
        set(kws)
        & (set(tags) | set(summary_tokens) | set(title_terms) | set(program_terms))
    ) | (keyword_terms & grant_terms)
    if overlap:
        score += min(len(overlap), 5) * 8
        fit_notes.append("Keyword overlap: " + ", ".join(sorted(overlap)) + ".")
    else:
        if kws:
            score -= 25
            fit_notes.append("Weak keyword overlap with this opportunity.")

    # 3) category relevance
    if requested_sector and grant_sector:
        if requested_sector == grant_sector:
            score += 30
            fit_notes.append(f"Sector aligned: {requested_sector}.")
        else:
            score -= 28
            fit_notes.append(
                f"Sector mismatch: client {requested_sector}, program {grant_sector}."
            )

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
        if max_amt > 0:
            utilization_ratio = amount / max_amt
            if 0.4 <= utilization_ratio <= 0.95:
                score += 6
                fit_notes.append(
                    "Requested funding is well-aligned with the published award range."
                )

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
        fit_notes.append(
            f"Requires approximately {req_match}% local match (cash or in-kind)."
        )

    if kws and overlap:
        score += min(len(set(overlap)), 4) * 2
    fit = (
        "Strong Match"
        if score >= 130
        else "Possible Match" if score >= 95 else "Low Match"
    )
    return {"score": score, "fit": fit, "fit_notes": " ".join(fit_notes)}


def infer_client_sector(kws: List[str]) -> str:
    keyword_blob = " ".join(kws)
    sector_rules = [
        (
            "agriculture / rural development",
            [
                "agriculture",
                "agricultural",
                "farming",
                "farm operation",
                "ranching",
                "food systems",
                "agricultural science",
                "agricultural education",
                "rural development",
            ],
        ),
        (
            "energy / manufacturing efficiency",
            ["energy efficiency", "rural energy", "energy", "ventilation", "efficiency", "manufacturing equipment"],
        ),
        (
            "telehealth / healthcare",
            [
                "telehealth",
                "health",
                "healthcare",
                "patient",
                "clinic",
                "elderly",
                "remote monitoring",
                "digital health",
            ],
        ),
        (
            "workforce development",
            [
                "workforce",
                "apprenticeship",
                "credential",
                "certification",
                "skilled trades",
                "manufacturing",
                "upskilling",
            ],
        ),
        (
            "education / STEM",
            [
                "education",
                "school",
                "classroom",
                "teacher",
                "stem",
                "student",
                "after school",
            ],
        ),
        (
            "housing / community development",
            [
                "housing",
                "community development",
                "revitalization",
                "homeless",
                "neighborhood",
            ],
        ),
        (
            "public safety / emergency management",
            [
                "public safety",
                "emergency",
                "flood",
                "disaster",
                "mitigation",
                "response",
            ],
        ),
        (
            "conservation / environment",
            [
                "conservation",
                "wetlands",
                "habitat",
                "ecosystem",
                "climate",
                "restoration",
                "wildlife",
            ],
        ),
        (
            "arts / culture",
            [
                "arts",
                "culture",
                "storytelling",
                "creative",
                "media",
                "youth empowerment",
            ],
        ),
        (
            "entrepreneurship / innovation",
            [
                "innovation",
                "startup",
                "prototype",
                "research",
                "commercialization",
                "entrepreneurship",
            ],
        ),
    ]
    for sector, needles in sector_rules:
        if any(n in keyword_blob for n in needles):
            return sector
    return ""


def _student_applicant_opportunity(gr: Dict[str, Any]) -> bool:
    """Return True only when the funding notice appears to require a student as applicant.

    GrantForgeUSA intentionally does not offer student-aid or student-applicant services.
    Generic grants that merely serve students are not excluded.
    """
    text = " ".join(
        str(gr.get(key) or "")
        for key in ("title", "eligibility_text", "summary")
    ).lower()
    if not text.strip():
        return False

    # Direct financial-aid / student-aid surfaces are always out of scope.
    if any(term in text for term in ("fafsa", "federal pell grant", "student financial aid")):
        return True

    # Restrictive applicant language: the student is the applicant, not merely a beneficiary.
    patterns = (
        r"(?:seeking|invites?)\s+(?:applications?|proposals?)\s+from[^.]{0,180}\bstudents?\b",
        r"\bapplicants?\b[^.]{0,100}\bmust\b[^.]{0,80}\bstudents?\b",
        r"\bonly\b[^.]{0,80}\bstudents?\b[^.]{0,80}\b(?:apply|applicant)",
        r"\bstudents?\b[^.]{0,140}\b(?:eligible to apply|may apply|to apply for)\b",
    )
    return any(re.search(pattern, text, flags=re.I) for pattern in patterns)


def _eligibility_needles(applicant_type: str) -> Tuple[str, ...]:
    return {
        "EDU_K12": ("independent school district", "school district", "local education agency", "education agency", "k-12 school", "k12 school"),
        "HIGHER_ED": ("institution of higher education", "institutions of higher education", "college", "colleges", "university", "universities", "higher education"),
        "HIGHER_ED_PUBLIC": ("public institution of higher education", "public institutions of higher education", "state controlled institution", "public college", "public university", "college", "colleges", "university", "universities"),
        "HIGHER_ED_PRIVATE": ("private institution of higher education", "private institutions of higher education", "private college", "private university", "college", "colleges", "university", "universities"),
        "RESEARCH_INSTITUTION": ("research institution", "research institutions", "research organization", "research organizations", "university research foundation", "research foundation", "research foundations"),
        "NONPROFIT_501C3": ("501(c)(3)", "501c3", "nonprofit", "non-profit"),
        "NONPROFIT": ("nonprofit", "non-profit", "community-based organization", "community organization", "faith-based organization"),
        "SMALL_BUSINESS": ("small business", "small businesses", "sbir", "sttr"),
        "FOR_PROFIT": ("for-profit", "for profit", "commercial organization", "businesses"),
        "GOV_LOCAL": ("local government", "county government", "city or township government", "municipality", "special district", "units of local government"),
        "GOV_STATE": ("state government", "state governments", "state agency", "state agencies"),
        "TRIBAL": ("tribal government", "tribal governments", "tribal organization", "tribal organizations", "indian tribe", "native american tribal"),
        "HOUSING": ("public housing authority", "public housing authorities", "indian housing authority", "housing authority"),
        "INDIVIDUAL": ("individual applicant", "individual applicants", "individuals"),
        "OTHER": ("other eligible applicant", "other eligible applicants"),
    }.get(applicant_type, ())


def _eligibility_text_is_restrictive(text: str) -> bool:
    lowered = (text or "").lower()
    signals = (
        "eligible applicants are limited to",
        "eligible applicants include only",
        "applications may only be submitted by",
        "applications can only be submitted by",
        "applicants are limited to",
        "eligibility is limited to",
        "only eligible applicants",
        "may only apply",
        "must be one of",
        "must meet all of the following",
        "eligible to receive direct awards",
    )
    return any(signal in lowered for signal in signals)


def _is_eligible_for_applicant(gr: Dict[str, Any], applicant_type: str) -> bool:
    """Conservatively validate applicant eligibility against official codes and restrictions.

    Dedicated Grants.gov applicant codes establish the broad applicant class. When the NOFO's
    additional-eligibility text explicitly narrows that class, the applicant class must also be
    positively named in that restriction text. Code 25 (Others) always requires positive free-text
    confirmation. Student-applicant opportunities remain outside GrantForgeUSA scope.
    """
    if _student_applicant_opportunity(gr):
        return False

    code_map = {
        "EDU_K12": {"05", "99"},
        "HIGHER_ED": {"06", "20", "99"},
        "HIGHER_ED_PUBLIC": {"06", "99"},
        "HIGHER_ED_PRIVATE": {"20", "99"},
        "RESEARCH_INSTITUTION": {"99"},
        "NONPROFIT_501C3": {"12", "99"},
        "NONPROFIT": {"12", "13", "99"},
        "SMALL_BUSINESS": {"23", "99"},
        "FOR_PROFIT": {"22", "99"},
        "GOV_LOCAL": {"01", "02", "04", "99"},
        "GOV_STATE": {"00", "99"},
        "TRIBAL": {"07", "11", "99"},
        "HOUSING": {"08", "99"},
        "INDIVIDUAL": {"21", "99"},
        "OTHER": {"99"},
    }
    codes = {
        str(code or "").strip().zfill(2)
        for code in (gr.get("eligibility_codes") or [])
        if str(code or "").strip()
    }
    free_text = str(gr.get("eligibility_text") or "").lower()
    needles = _eligibility_needles(applicant_type)

    # 'Others' is never treated as universal eligibility.
    if "25" in codes and not (codes & code_map.get(applicant_type, set())):
        if not free_text.strip():
            return False
        return any(term in free_text for term in needles)

    if codes & code_map.get(applicant_type, {"99"}):
        # A restrictive Additional Eligibility section can narrow a broad coded class.
        # If it does, require the submitted applicant class to be affirmatively represented.
        if free_text.strip() and _eligibility_text_is_restrictive(free_text):
            return any(term in free_text for term in needles)
        return True

    if codes:
        return False

    # Legacy/offline fixtures without numeric codes.
    title = (gr.get("title") or "").lower()
    tags = " ".join(normalized_tags(gr.get("tags", [])))
    elig = " ".join(str(e).lower() for e in gr.get("eligible_types", []))
    haystack = f"{title} {tags} {elig} {free_text}"
    if "unrestricted" in haystack and not _eligibility_text_is_restrictive(free_text):
        return True
    if "sbir" in haystack or "sttr" in haystack:
        return applicant_type == "SMALL_BUSINESS"
    if "cdbg" in haystack:
        return applicant_type == "GOV_LOCAL"
    return any(term in haystack for term in needles)


def shortlist(payload: Dict[str, Any], pinned_grant: Dict[str, Any] | None = None) -> Tuple[List[Dict[str, Any]], bool]:
    """
    Turn intake into 0–3 ranked federal opportunities.
    Production queries the live Grants.gov API first and uses the local dataset only as a resilient fallback.
    """
    payload = dict(payload or {})
    category = payload.get("category") or payload.get("who") or ""
    amount = _safe_float(payload.get("amountRequested"))
    applicant_type = normalize_applicant_type(category)
    kws = normalized_keywords(payload.get("keywords", ""))
    requested_sector = infer_client_sector(kws)
    state_value = payload.get("state") or payload.get("eligible_state") or ""

    live_grants_enabled = os.getenv("LIVE_GRANTS_ENABLED", "true").lower() != "false"
    if pinned_grant:
        grants = [pinned_grant]
    elif live_grants_enabled:
        live_query = " ".join(filter(None, [payload.get("projectTitle", ""), payload.get("keywords", "")])).strip()
        grants = search_live_grants(live_query, applicant_type=applicant_type, sector=requested_sector) if live_query else []
        if not grants:
            return [], False
    else:
        grants = _read_json(GRANTS_PATH) or []
    include_expired = bool(payload.get("includeExpired"))

    rows = []

    def build_rows(eligibility_required: bool) -> List[Dict[str, Any]]:
        built: List[Dict[str, Any]] = []
        for gr in grants:
            # GrantForgeUSA does not sell student-aid or student-applicant services.
            if _student_applicant_opportunity(gr):
                continue

            # hide expired unless explicitly requested
            close_date = gr.get("close_date") or gr.get("deadline") or ""
            is_expired = _is_expired(close_date)
            if not include_expired and is_expired:
                continue

            if eligibility_required and not _is_eligible_for_applicant(gr, applicant_type):
                continue

            geography_ok, geography_note = _geography_compatible(gr, state_value)
            funding_ok, funding_note = _funding_range_compatible(gr, amount)
            relevance_ok, relevance_note = _relevance_compatible(gr, payload, applicant_type)
            if not geography_ok or not funding_ok or not relevance_ok:
                continue

            s = score_grant(gr, category, kws, amount)
            purchasable = s["fit"] in ("Strong Match", "Possible Match")

            url = grant_display_url(gr)
            built.append(
                {
                    "title": gr.get("title"),
                    "program": gr.get("program")
                    or gr.get("program_id")
                    or gr.get("program_url")
                    or "unknown",
                    "program_url": url,
                    "program_id": gr.get("program_id", ""),
                    "opp_id": gr.get("opp_id") or gr.get("opportunity_id") or "",
                    "opp_number": gr.get("opp_number")
                    or gr.get("opportunity_number")
                    or "",
                    "official_url": grant_display_url(gr),
                    "amount": f"${int(_safe_float(gr.get('max_amount'), 0)):,.0f}",
                    "deadline": close_date or "TBA",
                    "fit": s["fit"],
                    "score": s["score"],
                    "fit_notes": s["fit_notes"],
                    "purchasable": purchasable,
                    "screening_notes": " ".join(n for n in (geography_note, funding_note, relevance_note) if n),
                    "min_amount": _safe_float(gr.get("min_amount"), 0),
                    "requires_match_percent": gr.get("requires_match_percent", 0),
                    "cost_sharing_required": gr.get("cost_sharing_required"),
                    "max_amount": _safe_float(gr.get("max_amount"), 0),
                    "tags": gr.get("tags", []),
                    "sector": gr.get("sector", ""),
                    "summary": gr.get("summary", ""),
                    "source": gr.get("source", "GrantForgeUSA verified fallback dataset"),
                    "level": "Federal",
                }
            )
        return built

    rows = build_rows(eligibility_required=True)

    rows.sort(
        key=lambda r: (
            _safe_float(r.get("score"), 0),
            _safe_float(r.get("max_amount"), 0),
        ),
        reverse=True,
    )

    viable_rows = [r for r in rows if _purchaseable_fit(r)]
    has_strong_matches = any(r.get("fit") == "Strong Match" for r in viable_rows)
    return viable_rows[:3], has_strong_matches


def _rotate_payment_log_if_needed() -> None:
    if not os.path.exists(LOG_PATH):
        return
    cutoff = datetime.utcnow() - timedelta(days=LOG_RETENTION_DAYS)
    try:
        df = pd.read_csv(LOG_PATH)
        if "ts_utc" in df.columns:
            parsed = pd.to_datetime(df["ts_utc"], errors="coerce", utc=True)
            df = df.loc[(parsed.isna()) | (parsed >= cutoff)]
            df.to_csv(LOG_PATH, index=False)
    except Exception:
        return


def _append_payment_log_row(row: Dict[str, Any]) -> None:
    try:
        _rotate_payment_log_if_needed()
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
            out.append(
                f"Purchase starter robotics/tech kits and integrate weekly {k.upper()} labs for {audience or 'participants'}."
            )
        elif k in ("equipment", "supplies"):
            out.append(
                "Acquire durable classroom equipment and consumable supplies required to deliver activities."
            )
        elif k in (
            "training",
            "workshop",
            "professional",
            "professional development",
            "pd",
        ):
            out.append(
                "Provide teacher/staff PD workshops to ensure safe, effective program delivery."
            )
        elif k in ("after-school", "afterschool", "tutoring"):
            out.append(
                "Launch a structured after-school tutoring/enrichment block with pre/post skill checks."
            )
        elif k in ("cte", "workforce"):
            out.append(
                "Align activities to CTE/workforce competencies with employer input and mock assessments."
            )
        else:
            out.append(
                f"Implement targeted activities related to “{display_k}” with measurable outputs."
            )
    return out


def _mk_evaluation_lines(audience: str) -> List[str]:
    who = audience or "participants"
    return [
        f"Track attendance and dosage for all {who}.",
        "Use short pre/post assessments tied to lesson objectives.",
        "Collect teacher/facilitator observations and student feedback.",
    ]


def build_narrative(intake: Dict[str, Any], grant: Dict[str, Any]) -> str:
    """Build an applicant-aware proposal draft without inventing facts, metrics, or compliance claims."""
    intake = dict(intake or {})
    org = _organization_name(intake)
    project = (intake.get("projectTitle") or "Proposed Project").strip()
    category = (intake.get("category") or intake.get("who") or "eligible applicant").strip()
    applicant_type = normalize_applicant_type(category)
    audience = (intake.get("audience") or "the intended beneficiaries").strip().rstrip(".")
    timeline = (intake.get("timeline") or "the proposed grant period").strip().rstrip(".")
    need = (intake.get("need") or "").strip()
    notes = (intake.get("notes") or "").strip()
    amount = _safe_float(intake.get("amountRequested"))
    annual_budget = _safe_float(intake.get("annualBudget"), 0)
    kws = normalized_keywords((intake.get("keywords") or "").strip())
    sector = infer_client_sector(kws) or "the proposed project area"
    g_title = _sanitize_text(grant.get("title") or "Federal funding opportunity", 240)
    g_program = _sanitize_text(grant.get("program") or grant.get("agency") or "Federal program", 240)
    g_deadline = _sanitize_text(grant.get("deadline") or "TBA", 80)
    g_min = _safe_float(grant.get("min_amount"), 0)
    g_max = _safe_float(grant.get("max_amount"), 0)
    g_summary = _sanitize_text(grant.get("summary") or "", 900)
    g_match = int(_safe_float(grant.get("requires_match_percent"), 0))
    g_cost_share = grant.get("cost_sharing_required")
    req_str = f"${amount:,.0f}" if amount > 0 else "the amount shown in the final budget"
    budget_str = f"${annual_budget:,.0f}" if annual_budget > 0 else "not supplied"
    focus = ", ".join(kws[:5]) if kws else project
    need_text = need or notes or f"The applicant identified a need directly related to {focus}."
    profile = {
        "EDU_K12": ("education applicant", "instructional or school-system delivery", "learners, educators, and the school community"),
        "HIGHER_ED": ("higher-education or research institution", "research, teaching, institutional, or sponsored-program delivery", "the identified research, education, or community beneficiaries"),
        "HIGHER_ED_PUBLIC": ("public college or university", "research, teaching, institutional, extension, or sponsored-program delivery", "the identified research, education, or community beneficiaries"),
        "HIGHER_ED_PRIVATE": ("private college or university", "research, teaching, institutional, or sponsored-program delivery", "the identified research, education, or community beneficiaries"),
        "RESEARCH_INSTITUTION": ("research institution or university research foundation", "research or sponsored-program delivery", "the identified research or community beneficiaries"),
        "NONPROFIT_501C3": ("501(c)(3) nonprofit", "mission-driven program delivery", "the identified beneficiaries and community partners"),
        "NONPROFIT": ("nonprofit or community organization", "mission-driven program delivery", "the identified beneficiaries and community partners"),
        "SMALL_BUSINESS": ("small business", "business, innovation, operational, or commercialization activity", "the business, workforce, customers, and other stated beneficiaries"),
        "FOR_PROFIT": ("for-profit organization", "business, innovation, operational, or commercialization activity", "the organization and other stated beneficiaries"),
        "GOV_LOCAL": ("local-government applicant", "public-service, infrastructure, or community implementation", "residents and other stated public beneficiaries"),
        "GOV_STATE": ("state-government applicant", "statewide or agency-led implementation", "the stated public beneficiaries"),
        "TRIBAL": ("Tribal applicant", "Tribal government or organization-led implementation", "the stated Tribal community beneficiaries"),
        "HOUSING": ("public-housing applicant", "housing, resident-service, or community implementation", "residents and other stated beneficiaries"),
        "INDIVIDUAL": ("individual applicant", "applicant-led project implementation", "the stated beneficiaries"),
        "OTHER": ("eligible applicant", "project implementation", "the stated beneficiaries"),
    }.get(applicant_type, ("eligible applicant", "project implementation", "the stated beneficiaries"))
    entity_label, delivery_frame, beneficiary_frame = profile
    opportunity_range = []
    if g_min > 0:
        opportunity_range.append(f"published floor ${g_min:,.0f}")
    if g_max > 0:
        opportunity_range.append(f"published ceiling ${g_max:,.0f}")
    range_text = ", ".join(opportunity_range) if opportunity_range else "award range not captured in the current synopsis"
    if g_match > 0:
        match_text = f" A {g_match}% match is listed and must be verified against the official notice."
    elif g_cost_share is True:
        match_text = " The Grants.gov synopsis indicates cost sharing or matching is required; the amount, basis, and any waiver must be verified in the official notice."
    elif g_cost_share is False:
        match_text = " The Grants.gov synopsis indicates cost sharing or matching is not required; verify the current official notice before submission."
    else:
        match_text = " Cost-sharing requirements were not conclusively captured from the synopsis and must be verified in the official notice."
    synopsis_text = f" The current Grants.gov synopsis states: {g_summary}" if g_summary else ""
    activity_language = {
        "energy / manufacturing efficiency": "procurement or installation planning, operational implementation, performance measurement, and documented efficiency results",
        "telehealth / healthcare": "service design, implementation protocols, access measures, quality monitoring, and documented health-service outcomes",
        "workforce development": "participant recruitment, training or credential activities, employer/partner coordination, and employment or skill outcomes",
        "education / STEM": "instructional or research design, educator/participant engagement, implementation fidelity, and learning or research outcomes",
        "housing / community development": "project delivery, resident/community engagement, implementation milestones, and measurable community outcomes",
        "public safety / emergency management": "readiness activities, implementation milestones, interagency coordination, and measurable safety or resilience outcomes",
        "conservation / environment": "field or implementation activities, stewardship milestones, monitoring, and measurable environmental outcomes",
        "arts / culture": "creative or cultural activities, public engagement, implementation milestones, and measurable participation or access outcomes",
        "entrepreneurship / innovation": "research or development activity, validation milestones, technical progress, and commercialization or adoption measures",
    }.get(sector, "defined project activities, documented milestones, responsible implementation, and measurable outcomes")
    sections = [
        "Executive Summary\n" + f"{org}, a {entity_label}, seeks {req_str} through {g_title} to carry out '{project}' over {timeline}. The project is intended to serve {audience}. Based on the information supplied by the applicant, the proposed work centers on {focus} and falls within {sector}. This draft frames the project around the selected federal opportunity while preserving applicant responsibility for every factual statement, target, attachment, certification, and final submission decision.",
        "Funding Opportunity Alignment\n" + f"Selected opportunity: {g_title}. Program/agency reference: {g_program}. Current deadline captured by GrantForgeUSA: {g_deadline}. Funding information captured from the opportunity: {range_text}. The requested amount is {req_str}.{match_text}{synopsis_text} Before submission, the applicant must compare this draft with the complete current notice, amendments, eligibility rules, required registrations, and application package.",
        "Statement of Need\n" + f"The applicant described the underlying need as follows: {need_text} The proposal should support this statement with applicant-verified local data, baseline information, documented demand, prior results, citations, or other evidence required by the funding notice. GrantForgeUSA does not invent those facts when they are not supplied in the intake.",
        "Program Description\n" + f"'{project}' will use {delivery_frame} focused on {activity_language}. The working scope is designed around {audience} and the applicant's stated priorities: {focus}. Final activities, quantities, locations, staffing assignments, partners, procurement specifications, and methods should be confirmed by {org} before submission and revised wherever the official notice requires a different structure.",
        "Goals, Objectives, and Performance Measures\n" + f"The draft goal is to address the stated need through a focused {sector} project with measurable implementation and outcome evidence. Before submission, {org} should set applicant-owned targets for: (1) the quantity and timing of major activities or deliverables; (2) the primary outcome expected for {audience}; and (3) completion of required project, reporting, and compliance milestones. Baselines and numerical targets should come from the applicant's records, research plan, operating data, or other defensible evidence rather than default percentages.",
        "Implementation Plan\n" + f"The proposed period is {timeline}. A final work plan should identify the responsible lead for each major task, milestone dates, partner or vendor responsibilities, dependencies, and the evidence used to document completion. The implementation sequence should cover startup/readiness, core delivery, monitoring and adjustment, and closeout/reporting. Where the notice uses required phases or milestones, those requirements supersede this general structure.",
        "Target Population / Beneficiaries\n" + f"The intake identifies {audience} as the primary audience or beneficiary group. For this {entity_label}, the proposal should explain how that audience connects to {beneficiary_frame}, why the project design is appropriate for them, and how participation, access, research subjects, customers, residents, or other beneficiaries will be defined where applicable. Any demographic, geographic, or participation claims must be verified by the applicant.",
        "Organizational Capacity\n" + f"The applicant reported an annual operating or organizational budget of approximately {budget_str}. The final application should describe only verified capacity: authorized leadership, relevant personnel or investigators, prior experience, required registrations, financial systems, facilities, partnerships, and other qualifications specifically requested by the notice. This draft does not assume that {org} possesses a certification, internal control, prior award history, staffing level, or partnership unless the applicant supplied and confirms that fact.",
        "Budget Use\n" + f"The working request is {req_str}. The final budget narrative should connect each cost directly to a confirmed project activity and use the cost categories, allowability rules, indirect-cost treatment, match requirements, and documentation standards in the official notice. GrantForgeUSA does not treat a cost as federally allowable merely because it was entered in the intake. The applicant should reconcile the narrative, line-item budget, quotes, calculations, and requested federal share before submission.",
        "Sustainability\n" + f"The sustainability section should explain which project benefits or capabilities {org} intends to maintain after the federal period and identify only realistic, applicant-supported continuation resources. Depending on the project, those may include institutional adoption, operating revenue, future grants, partner commitments, maintenance planning, dissemination, commercialization, or integration into ongoing operations. No continuation funding is assumed in this draft.",
        "Applicant Validation Required Before Submission\n" + f"This is a customized working proposal draft, not an agency approval or eligibility determination. {org} must verify the current notice for {g_title}, confirm applicant eligibility, replace or substantiate any draft assumption, finalize all numerical targets and budget details, complete required forms and attachments, obtain signatures/certifications, and submit through the official channel by the controlling deadline.",
    ]
    return "\n\n".join(sections)

def build_draft_text(intake: Dict[str, Any], grant: Dict[str, Any]) -> str:
    """Backward-compatible alias for narrative builder."""
    return build_narrative(intake, grant)


def make_pdf(order_id: str, payload: Dict[str, Any]) -> str:
    """Generate a paginated proposal PDF with protected header/footer space."""
    os.makedirs(PDF_DIR, exist_ok=True)
    pdf_path = os.path.join(PDF_DIR, f"{order_id}.pdf")
    created_at = _now_utc()
    def esc(value: Any) -> str:
        return str(value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    styles = getSampleStyleSheet()
    body = styles["BodyText"].clone("GrantForgeBody"); body.fontName = "Helvetica"; body.fontSize = 10; body.leading = 14; body.spaceAfter = 8
    heading = styles["Heading2"].clone("GrantForgeHeading"); heading.fontName = "Helvetica-Bold"; heading.fontSize = 12; heading.leading = 15; heading.spaceBefore = 8; heading.spaceAfter = 6
    small = styles["BodyText"].clone("GrantForgeSmall"); small.fontName = "Helvetica"; small.fontSize = 9; small.leading = 12; small.spaceAfter = 5
    doc = SimpleDocTemplate(pdf_path, pagesize=letter, leftMargin=54, rightMargin=54, topMargin=72, bottomMargin=78, title=f"GrantForgeUSA Proposal Draft - {order_id}", author="GrantForgeUSA, LLC")
    def page_frame(c, _doc):
        c.saveState(); c.setFont("Helvetica-Bold", 11); c.drawString(54, 756, "GrantForgeUSA | Proposal Draft"); c.setFont("Helvetica", 8.5); c.drawString(54, 742, f"Order: {order_id} | Created: {created_at}"); c.setFont("Helvetica-Oblique", 8); c.drawString(54, 36, "Customized drafting service - verify against the current official notice before submission."); c.setFont("Helvetica", 8); c.drawRightString(558, 36, f"Page {_doc.page}"); c.restoreState()
    story = []
    draft_body = payload.get("draft_body")
    if isinstance(draft_body, str) and draft_body.strip():
        story.append(Paragraph("Grant Narrative", heading))
        for block in draft_body.split("\n\n"):
            block = block.strip()
            if not block: continue
            lines = block.split("\n", 1)
            if len(lines) == 2 and len(lines[0]) <= 90:
                story.append(Paragraph(esc(lines[0]), heading)); story.append(Paragraph(esc(lines[1]).replace("\n", "<br/>"), body))
            else:
                story.append(Paragraph(esc(block).replace("\n", "<br/>"), body))
    else:
        story.append(Paragraph("GrantForgeUSA Order Details", heading))
        for key, value in payload.items(): story.append(Paragraph(f"<b>{esc(key)}:</b> {esc(value)}", body))
    story.append(Spacer(1, 10)); story.append(Paragraph("Grant Opportunity Details", heading))
    details = [("Project title", payload.get("projectTitle", "")), ("Applicant type", payload.get("category", "")), ("Requested amount", f"${_safe_float(payload.get('amountRequested'), 0):,.2f}"), ("Service fee", f"${_safe_float(payload.get('price'), 0):,.2f}"), ("Recommended opportunity", payload.get("grant_title", "")), ("Program", payload.get("grant_program", "")), ("Deadline", payload.get("grant_deadline", ""))]
    for label, value in details: story.append(Paragraph(f"<b>{esc(label)}:</b> {esc(value)}", body))
    grant_url = _safe_grants_url(payload.get("grant_url") or "")
    if grant_url: story.append(Paragraph(f'<b>Official opportunity:</b> <a href="{esc(grant_url)}">{esc(grant_url)}</a>', body))
    recommendations = payload.get("recommendations") if isinstance(payload.get("recommendations"), list) else []
    if recommendations:
        story.append(Spacer(1, 6)); story.append(Paragraph("Other Screened Opportunities", heading))
        for item in recommendations[:10]:
            if not isinstance(item, dict): continue
            title = esc(item.get("title") or "Federal funding opportunity"); url = _safe_grants_url(item.get("program_url") or item.get("url") or "")
            story.append(Paragraph(f'• <a href="{esc(url)}">{title}</a>' if url else f"• {title}", small))
    story.append(Spacer(1, 12)); story.append(Paragraph("<b>Final review notice:</b> GrantForgeUSA is an independent private drafting service. The customer must verify applicant eligibility, all facts, the current funding notice, required forms, certifications, attachments, budget, and final submission. Funding is not guaranteed. Customized drafting services are final-sale subject to the Terms of Service and applicable law.", small))
    doc.build(story, onFirstPage=page_frame, onLaterPages=page_frame)
    return pdf_path

@app.before_request
def _apply_rate_limit():
    if request.method == "OPTIONS":
        return None
    route = request.path
    if route in RATE_LIMITS and _rate_limit_exceeded(route):
        return (
            jsonify(ok=False, error="Rate limit exceeded. Please try again shortly."),
            429,
        )
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
        ts=_now_utc(),
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
    debug_token = os.getenv("DEBUG_AUTH_TOKEN", "")
    provided = request.headers.get("X-Debug-Auth", "")
    is_operator = (
        DEBUG_ENDPOINTS_ENABLED
        and bool(debug_token)
        and secrets.compare_digest(provided, debug_token)
    )
    if not is_operator:
        return jsonify(ok=False, error="Unauthorized"), 401
    return jsonify(ok=True, ts=_now_utc(), message="Debug endpoints enabled")


# ---------------- shortlist/search ----------------
@app.post("/questionnaire")
def questionnaire():
    try:
        data = sanitize_payload(request.get_json(force=True) or {})
    except Exception:
        return jsonify(ok=False, error="Invalid JSON"), 400

    missing_err = _validate_required_intake(data)
    if missing_err:
        return jsonify(ok=False, error=missing_err), 400

    org = _organization_name(data)
    results, has_strong_matches = shortlist(data)
    notice = ""
    if results and not has_strong_matches:
        notice = "Potential federal matches found. Review the fit notes and official notice carefully before purchasing."
    elif not results:
        notice = "No purchase-ready federal opportunity matched the information provided. Refine the project details, funding request, or search terms and try again."
    return jsonify(ok=True, organization=org, results=results, notice=notice)


@app.post("/search")
def search():
    return questionnaire()


# ---------------- contextual preview ----------------
@app.post("/preview")
def preview():
    try:
        data = sanitize_payload(request.get_json(force=True) or {})
    except Exception:
        return jsonify(ok=False, error="Invalid JSON"), 400

    missing_err = _validate_required_intake(data)
    if missing_err:
        return jsonify(ok=False, error=missing_err), 400

    requested_grant = data.get("grant") or {}
    pinned = {}
    requested_id = _first_identifier(requested_grant, "opp_id", "opportunity_id")
    if requested_id and "Grants.gov" in str(requested_grant.get("source") or ""):
        pinned = fetch_live_grant(requested_id)
    short, _ = shortlist(data, pinned_grant=pinned) if pinned else shortlist(data)
    if not short:
        return jsonify(ok=False, error="No purchase-ready federal opportunity matches this intake."), 422
    grant = short[0]
    if requested_grant:
        requested_key = _grant_key(requested_grant)
        grant = next((item for item in short if _grant_key(item) == requested_key), {})
        if not grant:
            return jsonify(ok=False, error="This opportunity no longer passes GrantForgeUSA screening for the submitted intake."), 422

    # Build full draft, then shorten for preview
    full_draft = build_narrative(data, grant)
    paras = full_draft.split("\n\n")
    preview_text = "\n\n".join(paras[:4])  # first few sections only

    return jsonify(ok=True, summary=preview_text)


# ---------------- Stripe Checkout ----------------
@app.post("/create-checkout-session")
def create_checkout_session():
    if not (stripe.api_key and PUBLISHABLE_KEY):
        return jsonify(ok=False, error="Stripe keys are not configured"), 400

    try:
        data = sanitize_payload(request.get_json(force=True) or {})
    except Exception:
        return jsonify(ok=False, error="Invalid JSON"), 400

    data = dict(data or {})
    missing_err = _validate_required_intake(data)
    if missing_err:
        return jsonify(ok=False, error=missing_err), 400

    org = _organization_name(data, default="Customer")
    category = (data.get("category") or data.get("who") or "Other").strip()
    amount_req = _safe_float(data.get("amountRequested"))
    annual_budget = _safe_float(data.get("annualBudget"), 0)
    requested_grant = data.get("grant") or {}

    chk = fraud_check(category, amount_req)
    if not chk["ok"]:
        return jsonify(ok=False, error=chk["msg"]), 400

    pinned = {}
    requested_id = _first_identifier(requested_grant, "opp_id", "opportunity_id")
    if requested_id and "Grants.gov" in str(requested_grant.get("source") or ""):
        pinned = fetch_live_grant(requested_id)
    short, _ = shortlist(data, pinned_grant=pinned) if pinned else shortlist(data)
    if not short:
        return jsonify(ok=False, error="No purchase-ready federal opportunity matches this intake."), 422
    requested_key = _grant_key(requested_grant)
    grant = next((item for item in short if _grant_key(item) == requested_key), {})
    if not grant or not _purchaseable_fit(grant):
        return jsonify(ok=False, error="Selected opportunity does not pass GrantForgeUSA purchase screening for this intake."), 422

    max_amt = _safe_float(grant.get("max_amount"), 0)
    if max_amt and amount_req > max_amt:
        return (
            jsonify(
                ok=False,
                error=f"Requested ${amount_req:,.0f} exceeds this program’s maximum (${max_amt:,.0f}).",
            ),
            400,
        )

    price = price_for(category, annual_budget)
    product_name = f"Grant Draft — {category}"

    order_id = datetime.utcnow().strftime("ORD-%Y%m%d-%H%M%S-%f")

    draft_body = build_narrative(data, grant)
    grant_url = grant_display_url(grant) if grant else ""
    recommendations = (
        data.get("recommendations")
        if isinstance(data.get("recommendations"), list)
        else []
    )

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
        "state": (data.get("state") or data.get("eligible_state") or "").strip(),
        "price": f"{price:.2f}",
        "refund_policy": "Final once customized generation begins; exceptions required by law or nondelivery.",
        "requester_ip": _client_ip(),
    }

    checkout_ref = secrets.token_urlsafe(18)
    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            phone_number_collection={"enabled": False},
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
            success_url=f"{FRONTEND_THANKS_URL}?ref={checkout_ref}",
            cancel_url=f"{FRONTEND_URL}",
            metadata=metadata,
        )
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 400

    with _CHECKOUT_REF_LOCK:
        _CHECKOUT_REF_STORE[checkout_ref] = {
            "session_id": session.id,
            "expires_at": datetime.utcnow() + timedelta(seconds=TOKEN_TTL_SECONDS),
            "used": False,
        }
    _store_draft(session.id, draft_body, recommendations)

    row = {
        "ts_utc": _now_utc(),
        "order_id": order_id,
        "organization_name": org,
        "session_id": session.id,
        "payment_status": "unpaid",
        "amount_total": price,
        "pdf_path": "",
        "paid": False,
    }
    _append_payment_log_row(row)

    return jsonify(
        ok=True,
        url=session.url,
        checkoutReference=checkout_ref,
        publishableKey=PUBLISHABLE_KEY,
    )


# ---------------- Stripe Webhook (reliable post-payment) ----------------
@app.post("/webhook/stripe")
def stripe_webhook():
    if not STRIPE_WEBHOOK_SECRET:
        return jsonify(ok=False, error="Webhook secret not configured"), 400

    payload = request.data
    sig_header = request.headers.get("Stripe-Signature", "")
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        return jsonify(ok=False, error=f"Signature verification failed: {e}"), 400

    if event["type"] == "checkout.session.completed":
        session_obj = event["data"]["object"]
        session_id = session_obj.get("id")
        md = session_obj.get("metadata") or {}

        row = find_log_by_session(session_id)
        order_id = (
            (row.get("order_id") if row else None)
            or md.get("order_id")
            or datetime.utcnow().strftime("ORD-%Y%m%d-%H%M%S-%f")
        )
        draft_payload = _load_draft(session_id)
        payload_for_pdf = dict(md)
        payload_for_pdf.update(
            {
                "payment_status": session_obj.get("payment_status"),
                "amount_total": session_obj.get("amount_total"),
                "currency": session_obj.get("currency"),
                "mode": session_obj.get("mode"),
                "draft_body": draft_payload.get("draft_body", ""),
                "recommendations": draft_payload.get("recommendations", []),
            }
        )
        try:
            pdf_path = make_pdf(order_id, payload_for_pdf)
            _update_payment_log_by(
                "session_id",
                session_id,
                {
                    "pdf_path": pdf_path,
                    "paid": True,
                    "payment_status": "paid",
                },
            )
        except Exception:
            pass

    return jsonify(ok=True)


# ---------------- Receipt / Download ----------------
@app.post("/create-download-token")
def create_download_token():
    raw_body = sanitize_payload(request.get_json(silent=True) or {})
    checkout_ref = _sanitize_text(raw_body.get("checkout_ref"), 200)
    if not checkout_ref:
        return jsonify(ok=False, error="missing checkout_ref"), 400

    session_id = _consume_checkout_ref(checkout_ref)
    if not session_id:
        return jsonify(ok=False, error="invalid or expired checkout reference"), 400

    if _is_session_already_downloaded(session_id):
        return (
            jsonify(ok=False, error="download already completed for this session"),
            409,
        )

    paid, _s, err = _stripe_session_paid(session_id)
    if err:
        return jsonify(ok=False, error=f"Stripe lookup failed: {err}"), 400
    if not paid:
        return jsonify(ok=False, error="payment not completed"), 402
    if not _session_belongs_requester(_s or {}):
        return jsonify(ok=False, error="session does not belong to requester"), 403

    token = _mint_download_token(session_id)
    _update_payment_log_by(
        "session_id", session_id, {"paid": True, "payment_status": "paid"}
    )
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
    if not _session_belongs_requester(s or {}):
        return jsonify(ok=False, error="session does not belong to requester"), 403

    if _is_session_already_downloaded(session_id):
        return jsonify(ok=False, error="download already completed for this order"), 409

    row = find_log_by_session(session_id)
    if not row:
        md = s.metadata or {}
        order_id = md.get("order_id") or datetime.utcnow().strftime(
            "ORD-%Y%m%d-%H%M%S-%f"
        )
        _append_payment_log_row(
            {
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
                "pdf_path": "",
                "paid": True,
            }
        )
        row = find_log_by_session(session_id)

    return jsonify(
        {
            "ok": True,
            "order_id": row.get("order_id", ""),
            "amount_total": row.get("price", 0),
            "paid": True,
            "grant_title": row.get("grant_title", ""),
            "download_path": f"/download-by-session?token={token}",
            "ts": _now_utc(),
        }
    )


@app.get("/download-by-session")
def download_by_session():
    try:
        token = request.args.get("token")
        if not token:
            return jsonify(ok=False, error="missing token"), 400

        session_id = _consume_token(token)
        if not session_id:
            return (
                jsonify(ok=False, error="invalid, expired, or already-used token"),
                400,
            )

        if _is_session_already_downloaded(session_id):
            return (
                jsonify(ok=False, error="download already completed for this order"),
                409,
            )

        paid, s, err = _stripe_session_paid(session_id)
        if err:
            return jsonify(ok=False, error=f"Stripe lookup failed: {err}"), 400
        if not paid:
            return jsonify(ok=False, error="payment not completed"), 402
        if not _session_belongs_requester(s or {}):
            return jsonify(ok=False, error="session does not belong to requester"), 403

        row = find_log_by_session(session_id)
        md = (s.metadata or {}) if s else {}
        order_id = (
            (row.get("order_id") if row else None)
            or md.get("order_id")
            or datetime.utcnow().strftime("ORD-%Y%m%d-%H%M%S-%f")
        )

        pdf_path = row.get("pdf_path") if row else ""
        if not isinstance(pdf_path, str):
            pdf_path = ""
        if not (pdf_path and os.path.exists(pdf_path)):
            draft_payload = _load_draft(session_id)
            pdf_payload = dict(md)
            pdf_payload["draft_body"] = draft_payload.get("draft_body", "")
            pdf_payload["recommendations"] = draft_payload.get("recommendations", [])
            pdf_path = make_pdf(order_id, pdf_payload)
            _update_payment_log_by(
                "session_id",
                session_id,
                {
                    "order_id": order_id,
                    "pdf_path": pdf_path,
                    "paid": True,
                    "payment_status": "paid",
                },
            )

        if not (pdf_path and os.path.exists(pdf_path)):
            return (
                jsonify(ok=False, error="PDF not found yet; try again in a moment."),
                404,
            )

        _mark_session_downloaded(session_id)
        name = os.path.basename(pdf_path) or f"{order_id}.pdf"
        return send_file(
            pdf_path, as_attachment=True, download_name=name, mimetype="application/pdf"
        )
    except Exception as e:
        return jsonify(ok=False, error=f"download route error: {e}"), 400


# ------------- main (optional local run) -------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
