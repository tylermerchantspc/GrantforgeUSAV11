"""Official state-government grant opportunity adapters for GrantForgeUSA.

Initial support is intentionally narrow and conservative: California, Illinois,
and Iowa. Each adapter reads an official state-government source, normalizes the
result into the same broad record shape used by the federal matcher, and returns
only records that are currently actionable enough to screen further.

State-source failure is fail-closed: it returns no state opportunities and never
falls back to third-party aggregators.
"""

from __future__ import annotations

import html
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote, urljoin, urlparse
from urllib.request import Request, urlopen

USER_AGENT = "GrantForgeUSA-StateAdapter/1.0 (+https://grantforgeusa.com)"
CACHE_TTL_SECONDS = 15 * 60

SUPPORTED_STATE_CODES = {"CA", "IL", "IA"}

STATE_SOURCE_INFO = {
    "CA": {
        "name": "California Grants Portal / California Open Data",
        "public_url": "https://www.grants.ca.gov/",
        "allowed_hosts": {"grants.ca.gov", "data.ca.gov", "ca.gov"},
    },
    "IL": {
        "name": "Illinois GATA Catalog of State Financial Assistance",
        "public_url": "https://omb.illinois.gov/public/gata/csfa/OpportunityList.aspx",
        "allowed_hosts": {"omb.illinois.gov", "illinois.gov"},
    },
    "IA": {
        "name": "IowaGrants",
        "public_url": "https://www.iowagrants.gov/storefrontFOList.do",
        "allowed_hosts": {"iowagrants.gov", "iowa.gov"},
    },
}

_CA_API = (
    "https://data.ca.gov/api/3/action/datastore_search?"
    "resource_id=111c8c88-21f6-453c-ae2c-b4785a0624f5&limit=1000"
)
_IL_LIST = "https://omb.illinois.gov/public/gata/csfa/OpportunityList.aspx"
_IA_LIST = "https://www.iowagrants.gov/storefrontFOList.do"

_CACHE: Dict[str, Dict[str, Any]] = {}
_CACHE_LOCK = threading.Lock()


def _get(url: str, timeout: float = 12.0) -> str:
    req = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/json,*/*",
        },
    )
    with urlopen(req, timeout=timeout) as response:
        if not 200 <= response.status < 300:
            return ""
        return response.read().decode("utf-8", errors="replace")


def _clean(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_money(value: Any) -> float:
    raw = str(value or "")
    nums = re.findall(r"\$?\s*([0-9][0-9,]*(?:\.\d+)?)", raw)
    if not nums:
        return 0.0
    try:
        return float(nums[-1].replace(",", ""))
    except ValueError:
        return 0.0


def _money_range(value: Any) -> tuple[float, float]:
    raw = str(value or "")
    nums = re.findall(r"\$?\s*([0-9][0-9,]*(?:\.\d+)?)", raw)
    values: List[float] = []
    for item in nums:
        try:
            values.append(float(item.replace(",", "")))
        except ValueError:
            pass
    if not values:
        return 0.0, 0.0
    if len(values) == 1:
        if "no limit" in raw.lower():
            return 0.0, values[0]
        return 0.0, values[0]
    return min(values), max(values)


def _iso_date(value: Any) -> str:
    raw = _clean(value)
    if not raw:
        return ""
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%b %d, %Y %I:%M %p",
        "%b %d, %Y %I:%M:%S %p",
        "%B %d, %Y",
    ):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    m = re.search(r"([A-Z][a-z]{2,8}\s+\d{1,2},\s+20\d{2})", raw)
    if m:
        for fmt in ("%b %d, %Y", "%B %d, %Y"):
            try:
                return datetime.strptime(m.group(1), fmt).date().isoformat()
            except ValueError:
                pass
    m = re.search(r"(20\d{2}-\d{2}-\d{2})", raw)
    return m.group(1) if m else ""


def _tokens(text: str) -> set[str]:
    stop = {
        "grant", "grants", "program", "programs", "state", "funding", "project",
        "projects", "community", "communities", "support", "services", "service",
        "application", "applicant", "applicants", "opportunity", "opportunities",
    }
    return {
        t for t in re.findall(r"[a-z0-9][a-z0-9-]{2,}", str(text or "").lower())
        if t not in stop
    }


def _query_relevant(record: Dict[str, Any], query: str) -> bool:
    q = _tokens(query)
    if not q:
        return True
    blob = " ".join(
        str(record.get(k) or "")
        for k in ("title", "summary", "sector", "eligibility_text", "program")
    )
    r = _tokens(blob)
    return bool(q & r)


def _allowed_state_url(state: str, url: str) -> bool:
    try:
        parsed = urlparse(str(url or "").strip())
    except Exception:
        return False
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    allowed = STATE_SOURCE_INFO.get(state, {}).get("allowed_hosts", set())
    return any(host == base or host.endswith("." + base) for base in allowed)


def is_official_state_url(state: str, url: str) -> bool:
    return _allowed_state_url((state or "").upper(), url)


def _cached(state: str, loader) -> List[Dict[str, Any]]:
    now = time.time()
    with _CACHE_LOCK:
        rec = _CACHE.get(state)
        if rec and now - rec["ts"] < CACHE_TTL_SECONDS:
            return [dict(x) for x in rec["items"]]
    try:
        items = loader()
    except Exception:
        return []
    with _CACHE_LOCK:
        _CACHE[state] = {"ts": now, "items": [dict(x) for x in items]}
    return items


def _ca_records() -> List[Dict[str, Any]]:
    body = _get(_CA_API)
    payload = json.loads(body)
    records = ((payload.get("result") or {}).get("records") or []) if payload.get("success") else []
    out: List[Dict[str, Any]] = []
    for row in records:
        if str(row.get("Status") or "").strip().lower() != "active":
            continue
        if "grant" not in str(row.get("Type") or "").lower():
            continue
        # First wave means actual state-origin funding, not federal pass-through funds.
        if str(row.get("FundingSource") or "").strip().lower() != "state":
            continue
        url = str(row.get("GrantURL") or "").strip()
        # California agency URLs often live on subdomains of ca.gov; if a record points
        # elsewhere, retain the authoritative portal as the display URL instead.
        if not _allowed_state_url("CA", url):
            # Do not invent a record-specific URL. Fall back to the authoritative
            # statewide portal when an agency link is not on an allowlisted CA host.
            url = STATE_SOURCE_INFO["CA"]["public_url"]
        max_amount = _parse_money(row.get("EstAmounts") or row.get("Purpose"))
        matching = str(row.get("MatchingFunds") or "").strip().lower()
        summary = " ".join(
            filter(None, [_clean(row.get("Purpose")), _clean(row.get("Description"))])
        )
        eligibility = _clean(row.get("ApplicantTypeNotes") or row.get("ApplicantType"))
        out.append(
            {
                "title": _clean(row.get("Title")),
                "program": _clean(row.get("AgencyDept")) or "California state grant",
                "agency": _clean(row.get("AgencyDept")),
                "program_url": url,
                "official_url": url,
                "opp_id": f"CA-{row.get('PortalID')}",
                "opportunity_id": f"CA-{row.get('PortalID')}",
                "opp_number": _clean(row.get("GrantID")),
                "deadline": _iso_date(row.get("ApplicationDeadline")),
                "close_date": _iso_date(row.get("ApplicationDeadline")),
                "min_amount": 0.0,
                "max_amount": max_amount,
                "eligibility_text": eligibility,
                "eligible_types": [eligibility] if eligibility else [],
                "eligibility_codes": [],
                "summary": summary,
                "tags": list(_tokens(" ".join([_clean(row.get("Categories")), summary]))),
                "sector_labels": [_clean(row.get("Categories"))],
                "sector": "",
                "cost_sharing_required": False if "not required" in matching else (True if "required" in matching else None),
                "requires_match_percent": 0,
                "source": "California Grants Portal live state data",
                "level": "State",
                "state": "CA",
                "funding_origin": "State",
                "source_updated": _clean(row.get("LastUpdated")),
            }
        )
    return out


def _table_pairs(page: str) -> Dict[str, str]:
    pairs: Dict[str, str] = {}
    for left, right in re.findall(
        r"<t[dh][^>]*>(.*?)</t[dh]>\s*<t[dh][^>]*>(.*?)</t[dh]>",
        page,
        flags=re.I | re.S,
    ):
        key = _clean(left).rstrip(":")
        value = _clean(right)
        if key and value and key not in pairs:
            pairs[key] = value
    return pairs


def _il_detail(url: str) -> Optional[Dict[str, Any]]:
    page = _get(url)
    fields = _table_pairs(page)
    if fields.get("Type of Assistance Instrument", "").lower() != "grant":
        return None
    if fields.get("Source of Funding", "").lower() != "state":
        return None
    program_match = re.search(r"Program\.aspx\?csfa=(\d+)", page, flags=re.I)
    program_page = ""
    program_fields: Dict[str, str] = {}
    if program_match:
        purl = urljoin(url, f"Program.aspx?csfa={program_match.group(1)}")
        program_page = _get(purl)
        program_fields = _table_pairs(program_page)
    all_text = _clean(program_page)
    eligibility = program_fields.get("Applicant Eligibility", "")
    if not eligibility:
        m = re.search(r"Applicant Eligibility\s+(.*?)\s+(?:Beneficiary Eligibility|Types of Assistance)", all_text, flags=re.I | re.S)
        eligibility = _clean(m.group(1)) if m else ""
    summary = program_fields.get("Short Description", "") or program_fields.get("Objective", "")
    if not summary:
        m = re.search(r"Short Description\s+(.*?)\s+(?:Federal Authorization|Objective)", all_text, flags=re.I | re.S)
        summary = _clean(m.group(1)) if m else ""
    award_range = fields.get("Single Award Range", "") or program_fields.get("Range and Average of Financial Assistance", "")
    min_amount, max_amount = _money_range(award_range)
    date_range = fields.get("Application Date Range", "") or program_fields.get("Deadlines", "")
    deadline = ""
    dates = re.findall(r"\d{1,2}/\d{1,2}/20\d{2}|[A-Z][a-z]+\s+\d{1,2},\s+20\d{2}", date_range)
    if dates:
        deadline = _iso_date(dates[-1])
    title = fields.get("Agency Funding Program", "") or fields.get("CSFA Popular Name", "")
    return {
        "title": title,
        "program": fields.get("Awarding Agency Name", "") or "Illinois state grant",
        "agency": fields.get("Awarding Agency Name", ""),
        "program_url": url,
        "official_url": url,
        "opp_id": "IL-" + (fields.get("Agency Opportunity Number", "") or url.rsplit("=", 1)[-1]),
        "opportunity_id": "IL-" + (fields.get("Agency Opportunity Number", "") or url.rsplit("=", 1)[-1]),
        "opp_number": fields.get("Agency Opportunity Number", ""),
        "deadline": deadline,
        "close_date": deadline,
        "min_amount": min_amount,
        "max_amount": max_amount,
        "eligibility_text": eligibility,
        "eligible_types": [eligibility] if eligibility else [],
        "eligibility_codes": [],
        "summary": summary,
        "tags": list(_tokens(" ".join([title, summary, eligibility]))),
        "sector_labels": [],
        "sector": "",
        "cost_sharing_required": fields.get("Cost Sharing or Matching Requirements", "").strip().lower() == "yes",
        "requires_match_percent": 0,
        "source": "Illinois GATA live state data",
        "level": "State",
        "state": "IL",
        "funding_origin": "State",
    }


def _il_records() -> List[Dict[str, Any]]:
    page = _get(_IL_LIST)
    links = sorted(set(re.findall(r'href=["\']([^"\']*Opportunity\.aspx\?nofo=\d+[^"\']*)', page, flags=re.I)))
    urls = [urljoin(_IL_LIST, html.unescape(link)) for link in links]
    out: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_il_detail, url): url for url in urls}
        for future in as_completed(futures):
            try:
                item = future.result()
            except Exception:
                item = None
            if item and item.get("title") and item.get("eligibility_text"):
                out.append(item)
    return out


def _ia_detail(url: str) -> Optional[Dict[str, Any]]:
    page = _get(url)
    plain = _clean(page)
    if not plain:
        return None
    title_match = re.search(r"Funding Opportunity Details\s+Login.*?\s+(\d+)\s*-\s*(.*?)\s+Funding Opportunity Details", plain, flags=re.I | re.S)
    if not title_match:
        title_match = re.search(r"(\d+)\s*-\s*(.*?)\s+Funding Opportunity Details", plain, flags=re.I | re.S)
    if not title_match:
        return None
    number, title = title_match.group(1), _clean(title_match.group(2))
    # Conservative product scope: reject loan-only instruments even when generic
    # IowaGrants boilerplate elsewhere on the page happens to contain the word grant.
    title_lower = title.lower()
    if re.search(r"\bloans?\b", title_lower) and not re.search(r"\bgrants?\b", title_lower):
        return None
    if not re.search(r"\bgrants?\b", title_lower):
        explicit_grant = re.search(
            r"\b(?:grant program|grant funding|grant award|grant funds|grant application)\b",
            plain,
            flags=re.I,
        )
        if not explicit_grant:
            return None
    status = re.search(r"Status\s+([A-Za-z]+)", plain, flags=re.I)
    if status and status.group(1).lower() not in {"posted", "active", "open"}:
        return None
    deadline_m = re.search(r"Final Application Deadline:\s*([^\n]*?)(?=\s+Status|\s+Posted Date)", plain, flags=re.I)
    deadline = _iso_date(deadline_m.group(1) if deadline_m else "")
    amount_m = re.search(r"Award Amount Range\s+(.*?)(?=\s+Project Dates)", plain, flags=re.I | re.S)
    min_amount, max_amount = _money_range(amount_m.group(1) if amount_m else "")
    elig_m = re.search(r"(?:Eligible Applicants|Eligibility and available funds)\s+(.*?)(?=\s+Eligibility Requirements|\s+Eligible Expenses|\s+Ineligible Projects|\s+Uses of Funds|\s+Other Budget Requirements|\s+Attachments)", plain, flags=re.I | re.S)
    eligibility = _clean(elig_m.group(1)) if elig_m else ""
    desc_m = re.search(r"Purpose\s+(.*?)(?=\s+Eligible Applicants|\s+Eligibility and available funds|\s+Eligibility Requirements)", plain, flags=re.I | re.S)
    summary = _clean(desc_m.group(1)) if desc_m else ""
    cost_share = bool(re.search(r"cost share is required|matching funds? (?:is|are) required", plain, flags=re.I))
    return {
        "title": title,
        "program": "Iowa state-administered opportunity",
        "agency": "State of Iowa",
        "program_url": url,
        "official_url": url,
        "opp_id": f"IA-{number}",
        "opportunity_id": f"IA-{number}",
        "opp_number": number,
        "deadline": deadline,
        "close_date": deadline,
        "min_amount": min_amount,
        "max_amount": max_amount,
        "eligibility_text": eligibility,
        "eligible_types": [eligibility] if eligibility else [],
        "eligibility_codes": [],
        "summary": summary,
        "tags": list(_tokens(" ".join([title, summary, eligibility]))),
        "sector_labels": [],
        "sector": "",
        "cost_sharing_required": cost_share,
        "requires_match_percent": 0,
        "source": "IowaGrants live state data",
        "level": "State",
        "state": "IA",
        "funding_origin": "State-administered",
    }


def _ia_records() -> List[Dict[str, Any]]:
    page = _get(_IA_LIST)
    links = sorted(set(re.findall(r'href=["\']([^"\']*viewStorefrontOpportunity\.do\?[^"\']+)', page, flags=re.I)))
    urls = [urljoin(_IA_LIST, html.unescape(link)) for link in links]
    out: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_ia_detail, url): url for url in urls}
        for future in as_completed(futures):
            try:
                item = future.result()
            except Exception:
                item = None
            if item and item.get("title") and item.get("eligibility_text"):
                out.append(item)
    return out


def search_state_grants(
    state: str,
    query: str,
    applicant_type: str = "",
    sector: str = "",
) -> List[Dict[str, Any]]:
    """Return normalized official state opportunities for a supported state.

    Applicant-type and final eligibility decisions remain in GrantForgeUSA's
    screening layer; this adapter only performs source retrieval and a lightweight
    relevance prefilter.
    """
    code = (state or "").strip().upper()
    if code not in SUPPORTED_STATE_CODES:
        return []
    loader = {"CA": _ca_records, "IL": _il_records, "IA": _ia_records}[code]
    records = _cached(code, loader)
    candidates = [r for r in records if _query_relevant(r, " ".join(filter(None, [query, sector])))]
    return candidates[:40]


def fetch_state_grant(state: str, identifier: str, refresh: bool = True) -> Dict[str, Any]:
    """Re-fetch and return one official state opportunity by normalized identifier.

    Payment-adjacent callers should keep refresh=True so a selected opportunity is
    revalidated against the authoritative state source instead of trusting client data.
    """
    code = (state or "").strip().upper()
    wanted = str(identifier or "").strip()
    if code not in SUPPORTED_STATE_CODES or not wanted:
        return {}
    loader = {"CA": _ca_records, "IL": _il_records, "IA": _ia_records}[code]
    if refresh:
        try:
            records = loader()
        except Exception:
            return {}
        with _CACHE_LOCK:
            _CACHE[code] = {"ts": time.time(), "items": [dict(x) for x in records]}
    else:
        records = _cached(code, loader)
    for item in records:
        keys = {
            str(item.get("opp_id") or "").strip(),
            str(item.get("opportunity_id") or "").strip(),
            str(item.get("opp_number") or "").strip(),
        }
        if wanted in keys:
            return dict(item)
    return {}


def state_source_status() -> Dict[str, Dict[str, Any]]:
    return {
        code: {
            "supported": True,
            "source": info["name"],
            "public_url": info["public_url"],
        }
        for code, info in STATE_SOURCE_INFO.items()
    }
