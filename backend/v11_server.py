# GrantforgeUSA — v11.4 backend (TEST/LIVE READY)
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


STATE_NAME_BY_ABBR = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "DC": "District of Columbia",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
}


STATE_PORTALS = {
    "MN": {
        "name": "Minnesota",
        "url": "https://mn.gov/admin/citizen/grants/",
        "label": "Minnesota Grants Portal",
    },
}


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
    """
    Build a Grants.gov search URL using title + tags.
    If your grants.json has a direct funding-opportunity URL, that will be used instead.
    """
    q = "+".join(_norm_words(title)[:6] + [t.lower() for t in (tags or [])][:4])
    return f"https://www.grants.gov/search-grants?keywords={q}"


# -------- URL normalizer (force Grants.gov or fallback to its search) --------
def _ensure_http_url(url: str, title: str, tags: List[str]) -> str:
    if isinstance(url, str) and url.startswith(("http://", "https://")) and "grants.gov" in url:
        return url
    return fallback_grants_gov_url(title or "", tags or [])


def grant_display_url(gr: Dict[str, Any]) -> str:
    """
    Single place to decide which URL we treat as the 'official' link.
    If you later add 'funding_url' or similar to grants.json, prefer it here.
    """
    raw = gr.get("funding_url") or gr.get("program_url") or ""
    return _ensure_http_url(raw, gr.get("title", ""), gr.get("tags", []) or [])


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


def _state_full_name(state_abbrev: str) -> str:
    return STATE_NAME_BY_ABBR.get((state_abbrev or "").upper(), "")


def _state_search_terms(state_abbrev: str) -> List[str]:
    abbr = (state_abbrev or "").upper()
    full = _state_full_name(abbr)
    return [t.lower() for t in (abbr, full) if t]


def _grant_number(gr: Dict[str, Any]) -> str:
    for key in ("grant_number", "opportunity_number", "opportunityNumber", "program_id", "program"):
        val = (gr.get(key) or "").strip() if isinstance(gr.get(key), str) else gr.get(key)
        if val:
            return str(val)

    title = (gr.get("title") or "").strip()
    if "(" in title and ")" in title:
        inner = title.split("(")[-1].split(")")[0].strip()
        if inner and (inner.isupper() or any(ch.isdigit() for ch in inner)):
            return inner

    return ""


def _state_portal_result(state_abbrev: str) -> Dict[str, Any]:
    abbr = (state_abbrev or "").upper()
    state_name = _state_full_name(abbr) or abbr
    portal = STATE_PORTALS.get(abbr)
    if portal:
        return {
            "title": portal["label"],
            "program": "state-portal",
            "program_url": portal["url"],
            "amount": "Varies",
            "deadline": "Varies",
            "fit": "State",
            "fit_notes": f"Official state grants portal for {portal['name']}.",
            "requires_match_percent": 0,
            "max_amount": 0,
            "tags": ["State grants", portal["name"]],
            "grant_number": "",
            "opportunity_number": "",
            "level": "State",
        }

    query = f"{state_name} site:.gov grants funding opportunities".strip()
    search_url = f"https://search.usa.gov/search?query={query.replace(' ', '%20')}"
    return {
        "title": f"State Grants Portal Search — {state_name}",
        "program": "state-portal-search",
        "program_url": search_url,
        "amount": "Varies",
        "deadline": "Varies",
        "fit": "State",
        "fit_notes": "Search results focused on .gov grant and funding opportunities.",
        "requires_match_percent": 0,
        "max_amount": 0,
        "tags": ["State grants", state_name],
        "grant_number": "",
        "opportunity_number": "",
        "level": "State",
    }


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
    """
    Compute a score + qualitative fit and human-readable notes.
    Goal: more 'true' shortlisting based on your internal grants.json.
    """
    score = 0
    fit_notes: List[str] = []

    cat_lower = (category or "").lower()

    # category eligibility
    elig = [e.lower() for e in gr.get("eligible_types", [])]
    category_match = any(e in cat_lower for e in elig)
    category_terms = [t for t in _norm_words(category) if len(t) > 2]
    grant_text = " ".join([
        str(gr.get("title", "")),
        " ".join(gr.get("tags", []) or []),
        str(gr.get("geo_scope", "")),
    ]).lower()
    category_text_match = any(t in grant_text for t in category_terms)
    if category_match or category_text_match:
        score += 25
        fit_notes.append("Eligible applicant category appears aligned.")
    else:
        fit_notes.append("Category not an explicit match.")

    # amount window
    min_amt = _safe_float(gr.get("min_amount"), 0.0)
    max_amt = _safe_float(gr.get("max_amount"), 10**12)
    if amount < min_amt:
        fit_notes.append(f"Ask (${amount:,.0f}) is below minimum (${min_amt:,.0f}).")
    elif amount > max_amt:
        fit_notes.append(f"Ask (${amount:,.0f}) exceeds maximum (${max_amt:,.0f}).")
    else:
        score += 15

    # keywords vs tags
    tags = [t.lower() for t in gr.get("tags", [])]
    overlap = set(kws) & set(tags)
    if overlap:
        score += min(len(overlap), 4) * 10
        fit_notes.append("Good overlap with focus areas: " + ", ".join(sorted(overlap)) + ".")
    else:
        fit_notes.append("Limited keyword overlap with focus areas.")

    # deadline
    if _deadline_ok(gr.get("deadline", "")):
        score += 8
    else:
        fit_notes.append("Deadline has passed.")

    # state/region (if data present)
    states = [s.lower() for s in gr.get("eligible_states", [])]
    if states:
        if state and state.lower() in states:
            score += 10
            fit_notes.append(f"Applicant state appears within eligible states ({state}).")
        else:
            fit_notes.append("Applicant state may not be explicitly listed as eligible.")

    # state relevance boost using abbreviation + full name
    state_terms = _state_search_terms(state)
    if state_terms:
        search_blob = " ".join([
            str(gr.get("title", "")),
            str(gr.get("program", "")),
            str(gr.get("program_id", "")),
            str(gr.get("geo_scope", "")),
            " ".join(gr.get("tags", []) or []),
        ]).lower()
        if any(term in search_blob for term in state_terms):
            score += 8
            fit_notes.append("Opportunity text references the applicant’s state.")

    # prioritize larger opportunity size
    max_amt = _safe_float(gr.get("max_amount"), 0)
    if max_amt > 0:
        score += min(10, int(max_amt / 100000))

    # match % note
    req_match = int(gr.get("requires_match_percent", 0) or 0)
    if req_match > 0:
        fit_notes.append(f"Requires approximately {req_match}% local match (cash or in-kind).")

    fit = "High" if score >= 65 else "Medium" if score >= 35 else "Low"
    minimally_relevant = bool(overlap) or category_match or category_text_match
    return {
        "score": score,
        "fit": fit,
        "fit_notes": " ".join(fit_notes),
        "minimally_relevant": minimally_relevant,
        "keyword_overlap_count": len(overlap),
    }


def shortlist(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Turn intake into up to 12 strong matches from backend/data/grants.json.
    Data quality lives in grants.json; logic lives here.
    """
    grants = _read_json(GRANTS_PATH) or []
    category = payload.get("category") or payload.get("who") or ""
    amount = _safe_float(payload.get("amountRequested"))
    kws = _norm_words(payload.get("keywords", ""))
    state = (payload.get("state") or "").strip()
    include_expired = payload.get("includeExpired", False)

    rows = []
    all_scored_rows = []
    for gr in grants:
        expired = _is_expired(gr.get("deadline", ""))
        if not include_expired and expired:
            continue

        s = score_grant(gr, category, kws, amount, state)

        url = grant_display_url(gr)
        row = {
            "title": gr.get("title"),
            "program": gr.get("program") or gr.get("program_id") or gr.get("program_url") or "unknown",
            "program_url": url,  # not shown on free UI, used in paid PDF
            "amount": f"${int(_safe_float(gr.get('max_amount'), 0)):,.0f}",
            "deadline": gr.get("deadline", "TBA"),
            "fit": s["fit"],
            "fit_notes": s["fit_notes"],
            "score": s["score"],
            "requires_match_percent": gr.get("requires_match_percent", 0),
            "max_amount": _safe_float(gr.get("max_amount"), 0),
            "tags": gr.get("tags", []),
            "grant_number": _grant_number(gr),
            "opportunity_number": _grant_number(gr),
            "level": "Federal",
            "expired": expired,
        }
        all_scored_rows.append(row)
        if s["minimally_relevant"]:
            rows.append(row)

    if len(rows) < 10:
        rows = all_scored_rows

    rows.sort(
        key=lambda r: (
            -int(r.get("score", 0)),
            0 if r["fit"] == "High" else 1 if r["fit"] == "Medium" else 2,
            -_safe_float(r.get("max_amount"), 0),
            1 if r.get("expired") else 0,
            r.get("deadline", "9999-12-31"),
        )
    )
    federal_rows = rows[:12]

    state_rows: List[Dict[str, Any]] = []
    if state:
        state_rows.append(_state_portal_result(state))

    return state_rows + federal_rows  # state first, then top federal matches


def build_preview_text(intake: Dict[str, Any], grant: Dict[str, Any]) -> str:
    org = (intake.get("organization") or "The applicant organization").strip()
    audience = (intake.get("audience") or "its target population").strip()
    timeline = (intake.get("timeline") or "a defined implementation timeline").strip()
    notes = (intake.get("notes") or "").strip()
    keywords = _norm_words(intake.get("keywords", ""))
    g_title = (grant.get("title") or "selected funding opportunity").strip()
    g_deadline = (grant.get("deadline") or "TBA").strip()
    g_number = _grant_number(grant)

    overview = f"{org} seeks funding through {g_title}"
    if g_number:
        overview += f" (Grant # {g_number})"
    overview += f" to deliver measurable services for {audience}. The proposal aligns activities, staffing, and budget controls to produce credible outcomes before the stated deadline of {g_deadline}."

    need = notes or (
        f"Current service capacity is not sufficient to meet demand for {audience}, particularly in areas connected to "
        f"{', '.join(keywords[:3]) if keywords else 'priority program outcomes'}."
    )
    need_para = f"Need Statement: {need}"

    objectives = _mk_objectives_from_keywords(keywords, audience)[:4]
    if not objectives:
        objectives = [
            "Increase participation rates by at least 20% over the project period.",
            "Improve outcome attainment using pre/post performance measures tied to project activities.",
            "Document implementation fidelity through recurring progress reviews and corrective action cycles.",
        ]
    obj_lines = "\n".join(f"• {item}" for item in objectives)
    objectives_para = f"Objectives and Outcomes:\n{obj_lines}"

    eval_line = (
        f"Implementation will follow {timeline}, with performance monitoring conducted through attendance tracking, milestone reviews, "
        "and periodic outcome analysis to support timely adjustments."
    )
    return "\n\n".join([overview, need_para, objectives_para, eval_line])


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

    # Clean audience so it doesn't end with a stray period
    raw_audience = (intake.get("audience") or "").strip()
    audience = raw_audience.rstrip(".").strip() or "participants"

    # Clean timeline; avoid double periods when user types a full sentence
    raw_timeline = (intake.get("timeline") or "TBA").strip()
    timeline = raw_timeline.rstrip().rstrip(".")

    notes = (intake.get("notes") or "").strip()
    category = (intake.get("category") or intake.get("who") or "organization").strip()
    state = (intake.get("state") or "").strip()

    amount = _safe_float(intake.get("amountRequested"))
    annual_budget = _safe_float(intake.get("annualBudget"), 0)
    keywords_str = (intake.get("keywords") or "").strip()
    kws = _norm_words(keywords_str)

    g_title = grant.get("title") or "Selected opportunity"
    g_deadline = grant.get("deadline") or "TBA"
    g_number = _grant_number(grant)
    g_match = int(grant.get("requires_match_percent", 0) or 0)
    g_max = _safe_float(grant.get("max_amount"), 0)
    g_tags = grant.get("tags", []) or []
    g_geo = (grant.get("geo_scope") or "").strip()
    g_url = grant_display_url(grant) if grant else ""

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

    # Region / scope note
    region_bits = []
    if g_geo:
        region_bits.append(f"This opportunity is described as serving the {g_geo} region.")
    if state:
        region_bits.append(f"The applicant is based in {state}.")
    region_note = " ".join(region_bits)

    # Objectives & evaluation
    objectives = _mk_objectives_from_keywords(kws, audience)
    evaluation = _mk_evaluation_lines(audience)

    # 1) Executive Summary
    p1 = (
        f"{org} proposes “{proj_title}” to support {audience} through activities focused on {focus_str}. "
        f"The project will request {req_str} under the {g_title} opportunity, "
    )

    if timeline and timeline.lower() != "tba":
        # If user wrote a full sentence, keep it; otherwise treat as a phrase.
        if any(ch in raw_timeline for ch in ".!?"):
            p1 += f"{timeline} "
        else:
            p1 += f"with an implementation timeline of {timeline}. "
    else:
        p1 += "The implementation timeline will be finalized with the funder’s guidance. "

    p1 += f"The applicant currently operates as {category} {budget_str}"
    if region_note:
        p1 += " " + region_note

    # 2) Need Statement
    if notes:
        need_body = notes
    else:
        need_body = (
            f"The target population faces barriers related to limited access to high-quality resources, "
            f"programming, and supports. Without targeted investment, {audience} are less likely to "
            f"receive consistent, structured services that improve outcomes over time."
        )
    p2 = "There is a clear documented need for this project. " + need_body

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
    p3 = "Objectives and Measurable Outcomes:\n" + "\n".join(obj_lines)

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
    p4 = "Implementation Strategy:\n" + "\n".join(f"- {l}" for l in act_lines)

    # 5) Budget Summary
    budget_lines = [
        "Grant funds will be used for allowable costs such as materials, supplies, limited equipment, and staffing.",
        "The applicant will follow all federal, state, and local procurement and fiscal accountability requirements.",
    ]
    if g_match > 0:
        budget_lines.append(
            f"The applicant will plan to meet the required {g_match}% match through eligible in-kind or cash contributions, as confirmed with the funder’s guidance."
        )
    if g_max > 0 and amount > 0:
        budget_lines.append(
            f"The requested amount of {req_str} is being scoped with awareness of the program’s published range (up to approximately ${g_max:,.0f}, as applicable)."
        )
    p5 = "Budget Narrative and Stewardship Plan:\n" + "\n".join(f"- {l}" for l in budget_lines)

    # 6) Evaluation Plan
    eval_lines = []
    for i, line in enumerate(evaluation, 1):
        eval_lines.append(f"{i}. {line}")
    p6 = "Evaluation and Continuous Improvement Plan:\n" + "\n".join(eval_lines)

    # 7) Alignment with Funder Priorities
    align_text = (
        f"This project aligns with {g_title} by advancing activities related to {tag_phrase}. "
        f"All proposed activities and costs will adhere to program guidance, applicable regulations, "
        f"and ethical standards. The applicant understands that this draft is a starting point and will "
        f"review, refine, and customize language prior to any final submission."
    )
    deadline_note = f"The current anticipated deadline in this draft is {g_deadline}."
    grant_no_note = f" Grant #: {g_number}." if g_number else ""
    url_note = ""
    if g_url:
        url_note = f" The funder’s official information or search page for this opportunity can be accessed on Grants.gov at: {g_url}."

    compliance_note = (
        " Before submitting, the applicant will re-verify eligibility, deadlines, required forms, "
        "and match expectations using the official funding notice on Grants.gov or the funder’s website."
    )

    p7 = align_text + grant_no_note + " " + deadline_note + url_note + compliance_note

    return "\n\n".join([p1, p2, p3, p4, p5, p6, p7])


def make_pdf(order_id: str, payload: Dict[str, Any]) -> str:
    """
    Generate a polished, multi-page PDF from payload data.
    """
    os.makedirs(PDF_DIR, exist_ok=True)
    pdf_path = os.path.join(PDF_DIR, f"{order_id}.pdf")
    c = canvas.Canvas(pdf_path, pagesize=letter)

    left_margin = 52
    right_margin = 560
    top_y = 772
    body_top_y = 724
    body_bottom = 72
    wrap_width = 98

    created_at = _now_utc()
    page_num = 1
    legal_disclaimer = (
        "This draft packet is provided for informational and preparatory purposes only and does not constitute legal, "
        "financial, or professional advice. GrantForgeUSA does not guarantee funding or award outcomes. Applicants are "
        "responsible for verifying eligibility, requirements, deadlines, and submission materials using the official "
        "funding notice and complying with all applicable laws and regulations."
    )

    def draw_header() -> int:
        c.setFont("Helvetica-Bold", 14)
        c.drawString(left_margin, top_y, "GrantForgeUSA | Draft")
        c.setFont("Helvetica", 10)
        c.drawString(left_margin, top_y - 16, f"Order: {order_id}")
        c.drawString(left_margin, top_y - 30, f"Created: {created_at}")
        grant_number = payload.get("grant_number") or payload.get("opportunity_number")
        if grant_number:
            c.drawString(left_margin, top_y - 44, f"Grant #: {grant_number}")
            return body_top_y - 14
        return body_top_y

    def draw_footer():
        c.setFont("Helvetica-Oblique", 8)
        c.drawString(left_margin, 50, "Prepared with proprietary matching and drafting system.")
        c.drawRightString(right_margin, 50, f"Page {page_num}")
        c.setFont("Times-Roman", 7)
        y = 39
        text = legal_disclaimer
        while text:
            chunk = text[:140]
            text = text[140:]
            c.drawString(left_margin, y, chunk)
            y -= 7
            if y < 16:
                break
        c.drawString(left_margin, 16, "All sales are final. No refunds.")

    def new_page() -> int:
        nonlocal page_num
        draw_footer()
        c.showPage()
        page_num += 1
        return draw_header()

    y = draw_header()

    def draw_section_header(title: str) -> int:
        nonlocal y
        if y < body_bottom + 20:
            y = new_page()
        c.setFont("Helvetica-Bold", 11)
        y = _wrap_draw_line(c, title, left_margin, y, width_chars=wrap_width)
        y -= 2
        c.setFont("Helvetica", 10)
        return y

    def draw_block_line(line: str) -> int:
        nonlocal y
        if y < body_bottom:
            y = new_page()
            c.setFont("Helvetica", 10)
        y = _wrap_draw_line(c, line, left_margin, y, width_chars=wrap_width)
        return y

    draft_body = payload.get("draft_body")
    if isinstance(draft_body, str) and draft_body.strip():
        draw_section_header("Draft Narrative")
        for para in draft_body.split("\n\n"):
            for line in para.split("\n"):
                if line.strip().endswith(":"):
                    c.setFont("Helvetica-Bold", 10)
                    draw_block_line(line.strip())
                    c.setFont("Helvetica", 10)
                else:
                    draw_block_line(line)
            y -= 8

        draw_section_header("Order Details")
        preferred = [
            "grant_title", "grant_number", "grant_deadline", "grant_url",
            "org", "category", "amountRequested", "annualBudget", "price",
        ]
        seen = set()
        for k in preferred + sorted(payload.keys()):
            if k in seen or k == "draft_body" or k not in payload:
                continue
            seen.add(k)
            draw_block_line(f"{k}: {payload[k]}")
    else:
        draw_section_header("Order Details")
        for k in sorted(payload.keys()):
            if k == "draft_body":
                continue
            draw_block_line(f"{k}: {payload[k]}")

    draw_footer()
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

    preview_text = build_preview_text(data, grant)
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
    product_name = f"Grant Draft — {category} (All sales final)"

    order_id = datetime.utcnow().strftime("ORD-%Y%m%d-%H%M%S-%f")

    # Build narrative draft now so PDF is ready immediately after checkout
    draft_body = build_draft_text(data, grant)

    grant_url = grant_display_url(grant) if grant else ""

    metadata = {
        "order_id": order_id,
        "org": org,
        "category": category,
        "amountRequested": f"{amount_req:.2f}",
        "annualBudget": f"{annual_budget:.2f}",
        "grant_title": grant.get("title", ""),
        "grant_program": grant.get("program", ""),
        "grant_deadline": grant.get("deadline", ""),
        "grant_number": _grant_number(grant),
        "grant_url": grant_url,
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
        "grant_number": metadata.get("grant_number", ""),
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
            "grant_number": md.get("grant_number", ""),
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
        "grant_number": row.get("grant_number", ""),
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
