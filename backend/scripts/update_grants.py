#!/usr/bin/env python3
"""Convert Grants.gov search export CSV to backend/data/grants.json."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_CSV = Path("/home/oai/share/grants-search-202603102237.csv")
DEFAULT_OUT = Path("backend/data/grants.json")


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _tokens(text: str) -> List[str]:
    words = re.findall(r"[a-zA-Z0-9][a-zA-Z0-9\-]{2,}", text.lower())
    stop = {
        "grant",
        "grants",
        "program",
        "federal",
        "funding",
        "opportunity",
        "opportunities",
        "application",
        "agency",
        "department",
        "notice",
    }
    unique: List[str] = []
    for w in words:
        if w in stop:
            continue
        if w not in unique:
            unique.append(w)
        if len(unique) == 10:
            break
    return unique


def _sector_guess(text: str) -> str:
    t = text.lower()
    if any(k in t for k in ("health", "clinic", "patient", "telehealth")):
        return "telehealth / healthcare"
    if any(k in t for k in ("school", "education", "classroom", "student", "stem")):
        return "education / STEM"
    if any(k in t for k in ("workforce", "apprenticeship", "credential", "employment")):
        return "workforce development"
    if any(k in t for k in ("housing", "community development", "homeless")):
        return "housing / community development"
    if any(k in t for k in ("emergency", "disaster", "public safety", "hazard")):
        return "public safety / emergency management"
    if any(k in t for k in ("environment", "conservation", "climate", "habitat", "coastal")):
        return "conservation / environment"
    if any(k in t for k in ("arts", "culture", "creative")):
        return "arts / culture"
    if any(k in t for k in ("innovation", "research", "prototype", "commercialization")):
        return "entrepreneurship / innovation"
    return ""


def parse_csv(csv_path: Path) -> List[Dict[str, Any]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        rows: List[Dict[str, Any]] = []
        for row in reader:
            url = _clean(row.get("url"))
            title = _clean(row.get("title"))
            synopsis = _clean(row.get("synopsis"))
            opp_num = _clean(row.get("opportunity_number"))
            agency_code = _clean(row.get("agency_code"))
            grant_id = _clean(row.get("id"))
            if not title:
                continue
            if not url.startswith("https://www.grants.gov"):
                continue

            blended = " ".join(p for p in (title, synopsis, agency_code) if p)
            rows.append(
                {
                    "id": grant_id,
                    "opportunity_number": opp_num,
                    "opp_number": opp_num,
                    "title": title,
                    "program": agency_code or "grants.gov",
                    "url": url,
                    "official_url": url,
                    "program_url": url,
                    "agency_code": agency_code,
                    "summary": synopsis,
                    "synopsis": synopsis,
                    "grantor_contact_name": _clean(row.get("grantor_contact_name")),
                    "grantor_contact_email": _clean(row.get("grantor_contact_email")),
                    "grantor_contact_telephone": _clean(row.get("grantor_contact_telephone")),
                    "tags": _tokens(blended),
                    "sector": _sector_guess(blended),
                    "eligible_types": [
                        "501c3 nonprofit",
                        "nonprofit",
                        "small business",
                        "city",
                        "municipality",
                        "school",
                        "district",
                        "local government",
                    ],
                    "min_amount": 0,
                    "max_amount": 10000000,
                    "deadline": "",
                    "close_date": "",
                    "requires_match_percent": 0,
                }
            )

    deduped: Dict[str, Dict[str, Any]] = {}
    for item in rows:
        key = item.get("id") or item.get("opportunity_number") or item.get("url")
        deduped[key] = item
    return list(deduped.values())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="Path to grants-search CSV export")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output JSON path")
    args = parser.parse_args()

    records = parse_csv(args.csv)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        json.dump(records, fh, indent=2)

    print(f"Wrote {len(records)} grants to {args.out}")


if __name__ == "__main__":
    main()
