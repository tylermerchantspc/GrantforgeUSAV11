"""Live Grants.gov opportunity search adapter for GrantForgeUSA.

Production matching uses the public Grants.gov search2 and fetchOpportunity APIs.
Neither endpoint requires authentication. This adapter keeps Grants.gov as the
source of truth and returns normalized records for the GrantForgeUSA screening
engine.
"""

from __future__ import annotations

import html
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_BASE = "https://api.grants.gov/v1/api"
SEARCH_URL = f"{API_BASE}/search2"
DETAIL_URL = f"{API_BASE}/fetchOpportunity"
USER_AGENT = "GrantForgeUSA/11.6 (+https://grantforgeusa.com)"

APPLICANT_ELIGIBILITY_CODES = {
    # Include code 25 (Others) for recall because many notices place legitimate
    # applicant types in Additional Information on Eligibility instead of a
    # dedicated applicant code. The server-side eligibility gate must then
    # positively confirm the applicant in that free-text field before sale.
    "EDU_K12": ["05", "25", "99"],
    "HIGHER_ED": ["06", "20", "25", "99"],
    "NONPROFIT_501C3": ["12", "25", "99"],
    "NONPROFIT": ["12", "13", "25", "99"],
    "SMALL_BUSINESS": ["23", "25", "99"],
    "FOR_PROFIT": ["22", "25", "99"],
    "GOV_LOCAL": ["01", "02", "04", "25", "99"],
    "GOV_STATE": ["00", "25", "99"],
    "TRIBAL": ["07", "11", "25", "99"],
    "HOUSING": ["08", "25", "99"],
    "INDIVIDUAL": ["21", "25", "99"],
    "OTHER": ["25", "99"],
}

SECTOR_FUNDING_CODES = {
    "education / STEM": ["ED", "ST"],
    "workforce development": ["ELT"],
    "telehealth / healthcare": ["HL"],
    "housing / community development": ["HO", "CD"],
    "public safety / emergency management": ["DPR", "LJL"],
    "conservation / environment": ["ENV", "NR"],
    "arts / culture": ["AR", "HU"],
    "entrepreneurship / innovation": ["BC", "ST"],
    "energy / manufacturing efficiency": ["EN", "BC"],
    "agriculture / rural development": ["AG", "RD"],
}


def _post_json(
    url: str,
    payload: Dict[str, Any],
    timeout: float = 8.0,
    attempts: int = 3,
) -> Dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    for attempt in range(attempts):
        request = Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                if 200 <= response.status < 300:
                    return json.loads(response.read().decode("utf-8"))
                if response.status not in (429, 500, 502, 503, 504):
                    return {}
        except HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504):
                return {}
        except (URLError, TimeoutError, ValueError, OSError):
            pass
        if attempt < attempts - 1:
            time.sleep(0.5 * (2**attempt))
    return {}


def _clean_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_money(value: Any) -> float:
    raw = re.sub(r"[^0-9.]", "", str(value or ""))
    try:
        return float(raw) if raw else 0.0
    except ValueError:
        return 0.0


def _parse_boolish(value: Any) -> Optional[bool]:
    """Parse Grants.gov yes/no style fields without treating non-empty strings as True."""
    if isinstance(value, bool):
        return value
    raw = str(value or "").strip().lower()
    if raw in {"yes", "y", "true", "1", "required"}:
        return True
    if raw in {"no", "n", "false", "0", "not required"}:
        return False
    return None


def _iso_date(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    for fmt in (
        "%m/%d/%Y",
        "%Y-%m-%d",
        "%b %d, %Y %I:%M:%S %p %Z",
        "%b %d, %Y %I:%M:%S %p",
    ):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    match = re.search(r"([A-Z][a-z]{2}\s+\d{1,2},\s+\d{4})", raw)
    if match:
        try:
            return datetime.strptime(match.group(1), "%b %d, %Y").date().isoformat()
        except ValueError:
            pass
    return raw[:10] if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", raw) else raw


def _eligibility_tags(descriptions: Iterable[str]) -> List[str]:
    joined = " | ".join(str(item or "").lower() for item in descriptions)
    tags: List[str] = []

    if any(term in joined for term in ("small business", "for-profit organization", "for profit organization")):
        tags.extend(["small business", "for-profit"])
    if any(term in joined for term in ("nonprofit", "non-profit", "501(c)(3)", "community-based")):
        tags.extend(["nonprofit", "501(c)(3)", "community-based organization"])
    if any(term in joined for term in ("school district", "independent school", "education agencies")):
        tags.extend(["school", "district", "education", "k12"])
    if any(term in joined for term in ("public institution of higher education", "private institution of higher education", "institution of higher education")):
        tags.extend(["higher education", "college", "university", "research institution", "education"])
    if any(
        term in joined
        for term in (
            "county government",
            "city or township government",
            "special district government",
            "local government",
            "state government",
            "tribal government",
        )
    ):
        tags.extend(["municipality", "city", "county", "local government", "tribal"])
    if "unrestricted" in joined:
        tags.append("unrestricted")

    tags.extend(_clean_text(item) for item in descriptions if _clean_text(item))
    return list(dict.fromkeys(tag for tag in tags if tag))


def _canonical_sector(activity_codes: Iterable[str]) -> str:
    code_set = {str(code or "").strip() for code in activity_codes}
    for sector, codes in SECTOR_FUNDING_CODES.items():
        if code_set.intersection(codes):
            return sector
    return ""


def _detail_to_grant(hit: Dict[str, Any], detail: Dict[str, Any]) -> Dict[str, Any]:
    data = detail.get("data") or {}
    synopsis = data.get("synopsis") or {}
    opportunity_id = data.get("id") or hit.get("id") or ""
    title = _clean_text(data.get("opportunityTitle") or hit.get("title") or "Federal funding opportunity")
    number = _clean_text(data.get("opportunityNumber") or hit.get("number") or "")

    applicant_items = [item for item in (synopsis.get("applicantTypes") or []) if isinstance(item, dict)]
    applicant_types = [_clean_text(item.get("description", "")) for item in applicant_items]
    applicant_codes = [str(item.get("id") or "").strip() for item in applicant_items if str(item.get("id") or "").strip()]
    activity_items = [item for item in (synopsis.get("fundingActivityCategories") or []) if isinstance(item, dict)]
    activity_categories = [_clean_text(item.get("description", "")) for item in activity_items]
    activity_codes = [str(item.get("id") or "").strip() for item in activity_items if str(item.get("id") or "").strip()]
    alns = [
        " ".join(filter(None, [_clean_text(item.get("alnNumber", "")), _clean_text(item.get("programTitle", ""))])).strip()
        for item in (data.get("alns") or [])
        if isinstance(item, dict)
    ]

    eligibility_text = _clean_text(
        synopsis.get("additionalInfoOnEligibility")
        or synopsis.get("additionalInformationOnEligibility")
        or synopsis.get("applicantEligibilityDesc")
        or synopsis.get("eligibilityDesc")
        or ""
    )
    summary = _clean_text(
        synopsis.get("synopsisDesc")
        or synopsis.get("fundingDesc")
        or data.get("forecast", {}).get("forecastDesc")
        or ""
    )
    close_date = _iso_date(
        hit.get("closeDate")
        or synopsis.get("responseDate")
        or synopsis.get("responseDateDesc")
        or data.get("originalDueDateDesc")
        or ""
    )
    max_amount = _parse_money(synopsis.get("awardCeiling") or synopsis.get("awardCeilingFormatted"))
    min_amount = _parse_money(synopsis.get("awardFloor") or synopsis.get("awardFloorFormatted"))

    searchable = " ".join([title, summary, eligibility_text, *activity_categories, *alns])
    tags = list(dict.fromkeys(re.findall(r"[A-Za-z0-9][A-Za-z0-9+-]{2,}", searchable.lower())))

    return {
        "title": title,
        "program": (alns[0] if alns else _clean_text(hit.get("agencyName") or hit.get("agencyCode") or "Federal")),
        "agency": _clean_text(synopsis.get("agencyName") or hit.get("agencyName") or ""),
        "program_id": number,
        "program_url": f"https://www.grants.gov/search-results-detail/{opportunity_id}",
        "official_url": f"https://www.grants.gov/search-results-detail/{opportunity_id}",
        "opp_id": str(opportunity_id),
        "opportunity_id": str(opportunity_id),
        "opp_number": number,
        "opportunity_number": number,
        "deadline": close_date,
        "close_date": close_date,
        "min_amount": min_amount,
        "max_amount": max_amount,
        "eligible_types": _eligibility_tags(applicant_types),
        "eligibility": applicant_types,
        "eligibility_codes": applicant_codes,
        "eligibility_text": eligibility_text,
        "funding_category_codes": activity_codes,
        "tags": tags[:200],
        "sector": _canonical_sector(activity_codes),
        "sector_labels": activity_categories[:3],
        "summary": summary[:5000],
        "cost_sharing_required": _parse_boolish(synopsis.get("costSharing")),
        "source": "Grants.gov live API",
        "source_updated": _clean_text(synopsis.get("lastUpdatedDate") or ""),
        "status": str(hit.get("oppStatus") or "posted").lower(),
    }


def _search_hits(
    keyword: str = "",
    rows: int = 25,
    eligibility_codes: Optional[List[str]] = None,
    funding_codes: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    payload: Dict[str, Any] = {
        "rows": rows,
        "oppStatuses": "posted",
        "sortBy": "openDate|desc",
    }
    if keyword.strip():
        payload["keyword"] = keyword.strip()
    if eligibility_codes:
        payload["eligibilities"] = "|".join(dict.fromkeys(eligibility_codes))
    if funding_codes:
        payload["fundingCategories"] = "|".join(dict.fromkeys(funding_codes))

    response = _post_json(SEARCH_URL, payload)
    if response.get("errorcode") not in (0, "0", None):
        return []
    return list(((response.get("data") or {}).get("oppHits") or []))


def _candidate_queries(keyword_text: str) -> List[str]:
    parts = [part.strip() for part in re.split(r"[,;\n]", keyword_text or "") if part.strip()]
    queries: List[str] = []
    for part in parts:
        if part not in queries:
            queries.append(part)
        words = [w for w in re.split(r"\s+", part) if len(w) >= 4]
        for word in words[:3]:
            if word.lower() not in {q.lower() for q in queries}:
                queries.append(word)
        if len(queries) >= 6:
            break
    return queries[:6]


def search_live_grants(
    keyword_text: str,
    applicant_type: str = "",
    sector: str = "",
    max_details: int = 24,
) -> List[Dict[str, Any]]:
    """Return currently posted Grants.gov opportunities relevant to an intake.

    Search uses applicant-type and funding-category filters when available,
    fans out across several customer terms for recall, and never fabricates a
    production result if Grants.gov returns no usable opportunity.
    """
    queries = _candidate_queries(keyword_text)
    eligibility_codes = APPLICANT_ELIGIBILITY_CODES.get(applicant_type, [])
    funding_codes = SECTOR_FUNDING_CODES.get(sector, [])

    unique: Dict[str, Dict[str, Any]] = {}

    # First pass: customer terms + both applicant and sector filters.
    for query in queries[:4]:
        for hit in _search_hits(query, rows=15, eligibility_codes=eligibility_codes, funding_codes=funding_codes):
            if str(hit.get("oppStatus") or "").lower() not in ("posted", ""):
                continue
            opp_id = str(hit.get("id") or "").strip()
            if opp_id:
                unique.setdefault(opp_id, hit)
            if len(unique) >= max_details:
                break
        if len(unique) >= max_details:
            break

    # Second pass: keep applicant eligibility, relax only the funding category.
    if len(unique) < min(8, max_details):
        for query in queries[:4]:
            for hit in _search_hits(query, rows=20, eligibility_codes=eligibility_codes):
                if str(hit.get("oppStatus") or "").lower() not in ("posted", ""):
                    continue
                opp_id = str(hit.get("id") or "").strip()
                if opp_id:
                    unique.setdefault(opp_id, hit)
                if len(unique) >= max_details:
                    break
            if len(unique) >= max_details:
                break

    # Final recall pass: filtered open opportunities even when Grants.gov full-text
    # search is too strict for the customer's phrasing.
    if len(unique) < min(5, max_details) and (eligibility_codes or funding_codes):
        for hit in _search_hits("", rows=25, eligibility_codes=eligibility_codes, funding_codes=funding_codes):
            if str(hit.get("oppStatus") or "").lower() not in ("posted", ""):
                continue
            opp_id = str(hit.get("id") or "").strip()
            if opp_id:
                unique.setdefault(opp_id, hit)
            if len(unique) >= max_details:
                break

    if not unique:
        return []

    grants: List[Dict[str, Any]] = []
    workers = min(4, len(unique))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_post_json, DETAIL_URL, {"opportunityId": int(opp_id)}): (opp_id, hit)
            for opp_id, hit in list(unique.items())[:max_details]
            if opp_id.isdigit()
        }
        for future in as_completed(futures):
            _, hit = futures[future]
            try:
                detail = future.result()
            except Exception:
                continue
            if detail and (detail.get("data") or {}).get("id"):
                grants.append(_detail_to_grant(hit, detail))

    return grants


def fetch_live_grant(opportunity_id: str) -> Dict[str, Any]:
    """Fetch and normalize one Grants.gov opportunity by its stable numeric id."""
    opp_id = str(opportunity_id or "").strip()
    if not opp_id.isdigit():
        return {}
    detail = _post_json(DETAIL_URL, {"opportunityId": int(opp_id)})
    if not detail or not (detail.get("data") or {}).get("id"):
        return {}
    return _detail_to_grant({"id": opp_id}, detail)
