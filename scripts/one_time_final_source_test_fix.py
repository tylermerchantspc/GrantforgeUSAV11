from pathlib import Path

p = Path('backend/v11_server.py')
s = p.read_text()
old = '''    if APP_MODE == "production":
        if os.getenv("LIVE_GRANTS_ENABLED", "true").lower() == "false":
            return [], False
        live_query = " ".join(filter(None, [payload.get("projectTitle", ""), payload.get("keywords", "")])).strip()
        grants = search_live_grants(live_query, applicant_type=applicant_type, sector=requested_sector) if live_query else []
        if not grants:
            return [], False
    else:
        grants = _read_json(GRANTS_PATH) or []
'''
new = '''    live_grants_enabled = os.getenv("LIVE_GRANTS_ENABLED", "true").lower() != "false"
    if live_grants_enabled:
        live_query = " ".join(filter(None, [payload.get("projectTitle", ""), payload.get("keywords", "")])).strip()
        grants = search_live_grants(live_query, applicant_type=applicant_type, sector=requested_sector) if live_query else []
        if not grants:
            return [], False
    else:
        grants = _read_json(GRANTS_PATH) or []
'''
if old not in s:
    raise SystemExit('Expected shortlist source block not found')
p.write_text(s.replace(old, new))

p = Path('backend/tests/test_v11_server.py')
s = p.read_text()
if 'os.environ.setdefault("LIVE_GRANTS_ENABLED", "false")' not in s:
    s = s.replace('os.environ.setdefault("STRIPE_PUBLISHABLE_KEY", "pk_test_dummy")\n', 'os.environ.setdefault("STRIPE_PUBLISHABLE_KEY", "pk_test_dummy")\nos.environ.setdefault("LIVE_GRANTS_ENABLED", "false")\n')
helper_marker = '\ndef _run_paid_pdf_flow(client, monkeypatch, payload):\n'
helper = '''
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

'''
if '_purchase_ready_grant' not in s:
    s = s.replace(helper_marker, helper + helper_marker)
s = s.replace('def _run_paid_pdf_flow(client, monkeypatch, payload):\n    sessions = _mock_checkout(monkeypatch)\n', 'def _run_paid_pdf_flow(client, monkeypatch, payload):\n    sessions = _mock_checkout(monkeypatch)\n    _mock_purchase_ready_shortlist(monkeypatch, payload)\n')
s = s.replace('    payload = _payload("Unpaid Org", "housing, resilience", "501c3 Nonprofit")\n    recs = client.post', '    payload = _payload("Unpaid Org", "housing, resilience", "501c3 Nonprofit")\n    _mock_purchase_ready_shortlist(monkeypatch, payload)\n    recs = client.post')
s = s.replace('    payload = _payload("ReUse Block Org", "workforce, youth", "Church / Faith Org")\n    sessions = _mock_checkout(monkeypatch)\n', '    payload = _payload("ReUse Block Org", "workforce, youth", "Church / Faith Org")\n    sessions = _mock_checkout(monkeypatch)\n    _mock_purchase_ready_shortlist(monkeypatch, payload)\n')
s = s.replace('    payload = _payload("Ownership Org", "workforce, youth", "501c3 Nonprofit")\n    recs = client.post', '    payload = _payload("Ownership Org", "workforce, youth", "501c3 Nonprofit")\n    _mock_purchase_ready_shortlist(monkeypatch, payload)\n    recs = client.post')
extra = '''

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
'''
if 'test_live_source_failure_does_not_fall_back' not in s:
    s += extra
p.write_text(s)
