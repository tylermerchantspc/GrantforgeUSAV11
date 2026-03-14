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
    assert "Introduction" in text
    assert "Problem Statement" in text
    assert "Objectives" in text
    assert "Program Design" in text
    assert "Budget" in text
    assert "Conclusion" in text


def _run_paid_pdf_flow(client, monkeypatch, payload):
    sessions = _mock_checkout(monkeypatch)

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
                "amount_total": 250000,
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
