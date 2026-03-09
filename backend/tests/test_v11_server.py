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
    srv._TOKEN_STORE.clear()
    srv._CHECKOUT_REF_STORE.clear()
    srv._DRAFT_STORE.clear()
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
        sess = DummySession(id=sid, url=f"https://stripe.test/{sid}", payment_status="paid", metadata=kwargs.get("metadata", {}))
        sessions[sid] = sess
        return sess

    def retrieve(session_id):
        return sessions[session_id]

    monkeypatch.setattr(srv.stripe.checkout.Session, "create", create)
    monkeypatch.setattr(srv.stripe.checkout.Session, "retrieve", retrieve)
    return sessions


def test_narrative_uses_senior_sections():
    grant = {"title": "Health Equity Grant", "deadline": "2027-01-01", "max_amount": 500000}
    text = srv.build_narrative(_payload("River Health Alliance", "telehealth, patient access", "501c3 Nonprofit"), grant)
    assert "Overview" in text
    assert "Objectives" in text
    assert "Implementation Plan" in text
    assert "Impact" in text


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
            {"title": r["title"], "program_url": r["program_url"]}
            for r in results
        ],
    }

    checkout = client.post("/create-checkout-session", json=full_payload)
    assert checkout.status_code == 200
    checkout_ref = checkout.get_json()["checkoutReference"]
    assert checkout_ref

    # must not download without paid token
    denied = client.get("/download-by-session?token=missing")
    assert denied.status_code == 400

    token_resp = client.post("/create-download-token", json={"checkout_ref": checkout_ref})
    assert token_resp.status_code == 200
    token = token_resp.get_json()["token"]

    sid = next(iter(sessions.keys()))
    webhook_payload = {
        "type": "checkout.session.completed",
        "data": {"object": {"id": sid, "metadata": sessions[sid]["metadata"], "payment_status": "paid", "amount_total": 250000, "currency": "usd", "mode": "payment"}},
    }
    monkeypatch.setattr(srv.stripe.Webhook, "construct_event", lambda payload, sig, sec: webhook_payload)
    monkeypatch.setattr(srv, "STRIPE_WEBHOOK_SECRET", "whsec_test")
    wh = client.post("/webhook/stripe", data=b"{}", headers={"Stripe-Signature": "sig"})
    assert wh.status_code == 200

    download = client.get(f"/download-by-session?token={token}")
    assert download.status_code == 200

    # token should be one-time
    second = client.get(f"/download-by-session?token={token}")
    assert second.status_code == 400

    assert all(r["program_url"].startswith("https://www.grants.gov/") for r in results)


def test_nonprofit_end_to_end_flow(client, monkeypatch):
    payload = _payload("North Star Nonprofit", "youth mentoring, workforce, STEM", "501c3 Nonprofit")
    _run_paid_pdf_flow(client, monkeypatch, payload)


def test_church_faith_end_to_end_flow(client, monkeypatch):
    payload = _payload("Living Hope Church", "food security, family counseling, recovery", "Church / Faith Org")
    _run_paid_pdf_flow(client, monkeypatch, payload)
