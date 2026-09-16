import copy
from backend import v11_server as srv

def payload(state='CA', category='City / County / Local Government', amount=250000):
    return {
        'organization':'Test Applicant','category':category,'state':state,
        'annualBudget':5000000,'projectTitle':'Drinking Water Main Replacement',
        'amountRequested':amount,'timeline':'18 months','audience':'Residents',
        'keywords':'drinking water, water infrastructure, lead service',
        'need':'Replace aging drinking water mains and lead service lines.',
        'notes':'Local government public water infrastructure project.'
    }

def state_grant(**patch):
    base = {
        'title':'Drinking Water Infrastructure Grant',
        'program':'California Water Agency','agency':'California Water Agency',
        'official_url':'https://data.ca.gov/example','program_url':'https://data.ca.gov/example',
        'opp_id':'CA-100','opportunity_id':'CA-100','opp_number':'CA-WATER-100',
        'deadline':'2026-12-15','close_date':'2026-12-15',
        'min_amount':0,'max_amount':500000,
        'eligibility_text':'Eligible applicants include local governments, counties, cities, and municipalities.',
        'eligible_types':['local government','counties','cities','municipalities'],
        'eligibility_codes':[],
        'summary':'Funds drinking water infrastructure, water mains, and lead service line replacement.',
        'sector_labels':['water infrastructure'],'sector':'water / infrastructure',
        'tags':['drinking water','water infrastructure','lead service'],
        'source':'California Grants Portal live state data','level':'State','state':'CA','funding_origin':'State',
        'cost_sharing_required':False,'requires_match_percent':0,
    }
    base.update(patch)
    return base

def federal_grant():
    return {
        'title':'Federal Drinking Water Infrastructure Grant','program':'Federal Water Program',
        'official_url':'https://www.grants.gov/opportunity/details/999999','program_url':'https://www.grants.gov/opportunity/details/999999',
        'opp_id':'999999','opportunity_id':'999999','opp_number':'FED-WATER',
        'deadline':'2026-12-20','close_date':'2026-12-20','min_amount':0,'max_amount':500000,
        'eligibility_text':'City or township governments and county governments are eligible.',
        'eligible_types':['local government'],'eligibility_codes':['02','04'],
        'summary':'Funds drinking water infrastructure, water mains, and lead service line replacement.',
        'sector_labels':['water infrastructure'],'sector':'water / infrastructure',
        'tags':['drinking water','water infrastructure','lead service'],
        'source':'Grants.gov live data','level':'Federal','cost_sharing_required':False,'requires_match_percent':0,
    }

def test_supported_state_merges_federal_and_state(monkeypatch):
    monkeypatch.setenv('LIVE_GRANTS_ENABLED','true')
    monkeypatch.setattr(srv, 'search_live_grants', lambda *a, **k: [federal_grant()])
    monkeypatch.setattr(srv, 'search_state_grants', lambda *a, **k: [state_grant()])
    rows, _ = srv.shortlist(payload())
    levels = {r['level'] for r in rows}
    assert levels == {'Federal','State'}

def test_unsupported_state_never_calls_state_source(monkeypatch):
    monkeypatch.setenv('LIVE_GRANTS_ENABLED','true')
    monkeypatch.setattr(srv, 'search_live_grants', lambda *a, **k: [federal_grant()])
    def explode(*a, **k):
        raise AssertionError('unsupported state source called')
    monkeypatch.setattr(srv, 'search_state_grants', explode)
    rows, _ = srv.shortlist(payload(state='MN'))
    assert rows and all(r['level']=='Federal' for r in rows)

def test_state_source_failure_can_fail_closed_without_affecting_federal(monkeypatch):
    monkeypatch.setenv('LIVE_GRANTS_ENABLED','true')
    monkeypatch.setattr(srv, 'search_live_grants', lambda *a, **k: [federal_grant()])
    monkeypatch.setattr(srv, 'search_state_grants', lambda *a, **k: [])
    rows, _ = srv.shortlist(payload())
    assert len(rows)==1 and rows[0]['level']=='Federal'

def test_state_missing_critical_verification_fields_is_not_purchase_ready(monkeypatch):
    monkeypatch.setenv('LIVE_GRANTS_ENABLED','true')
    monkeypatch.setattr(srv, 'search_live_grants', lambda *a, **k: [])
    for patch in ({'deadline':'','close_date':''},{'eligibility_text':''},{'max_amount':0},{'official_url':'https://evil.example/grant','program_url':'https://evil.example/grant'}):
        monkeypatch.setattr(srv, 'search_state_grants', lambda *a, _p=patch, **k: [state_grant(**_p)])
        rows, _ = srv.shortlist(payload())
        assert rows == []

def test_state_amount_and_relevance_hard_gates_still_apply(monkeypatch):
    monkeypatch.setenv('LIVE_GRANTS_ENABLED','true')
    monkeypatch.setattr(srv, 'search_live_grants', lambda *a, **k: [])
    monkeypatch.setattr(srv, 'search_state_grants', lambda *a, **k: [state_grant(max_amount=100000)])
    assert srv.shortlist(payload(amount=250000))[0] == []
    bad = state_grant(title='Arts Festival Grant',summary='Supports visual arts exhibitions and cultural programming.',sector_labels=['arts'],sector='arts / culture',tags=['arts'])
    monkeypatch.setattr(srv, 'search_state_grants', lambda *a, **k: [bad])
    assert srv.shortlist(payload())[0] == []

def test_state_display_url_does_not_accept_arbitrary_host():
    assert srv.grant_display_url(state_grant()) == 'https://data.ca.gov/example'
    bad = state_grant(official_url='https://evil.example/grant',program_url='https://evil.example/grant')
    assert srv.grant_display_url(bad) == ''

def test_selected_state_grant_is_refetched_and_browser_tampering_ignored(monkeypatch):
    requested = state_grant(title='FORGED TITLE',max_amount=99999999)
    monkeypatch.setattr(srv, 'fetch_state_grant', lambda state, ident, refresh=True: state_grant())
    live = srv._verified_requested_grant(requested,'CA')
    assert live['title']=='Drinking Water Infrastructure Grant'
    assert live['max_amount']==500000

def test_wrong_state_selected_grant_rejected(monkeypatch):
    requested = state_grant(state='CA')
    monkeypatch.setattr(srv, 'fetch_state_grant', lambda *a, **k: (_ for _ in ()).throw(AssertionError('should not fetch')))
    assert srv._verified_requested_grant(requested,'IA') == {}

def test_state_draft_uses_state_source_language_not_grantsgov():
    text = srv.build_narrative(payload(), state_grant())
    assert 'official state opportunity' in text
    assert 'selected government grant opportunity' in text
    assert 'current Grants.gov synopsis states' not in text

def test_federal_draft_retains_grantsgov_source_language():
    text = srv.build_narrative(payload(), federal_grant())
    assert 'Grants.gov synopsis' in text

def test_aging_infrastructure_language_does_not_trigger_geriatric_strict_group():
    assert "aging" not in srv._purpose_groups("Replace aging drinking water mains in a rural community")

def test_explicit_aging_research_still_triggers_aging_group():
    assert "aging" in srv._purpose_groups("biology of aging and geriatric research")


def test_generic_resident_through_words_do_not_create_program_purpose_match():
    payload = {
        "projectTitle":"Extreme Heat Community Resilience and Cooling Access",
        "keywords":"extreme heat, climate resilience, cooling, vulnerable communities",
        "need":"Reduce heat exposure for vulnerable residents through community cooling and resilience services.",
        "notes":"Nonprofit community resilience program.",
        "audience":"Residents and community members",
    }
    grant = {
        "title":"Statewide Park Development and Community Revitalization Program",
        "summary":"Provides funding to develop parks for residents through community-led projects.",
        "sector_labels":["parks"],
        "tags":["parks","resident","community"],
    }
    ok, note = srv._relevance_compatible(grant, payload, "NONPROFIT")
    assert ok is False
