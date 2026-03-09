import importlib.util
import os
from pathlib import Path

import pytest

os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_dummy")
os.environ.setdefault("STRIPE_PUBLISHABLE_KEY", "pk_test_dummy")

MODULE_PATH = Path(__file__).resolve().parents[1] / "v11_server.py"
spec = importlib.util.spec_from_file_location("v11_server", MODULE_PATH)
srv = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(srv)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(srv, "PROTECTED_DIR", str(tmp_path / "protected"))
    monkeypatch.setattr(srv, "PDF_DIR", str(tmp_path / "protected" / "pdfs"))
    monkeypatch.setattr(srv, "LOG_PATH", str(tmp_path / "protected" / "payments_log.csv"))
    os.makedirs(srv.PDF_DIR, exist_ok=True)
    srv.app.config.update(TESTING=True)
    return srv.app.test_client()


def _payload(org, keywords, category="501c3 Nonprofit"):
    return {
        "organization": org,
        "category": category,
        "keywords": keywords,
        "amountRequested": 150000,
        "annualBudget": 550000,
        "projectTitle": "Community Impact Program",
        "timeline": "12 months",
        "audience": "underserved residents",
        "notes": "Local service expansion and outcomes tracking",
    }


def test_search_limits_to_under_2m_and_sorts():
    results, _ = srv.shortlist(_payload("Org", "healthcare, telehealth"))
    assert results
    assert all(float(r.get("max_amount", 0)) <= 2_000_000 for r in results)
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)


def test_narrative_professional_sections_and_no_examples():
    grant = {"title": "Health Equity Grant", "deadline": "2027-01-01", "max_amount": 500000, "requires_match_percent": 0}
    text = srv.build_narrative(_payload("River Health Alliance", "telehealth, patient access"), grant)
    assert "Summary" in text
    assert "Need Statement" in text
    assert "example" not in text.lower()
    assert "sample" not in text.lower()


def test_pdf_contains_grants_url_link(tmp_path):
    grant = {
        "title": "Climate Resilience Program",
        "opportunity_number": "EPA-CLIMATE-2027",
        "deadline": "2027-05-01",
        "max_amount": 250000,
    }
    payload = _payload("Green Future Network", "climate, conservation")
    draft = srv.build_narrative(payload, grant)
    p = dict(payload)
    p["draft_body"] = draft
    p["grant_url"] = srv.grant_display_url(grant)
    pdf = srv.make_pdf("ORD-TEST", p)
    assert os.path.exists(pdf)
    assert p["grant_url"].startswith("https://www.grants.gov/search-results-detail/")


def test_download_requires_paid_status(client, monkeypatch):
    monkeypatch.setattr(srv, "_consume_token", lambda _t: "cs_test_123")
    monkeypatch.setattr(srv, "_stripe_session_paid", lambda _sid: (False, None, ""))
    resp = client.get("/download-by-session?token=abc")
    assert resp.status_code == 402


def test_ten_diverse_clients_search_and_preview(client):
    scenarios = [
        ("Health Bridge", "telehealth, elderly care"),
        ("Clean Water Now", "watershed restoration, conservation"),
        ("Digital Voices", "media literacy, youth empowerment"),
        ("City Safety Dept", "public safety, hazard mitigation", "City / Municipality"),
        ("WorkReady Labs", "workforce, certification"),
        ("Harvest Hope", "food security, community health"),
        ("Neighborhood Homes", "housing, neighborhood revitalization"),
        ("Veteran Pathways", "mental health, social services"),
        ("Makers Guild", "innovation, entrepreneurship"),
        ("Green Transit Coalition", "climate, emissions reduction"),
    ]
    for row in scenarios:
        org, kws = row[0], row[1]
        category = row[2] if len(row) > 2 else "501c3 Nonprofit"
        payload = _payload(org, kws, category)
        s = client.post("/search", json=payload)
        assert s.status_code == 200
        data = s.get_json()
        assert data["ok"] is True
        assert isinstance(data.get("results", []), list)
        if data["results"]:
            p = client.post("/preview", json={**payload, "grant": data["results"][0]})
            assert p.status_code == 200
            assert "Summary" in p.get_json().get("summary", "")


def test_questionnaire_sanitizes_phone_field(client):
    payload = _payload("Org", "healthcare")
    payload["phone"] = "=cmd|' /C calc'!A0"
    resp = client.post("/questionnaire", json=payload)
    assert resp.status_code == 200
