import json

from backend import state_grants_live as sg


def test_unsupported_state_fails_closed():
    assert sg.search_state_grants("MN", "water infrastructure") == []


def test_state_url_validation_is_allowlisted():
    assert sg.is_official_state_url("CA", "https://data.ca.gov/example") is True
    assert sg.is_official_state_url("IL", "https://omb.illinois.gov/public/gata") is True
    assert sg.is_official_state_url("IA", "https://www.iowagrants.gov/storefrontFOList.do") is True
    assert sg.is_official_state_url("CA", "https://example.com/grants") is False
    assert sg.is_official_state_url("CA", "http://data.ca.gov/example") is False


def test_california_parser_keeps_state_grants_and_rejects_federal_passthrough(monkeypatch):
    payload = {
        "success": True,
        "result": {
            "records": [
                {
                    "PortalID": "100",
                    "GrantID": "CA-TEST",
                    "Status": "active",
                    "Type": "Grant",
                    "FundingSource": "State",
                    "AgencyDept": "California Test Agency",
                    "Title": "Community Water Grant",
                    "Purpose": "Improve drinking water systems with grants up to $500,000.",
                    "Description": "Supports drinking water infrastructure.",
                    "ApplicantType": "Public Agency",
                    "ApplicantTypeNotes": "Eligible applicants include counties and cities.",
                    "Categories": "Environment & Water",
                    "MatchingFunds": "Not Required",
                    "ApplicationDeadline": "2026-12-01 23:59:00",
                    "GrantURL": "https://data.ca.gov/example",
                    "LastUpdated": "2026-09-15 10:00:00",
                    "EstAmounts": "Up to $500,000",
                },
                {
                    "PortalID": "101",
                    "GrantID": "FED-PASS",
                    "Status": "active",
                    "Type": "Grant",
                    "FundingSource": "Federal",
                    "AgencyDept": "California Test Agency",
                    "Title": "Federal Pass Through",
                },
            ]
        },
    }
    monkeypatch.setattr(sg, "_get", lambda url, timeout=12.0: json.dumps(payload))
    rows = sg._ca_records()
    assert len(rows) == 1
    row = rows[0]
    assert row["title"] == "Community Water Grant"
    assert row["max_amount"] == 500000
    assert row["deadline"] == "2026-12-01"
    assert row["funding_origin"] == "State"
    assert row["cost_sharing_required"] is False


def test_iowa_detail_parses_amount_deadline_and_eligibility(monkeypatch):
    page = '''
    <html><body>
    230028 - Iowa Energy Center Grant Program
    Funding Opportunity Details
    ENERGY
    Final Application Deadline: Oct 23, 2026 11:59 PM
    Status Posted Posted Date Aug 24, 2026 3:25 PM
    Award Amount Range No Limit - $1,000,000.00 Project Dates 12/09/2026 -
    Purpose The program supports energy workforce development and research.
    Eligible Applicants Iowa Businesses, colleges and universities, and private nonprofit agencies and foundations are eligible to apply.
    Eligibility Requirements Applicants shall demonstrate a benefit for ratepayers.
    Other Budget Requirements Cost share is required to apply for an Iowa Energy Center Grant.
    </body></html>
    '''
    monkeypatch.setattr(sg, "_get", lambda url, timeout=12.0: page)
    row = sg._ia_detail("https://www.iowagrants.gov/viewStorefrontOpportunity.do?OIDString=x")
    assert row is not None
    assert row["opp_number"] == "230028"
    assert row["deadline"] == "2026-10-23"
    assert row["max_amount"] == 1000000
    assert "Iowa Businesses" in row["eligibility_text"]
    assert row["cost_sharing_required"] is True


def test_illinois_detail_rejects_non_state_funding(monkeypatch):
    page = '''<table>
    <tr><td>Type of Assistance Instrument</td><td>Grant</td></tr>
    <tr><td>Source of Funding</td><td>Federal</td></tr>
    <tr><td>Agency Funding Program</td><td>Federal Pass Through</td></tr>
    </table>'''
    monkeypatch.setattr(sg, "_get", lambda url, timeout=12.0: page)
    assert sg._il_detail("https://omb.illinois.gov/public/gata/csfa/Opportunity.aspx?nofo=1") is None


def test_query_prefilter_requires_real_topic_overlap(monkeypatch):
    sg._CACHE.clear()
    monkeypatch.setattr(
        sg,
        "_ca_records",
        lambda: [
            {
                "title": "Drinking Water Infrastructure Grant",
                "summary": "Replace lead service lines and water mains.",
                "program": "Water Agency",
                "eligibility_text": "Cities and counties",
                "sector": "",
            }
        ],
    )
    assert sg.search_state_grants("CA", "drinking water lead service")
    sg._CACHE.clear()
    assert sg.search_state_grants("CA", "domestic violence legal advocacy") == []
