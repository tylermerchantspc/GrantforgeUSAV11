"""Launch smoke tests for narrative, URL quality, and checkout config guards."""

from pathlib import Path

from backend.v11_server import build_narrative, grant_display_url, shortlist


def make_payload(category: str, i: int):
    return {
        "organization": f"Org {i}",
        "category": category,
        "keywords": "workforce, training, technology, underserved",
        "amountRequested": 85000 + i * 1000,
        "annualBudget": 300000 + i * 5000,
        "projectTitle": f"Impact Initiative {i}",
        "timeline": "18 months",
        "audience": "low-income residents and job seekers",
        "notes": "Local partners report rising demand and service delays.",
    }


def assert_narrative_complete(narrative: str):
    required_sections = [
        "Executive Summary",
        "Statement of Need",
        "Program Description",
        "Target Population",
    ]
    for section in required_sections:
        assert section in narrative, f"missing section: {section}"

    assert len(narrative) >= 1400, f"narrative too short: {len(narrative)}"


def run_narrative_matrix():
    categories = [
        "Teacher (Classroom)",
        "School / District",
        "Church / Faith Org",
        "501c3 Nonprofit",
        "Small Business",
        "City / Municipality",
        "Other",
        "Nonprofit",
        "Teacher",
        "Municipality",
    ]
    for idx, category in enumerate(categories, start=1):
        payload = make_payload(category, idx)
        rows, _ = shortlist(payload)
        assert rows, f"no recommendations for {category}"
        narrative = build_narrative(payload, rows[0])
        assert_narrative_complete(narrative)


def run_grant_link_checks():
    rows, _ = shortlist(make_payload("501c3 Nonprofit", 99))
    assert rows, "no recommendation rows"

    for row in rows:
        url = grant_display_url(row)
        opp_number = row.get("opp_number") or row.get("opportunity_number")
        assert url.startswith("https://www.grants.gov/"), f"unexpected domain: {url}"
        if opp_number:
            assert ("opportunity/details/" in url) or ("search-results?query=" in url), f"not valid official grants URL: {url}"


def run_checkout_config_checks():
    source = Path("backend/v11_server.py").read_text(encoding="utf-8")
    assert "phone_number_collection" not in source, "phone number collection must be disabled"
    assert '@app.get("/get/debug-paths")' in source, "debug endpoint missing"
    assert 'return jsonify(ok=False, error="Not found"), 404' in source, "debug endpoint should be disabled"


def main():
    run_narrative_matrix()
    run_grant_link_checks()
    run_checkout_config_checks()
    print("Smoke tests passed: narrative matrix + grants.gov links + checkout config")


if __name__ == "__main__":
    main()
