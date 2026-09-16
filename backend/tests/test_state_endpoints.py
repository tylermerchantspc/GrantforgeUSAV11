from types import SimpleNamespace

from backend import v11_server as srv


def intake(state="CA"):
    return {
        "organization": "Test City",
        "contactName": "GrantForge QA",
        "contactEmail": "qa@example.com",
        "zip": "95814",
        "state": state,
        "category": "City / County / Local Government",
        "annualBudget": 5_000_000,
        "projectTitle": "Drinking Water Main Replacement",
        "amountRequested": 250_000,
        "timeline": "18 months",
        "audience": "Residents served by the municipal water system",
        "keywords": "drinking water, water infrastructure, lead service lines",
        "need": "Replace aging drinking water mains and lead service lines.",
        "notes": "Municipal public water infrastructure project.",
    }


def live_state_grant(**patch):
    row = {
        "title": "Drinking Water Infrastructure Grant",
        "program": "California Water Agency",
        "agency": "California Water Agency",
        "official_url": "https://data.ca.gov/example",
        "program_url": "https://data.ca.gov/example",
        "opp_id": "CA-100",
        "opportunity_id": "CA-100",
        "opp_number": "CA-WATER-100",
        "deadline": "2026-12-15",
        "close_date": "2026-12-15",
        "min_amount": 0,
        "max_amount": 500_000,
        "eligibility_text": "Eligible applicants include local governments, counties, cities, and municipalities.",
        "eligible_types": ["local government", "counties", "cities", "municipalities"],
        "eligibility_codes": [],
        "summary": "Funds drinking water infrastructure, water mains, and lead service line replacement.",
        "sector_labels": ["water infrastructure"],
        "sector": "water / infrastructure",
        "tags": ["drinking water", "water infrastructure", "lead service"],
        "source": "California Grants Portal live state data",
        "level": "State",
        "state": "CA",
        "funding_origin": "State",
        "cost_sharing_required": False,
        "requires_match_percent": 0,
    }
    row.update(patch)
    return row


def selected_stub(**patch):
    row = {
        "title": "FORGED BROWSER TITLE",
        "program": "Forged Program",
        "official_url": "https://evil.example/grant",
        "program_url": "https://evil.example/grant",
        "opp_id": "CA-100",
        "opportunity_id": "CA-100",
        "opp_number": "CA-WATER-100",
        "max_amount": 99_999_999,
        "source": "California Grants Portal live state data",
        "level": "State",
        "state": "CA",
    }
    row.update(patch)
    return row


def _clear_rate_limits():
    store = getattr(srv, "_RATE_LIMIT_STORE", None)
    if hasattr(store, "clear"):
        store.clear()


def test_preview_refetches_state_record_and_ignores_browser_tampering(monkeypatch):
    _clear_rate_limits()
    canonical = live_state_grant()
    seen = {}

    def fetch(state, ident, refresh=True):
        seen.update(state=state, ident=ident, refresh=refresh)
        return dict(canonical)

    monkeypatch.setattr(srv, "fetch_state_grant", fetch)
    payload = {**intake(), "grant": selected_stub()}
    response = srv.app.test_client().post("/preview", json=payload)
    assert response.status_code == 200, response.get_json()
    body = response.get_json()
    assert body["ok"] is True
    assert seen == {"state": "CA", "ident": "CA-100", "refresh": True}
    assert "Drinking Water Infrastructure Grant" in body["summary"]
    assert "FORGED BROWSER TITLE" not in body["summary"]


def test_preview_rejects_stale_or_unknown_state_identifier(monkeypatch):
    _clear_rate_limits()
    monkeypatch.setattr(srv, "fetch_state_grant", lambda *a, **k: {})
    response = srv.app.test_client().post("/preview", json={**intake(), "grant": selected_stub(opp_id="CA-NOT-FOUND", opportunity_id="CA-NOT-FOUND")})
    assert response.status_code == 422
    assert "re-verified" in response.get_json()["error"]


def test_preview_rejects_state_selection_for_wrong_applicant_state(monkeypatch):
    _clear_rate_limits()
    called = False

    def should_not_fetch(*args, **kwargs):
        nonlocal called
        called = True
        return live_state_grant()

    monkeypatch.setattr(srv, "fetch_state_grant", should_not_fetch)
    payload = {**intake(state="IA"), "grant": selected_stub(state="CA")}
    response = srv.app.test_client().post("/preview", json=payload)
    assert response.status_code == 422
    assert called is False


def test_preview_blocks_grant_that_closed_after_search(monkeypatch):
    _clear_rate_limits()
    monkeypatch.setattr(
        srv,
        "fetch_state_grant",
        lambda *a, **k: live_state_grant(deadline="2026-01-01", close_date="2026-01-01"),
    )
    response = srv.app.test_client().post("/preview", json={**intake(), "grant": selected_stub()})
    assert response.status_code == 422
    assert "purchase-ready" in response.get_json()["error"] or "no longer passes" in response.get_json()["error"].lower()


def test_checkout_refetches_state_record_and_uses_verified_metadata(monkeypatch):
    _clear_rate_limits()
    canonical = live_state_grant()
    monkeypatch.setattr(srv, "fetch_state_grant", lambda *a, **k: dict(canonical))
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id="cs_test_state_123", url="https://checkout.stripe.com/c/pay/cs_test_state_123")

    monkeypatch.setattr(srv.stripe.checkout.Session, "create", fake_create)
    monkeypatch.setattr(srv, "_append_payment_log_row", lambda row: None)
    monkeypatch.setattr(srv, "_store_draft", lambda *a, **k: None)

    response = srv.app.test_client().post(
        "/create-checkout-session",
        json={**intake(), "grant": selected_stub()},
    )
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["ok"] is True
    md = captured["metadata"]
    assert md["grant_title"] == "Drinking Water Infrastructure Grant"
    assert md["grant_title"] != "FORGED BROWSER TITLE"
    assert md["grant_level"] == "State"
    assert md["grant_state"] == "CA"
    assert md["grant_opp_id"] == "CA-100"
    assert str(captured["line_items"][0]["price_data"]["unit_amount"]) == "4999"
    assert str(srv.stripe.api_key).startswith("sk_test_")


def test_checkout_blocks_state_source_failure_before_stripe(monkeypatch):
    _clear_rate_limits()
    monkeypatch.setattr(srv, "fetch_state_grant", lambda *a, **k: {})
    called = False

    def fake_create(**kwargs):
        nonlocal called
        called = True
        raise AssertionError("Stripe must not be called")

    monkeypatch.setattr(srv.stripe.checkout.Session, "create", fake_create)
    response = srv.app.test_client().post(
        "/create-checkout-session",
        json={**intake(), "grant": selected_stub()},
    )
    assert response.status_code == 422
    assert called is False
