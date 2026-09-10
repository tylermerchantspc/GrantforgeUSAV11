"""Live Grants.gov opportunity search adapter for GrantForgeUSA.

Uses the public Grants.gov search2 and fetchOpportunity APIs. No API key is
required for these two endpoints. The adapter returns records shaped like the
legacy GrantForgeUSA grant dataset so the existing eligibility/scoring engine
can rank them without exposing vendor-specific response structures upstream.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, Iterable, List
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_BASE = "https://api.grants.gov/v1/api"
SEARCH_URL = f"{API_BASE}/search2"
DETAIL_URL = f"{API_BASE}/fetchOpportunity"
USER_AGENT = "GrantForgeUSA/11.5 (+https://grantforgeusa.com)"


def _post_json(url: str, payload: Dict[str, Any], timeout: float = 6.0) -> Dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
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
            if response.status < 200 or response.status >= 300:
                return {}
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        return {}


def _clean_text(value: Any) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_money(value: Any) -> float:
    raw = re.sub(r"[^0-9.]", "", str(value or ""))
    try:
        return float(raw) if raw else 0.0
    except ValueError:
        return 0.0


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
    if any(
        term in joined
        for term in (
            "school district",
            "independent school",
            "public institution of higher education",
            "private institution of higher education",
            "education agencies",
        )
    ):
        tags.extend(["school", "district", "education"])
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

    # Keep the raw descriptions as eligibility evidence for the existing matcher.
    tags.extend(_clean_text(item) for item in descriptions if _clean_text(item))
    return list(dict.fromkeys(tag for tag in tags if tag))


def _detail_to_grant(hit: Dict[str, Any], detail: Dict[str, Any]) -> Dict[str, Any]:
    data = detail.get("data") or {}
    synopsis = data.get("synopsis") or {}
    opportunity_id = data.get("id") or hit.get("id") or ""
    title = data.get("opportunityTitle") or hit.get("title") or "Federal funding opportunity"
    number = data.get("opportunityNumber") or hit.get("number") or ""

    applicant_types = [
        item.get("description", "")
        for item in (synopsis.get("applicantTypes") or [])
        if isinstance(item, dict)
    ]
    activity_categories = [
        item.get("description", "")
        for item in (synopsis.get("fundingActivityCategories") or [])
        if isinstance(item, dict)
    ]
    alns = [
        " ".join(filter(None, [item.get("alnNumber", ""), item.get("programTitle", "")])).strip()
        for item in (data.get("alns") or [])
        if isinstance(item, dict)
    ]

    summary = _clean_text(
        synopsis.get("synopsisDesc")
        or synopsis.get("fundingDesc")
        or data.get("forecast", {}).get("forecastDesc")
        or ""
    )
    close_date = _iso_date(
        hit.get("closeDate")
        or synopsis.get("responseDate")
        or data.get("originalDueDateDesc")
        or ""
    )
    max_amount = _parse_money(synopsis.get("awardCeiling") or synopsis.get("awardCeilingFormatted"))

    searchable = " ".join([title, summary, *activity_categories, *alns])
    tags = list(dict.fromkeys(re.findall(r"[A-Za-z0-9][A-Za-z0-9+-]{2,}", searchable.lower())))

    return {
        "title": title,
        "program": (alns[0] if alns else hit.get("agencyName") or hit.get("agencyCode") or "Federal"),
        "program_id": number,
        "program_url": f"https://www.grants.gov/search-results-detail/{opportunity_id}",
        "opp_id": str(opportunity_id),
        "opportunity_id": str(opportunity_id),
        "opp_number": number,
        "opportunity_number": number,
        "deadline": close_date,
        "close_date": close_date,
        "max_amount": max_amount,
        "eligible_types": _eligibility_tags(applicant_types),
        "eligibility": applicant_types,
        "tags": tags[:160],
        "sector": " / ".join(activity_categories[:3]),
        "summary": summary[:3000],
        "source": "Grants.gov live API",
        "source_updated": synopsis.get("lastUpdatedDate") or "",
    }


def _search_hits(keyword: str, rows: int = 25) -> List[Dict[str, Any]]:
    response = _post_json(
        SEARCH_URL,
        {
            "rows": rows,
            "keyword": keyword,
            "oppStatuses": "posted|forecasted",
            "sortBy": "openDate|desc",
        },
    )
    if response.get("errorcode") not in (0, "0", None):
        return []
    return list(((response.get("data") or {}).get("oppHits") or []))


def search_live_grants(keyword_text: str, max_details: int = 12) -> List[Dict[str, Any]]:
    """Return current Grants.gov opportunities relevant to the user's intake.

    Failure is intentionally represented as an empty list so the caller can use
    its local verified fallback without making the customer-facing search fail.
    """
    phrases = [part.strip() for part in re.split(r"[,;\n]", keyword_text or "") if part.strip()]
    primary = " ".join(phrases[:4]).strip()
    if not primary:
        return []

    hits = _search_hits(primary)
    if not hits and phrases:
        # Grants.gov full-text search can be narrower than expected for a compound
        # phrase. Fall back to the first strong intake term rather than returning
        # nothing solely because the combined query was over-constrained.
        hits = _search_hits(phrases[0])

    unique: Dict[str, Dict[str, Any]] = {}
    for hit in hits:
        if str(hit.get("oppStatus") or "").lower() not in ("posted", "forecasted", ""):
            continue
        opportunity_id = str(hit.get("id") or "").strip()
        if opportunity_id:
            unique.setdefault(opportunity_id, hit)
        if len(unique) >= max_details:
            break

    if not unique:
        return []

    grants: List[Dict[str, Any]] = []
    workers = min(6, len(unique))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_post_json, DETAIL_URL, {"opportunityId": int(opp_id)}): (opp_id, hit)
            for opp_id, hit in unique.items()
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
