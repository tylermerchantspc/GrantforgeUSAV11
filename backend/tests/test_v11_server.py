import importlib.util
import os
from pathlib import Path

import pytest

os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_dummy")
os.environ.setdefault("STRIPE_PUBLISHABLE_KEY", "pk_test_dummy")
os.environ.setdefault("LIVE_GRANTS_ENABLED", "false")

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
    monkeypatch.setattr(
        srv, "LOG_PATH", str(tmp_path / "protected" / "payments_log.csv")
    )
    os.makedirs(srv.PDF_DIR, exist_ok=True)
    srv._TOKEN_STORE.clear()
    srv._CHECKOUT_REF_STORE.clear()
    srv._DRAFT_STORE.clear()
    srv._COMPLETED_DOWNLOADS.clear()
    srv.app.config.update(TESTING=True)
    return srv.app.test_client()


def _payload(org, keywords, category):
    return {
        "organization": org,
        "category": category,
        "keywords": keywords,
        "amountRequested": 125000,
        "annualBudget": 450000,
        "projectTitle": "Community Capacity Expansion",
        "timeline": "18 months",
        "audience": "low-income families and youth",
        "state": "MN",
        "notes": "Cross-sector partnerships and evidence-based delivery",
    }


def _mock_checkout(monkeypatch):
    sessions = {}

    class DummySession(dict):
        __getattr__ = dict.get

    def create(**kwargs):
        sid = f"cs_test_{len(sessions)+1}"
        sess = DummySession(
            id=sid,
            url=f"https://stripe.test/{sid}",
            payment_status="paid",
            metadata=kwargs.get("metadata", {}),
        )
        sessions[sid] = sess
        return sess

    def retrieve(session_id):
        return sessions[session_id]

    monkeypatch.setattr(srv.stripe.checkout.Session, "create", create)
    monkeypatch.setattr(srv.stripe.checkout.Session, "retrieve", retrieve)
    return sessions


def test_narrative_uses_senior_sections():
    grant = {
        "title": "Health Equity Grant",
        "deadline": "2027-01-01",
        "max_amount": 500000,
    }
    text = srv.build_narrative(
        _payload(
            "River Health Alliance", "telehealth, patient access", "501c3 Nonprofit"
        ),
        grant,
    )
    assert "Executive Summary" in text
    assert "Statement of Need" in text
    assert "Program Description" in text
    assert "Budget Use" in text
    assert "Sustainability" in text


def _purchase_ready_grant(payload):
    return {
        "title": "Workforce Innovation Demonstration Grant",
        "program": "Federal Workforce Program",
        "program_url": "https://www.grants.gov/opportunity/details/TEST-2027-001",
        "official_url": "https://www.grants.gov/opportunity/details/TEST-2027-001",
        "opp_number": "TEST-2027-001",
        "deadline": "2027-12-31",
        "min_amount": 10000,
        "max_amount": 500000,
        "fit": "Strong Match",
        "score": 150,
        "fit_notes": "Eligibility, project purpose, geography, and funding range align.",
        "purchasable": True,
        "requires_match_percent": 0,
        "tags": ["workforce", "youth", "community"],
        "sector": "workforce development",
        "summary": "Test fixture for secure checkout and PDF lifecycle regression coverage.",
        "source": "Test fixture",
        "level": "Federal",
    }


def _mock_purchase_ready_shortlist(monkeypatch, payload):
    grant = _purchase_ready_grant(payload)
    monkeypatch.setattr(srv, "shortlist", lambda data: ([dict(grant)], True))
    return grant


def _run_paid_pdf_flow(client, monkeypatch, payload):
    sessions = _mock_checkout(monkeypatch)
    _mock_purchase_ready_shortlist(monkeypatch, payload)

    invalid = dict(payload)
    invalid["audience"] = ""
    bad = client.post("/questionnaire", json=invalid)
    assert bad.status_code == 400

    search = client.post("/questionnaire", json=payload)
    assert search.status_code == 200
    results = search.get_json()["results"]
    assert results

    grant = results[0]
    full_payload = {
        **payload,
        "grant": grant,
        "recommendations": [
            {"title": r["title"], "program_url": r["program_url"]} for r in results
        ],
    }

    checkout = client.post("/create-checkout-session", json=full_payload)
    assert checkout.status_code == 200
    checkout_ref = checkout.get_json()["checkoutReference"]
    assert checkout_ref

    # must not download without paid token
    denied = client.get("/download-by-session?token=missing")
    assert denied.status_code == 400

    token_resp = client.post(
        "/create-download-token", json={"checkout_ref": checkout_ref}
    )
    assert token_resp.status_code == 200
    token = token_resp.get_json()["token"]

    sid = next(iter(sessions.keys()))
    webhook_payload = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": sid,
                "metadata": sessions[sid]["metadata"],
                "payment_status": "paid",
                "amount_total": srv.cents(srv.price_for(payload["category"], payload["annualBudget"])),
                "currency": "usd",
                "mode": "payment",
            }
        },
    }
    monkeypatch.setattr(
        srv.stripe.Webhook, "construct_event", lambda payload, sig, sec: webhook_payload
    )
    monkeypatch.setattr(srv, "STRIPE_WEBHOOK_SECRET", "whsec_test")
    wh = client.post("/webhook/stripe", data=b"{}", headers={"Stripe-Signature": "sig"})
    assert wh.status_code == 200

    download = client.get(f"/download-by-session?token={token}")
    assert download.status_code == 200

    # token should be one-time
    second = client.get(f"/download-by-session?token={token}")
    assert second.status_code == 400

    assert all(
        (r["program_url"] or "").startswith("https://www.grants.gov") for r in results
    )


def test_nonprofit_end_to_end_flow(client, monkeypatch):
    payload = _payload(
        "North Star Nonprofit", "youth mentoring, workforce, STEM", "501c3 Nonprofit"
    )
    _run_paid_pdf_flow(client, monkeypatch, payload)


def test_church_faith_end_to_end_flow(client, monkeypatch):
    payload = _payload(
        "Living Hope Church",
        "food security, family counseling, recovery",
        "Church / Faith Org",
    )
    _run_paid_pdf_flow(client, monkeypatch, payload)


def test_receipt_requires_paid_session(client, monkeypatch):
    sessions = _mock_checkout(monkeypatch)

    def create_unpaid(**kwargs):
        sid = f"cs_test_unpaid_{len(sessions)+1}"

        class DummySession(dict):
            __getattr__ = dict.get

        sess = DummySession(
            id=sid,
            url=f"https://stripe.test/{sid}",
            payment_status="unpaid",
            metadata=kwargs.get("metadata", {}),
        )
        sessions[sid] = sess
        return sess

    monkeypatch.setattr(srv.stripe.checkout.Session, "create", create_unpaid)

    payload = _payload("Unpaid Org", "housing, resilience", "501c3 Nonprofit")
    _mock_purchase_ready_shortlist(monkeypatch, payload)
    recs = client.post("/questionnaire", json=payload).get_json()["results"]
    checkout = client.post(
        "/create-checkout-session",
        json={**payload, "grant": recs[0], "recommendations": recs},
    )
    checkout_ref = checkout.get_json()["checkoutReference"]

    token_resp = client.post(
        "/create-download-token", json={"checkout_ref": checkout_ref}
    )
    assert token_resp.status_code == 402


def test_session_cannot_be_reused_after_download(client, monkeypatch):
    payload = _payload("ReUse Block Org", "workforce, youth", "Church / Faith Org")
    sessions = _mock_checkout(monkeypatch)
    _mock_purchase_ready_shortlist(monkeypatch, payload)
    recs = client.post("/questionnaire", json=payload).get_json()["results"]
    checkout = client.post(
        "/create-checkout-session",
        json={**payload, "grant": recs[0], "recommendations": recs},
    )
    token_resp = client.post(
        "/create-download-token",
        json={"checkout_ref": checkout.get_json()["checkoutReference"]},
    )
    token = token_resp.get_json()["token"]

    first_download = client.get(f"/download-by-session?token={token}")
    assert first_download.status_code == 200

    sid = next(iter(sessions.keys()))
    new_token = srv._mint_download_token(sid)
    receipt = client.get(f"/receipt?token={new_token}")
    assert receipt.status_code == 409

    second_download = client.get(f"/download-by-session?token={new_token}")
    assert second_download.status_code == 409


def test_grant_url_validation_allows_only_official_grants_domain():
    assert (
        srv.grant_display_url(
            {"program_url": "https://www.grants.gov/opportunity/details/ABC-123"}
        )
        == "https://www.grants.gov/opportunity/details/ABC-123"
    )
    assert (
        srv.grant_display_url({"program_url": "https://invalid.local/not-allowed"}) == ""
    )


def test_download_token_rejects_non_owner_ip(client, monkeypatch):
    _mock_checkout(monkeypatch)
    payload = _payload("Ownership Org", "workforce, youth", "501c3 Nonprofit")
    _mock_purchase_ready_shortlist(monkeypatch, payload)
    recs = client.post("/questionnaire", json=payload).get_json()["results"]
    checkout = client.post(
        "/create-checkout-session",
        json={**payload, "grant": recs[0], "recommendations": recs},
    )
    checkout_ref = checkout.get_json()["checkoutReference"]

    bad = client.post(
        "/create-download-token",
        json={"checkout_ref": checkout_ref},
        environ_overrides={"REMOTE_ADDR": "10.10.10.10"},
    )
    assert bad.status_code == 403


def test_geography_blocks_appalachian_grant_for_minnesota():
    grant = {"title": "Appalachian Regional Commission INSPIRE Initiative", "program": "ARC"}
    ok, note = srv._geography_compatible(grant, "MN")
    assert ok is False
    assert "outside" in note.lower()

def test_geography_allows_appalachian_state():
    grant = {"title": "Appalachian Regional Commission INSPIRE Initiative", "program": "ARC"}
    ok, _ = srv._geography_compatible(grant, "VA")
    assert ok is True

def test_funding_range_is_hard_gate():
    grant = {"min_amount": 150000, "max_amount": 350000}
    assert srv._funding_range_compatible(grant, 90000)[0] is False
    assert srv._funding_range_compatible(grant, 200000)[0] is True
    assert srv._funding_range_compatible(grant, 500000)[0] is False


def test_state_is_required(client):
    payload = _payload("State Required Org", "workforce, youth", "501c3 Nonprofit")
    payload.pop("state")
    response = client.post("/questionnaire", json=payload)
    assert response.status_code == 400
    assert "state" in response.get_json()["error"].lower()


def test_low_match_cannot_be_purchased(client, monkeypatch):
    payload = _payload("Low Match Org", "workforce, youth", "501c3 Nonprofit")
    low = _purchase_ready_grant(payload)
    low.update({"fit": "Low Match", "score": 70, "purchasable": False})
    monkeypatch.setattr(srv, "shortlist", lambda data: ([], False))
    response = client.post("/create-checkout-session", json={**payload, "grant": low})
    assert response.status_code == 422


def test_live_source_failure_does_not_fall_back(monkeypatch):
    payload = _payload("Live Source Org", "workforce, youth", "501c3 Nonprofit")
    monkeypatch.setenv("LIVE_GRANTS_ENABLED", "true")
    monkeypatch.setattr(srv, "search_live_grants", lambda *args, **kwargs: [])
    results, has_strong = srv.shortlist(payload)
    assert results == []
    assert has_strong is False



def test_flat_pricing_for_all_applicant_types():
    categories = ["K-12 School / District / Educator", "College / University / Research Institution", "Church / Faith Organization", "501(c)(3) Nonprofit", "Small Business", "For-Profit Organization", "City / County / Local Government", "State Government / Agency", "Tribal Government / Organization", "Public Housing Authority", "Individual / Independent Applicant", "Other Eligible Applicant"]
    for category in categories:
        for budget in (1, 100000, 5000000, 500000000):
            assert srv.price_for(category, budget) == pytest.approx(49.99)


def test_higher_ed_uses_official_eligibility_codes():
    assert srv._is_eligible_for_applicant({"eligibility_codes": ["06"]}, "HIGHER_ED") is True
    assert srv._is_eligible_for_applicant({"eligibility_codes": ["20"]}, "HIGHER_ED") is True
    assert srv._is_eligible_for_applicant({"eligibility_codes": ["23"]}, "HIGHER_ED") is False


def test_narrative_does_not_invent_default_outcomes_or_capacity():
    grant = {"title": "Research Opportunity", "program": "Federal Program", "deadline": "2027-01-01", "max_amount": 500000, "summary": "Supports rigorous research and documented project outcomes."}
    payload = _payload("Example University", "research, education, rural", "College / University / Research Institution")
    text = srv.build_narrative(payload, grant)
    assert "20%" not in text and "70%" not in text and "90%" not in text
    assert "does not assume" in text
    assert "Applicant Validation Required Before Submission" in text



def test_other_code_requires_free_text_confirmation_for_higher_ed():
    allowed = {
        "eligibility_codes": ["25"],
        "eligibility_text": "Eligible applicants include public and private agencies and institutions, such as colleges and universities.",
    }
    unrelated = {
        "eligibility_codes": ["25"],
        "eligibility_text": "Eligible applicants are limited to state correctional agencies and federally recognized tribal governments.",
    }
    blank = {"eligibility_codes": ["25"], "eligibility_text": ""}
    assert srv._is_eligible_for_applicant(allowed, "HIGHER_ED") is True
    assert srv._is_eligible_for_applicant(unrelated, "HIGHER_ED") is False
    assert srv._is_eligible_for_applicant(blank, "HIGHER_ED") is False


def test_student_applicant_opportunities_are_out_of_scope_even_with_broad_codes():
    student_only = {
        "eligibility_codes": ["12", "20", "21", "99"],
        "title": "Research Fellowship",
        "summary": "The program is seeking proposals from current master and doctoral students enrolled at colleges or universities within the US to apply for an award.",
    }
    assert srv._student_applicant_opportunity(student_only) is True
    assert srv._is_eligible_for_applicant(student_only, "HIGHER_ED") is False
    assert srv._is_eligible_for_applicant(student_only, "INDIVIDUAL") is False


def test_grants_serving_students_are_not_mistaken_for_student_applicant_programs():
    institutional = {
        "eligibility_codes": ["05"],
        "title": "STEM Education Program",
        "summary": "Independent school districts may apply for projects serving rural high-school students.",
    }
    assert srv._student_applicant_opportunity(institutional) is False
    assert srv._is_eligible_for_applicant(institutional, "EDU_K12") is True



def test_restrictive_additional_eligibility_can_narrow_dedicated_code():
    restricted_nonprofit = {
        "eligibility_codes": ["12", "25"],
        "eligibility_text": "The following types of organizations are eligible to receive direct awards: CSBG state associations, tribes and territories funded directly in FY 2025.",
    }
    assert srv._is_eligible_for_applicant(restricted_nonprofit, "NONPROFIT_501C3") is False


def test_restrictive_additional_eligibility_keeps_named_applicant_class():
    restricted_local = {
        "eligibility_codes": ["01", "02", "04", "25"],
        "eligibility_text": "Eligible applicants are limited to States; units of local government; and tribal governments.",
    }
    assert srv._is_eligible_for_applicant(restricted_local, "GOV_LOCAL") is True


def test_named_state_list_rejects_out_of_area_applicant():
    grant = {
        "title": "Manufacturing Extension Program",
        "summary": "Establish and operate a center in the States of Alabama, Alaska, Arkansas, California, Georgia, Louisiana, Massachusetts, Missouri, Montana, Ohio, Pennsylvania, Utah and Vermont.",
    }
    assert srv._geography_compatible(grant, "MN")[0] is False
    assert srv._geography_compatible(grant, "AL")[0] is True


def test_narrative_flags_required_cost_sharing_without_inventing_percentage():
    grant = {
        "title": "Rural STEM Opportunity",
        "program": "NIFA",
        "deadline": "2026-09-30",
        "max_amount": 200000,
        "cost_sharing_required": True,
    }
    payload = _payload("Example University", "stem, agriculture, rural", "College / University / Research Institution")
    text = srv.build_narrative(payload, grant)
    assert "cost sharing or matching is required" in text
    assert "must be verified" in text
