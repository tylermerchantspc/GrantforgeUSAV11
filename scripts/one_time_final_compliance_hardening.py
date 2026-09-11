from pathlib import Path


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 occurrence, found {count}")
    return text.replace(old, new, 1)


# --- Grants.gov adapter: parse cost-sharing accurately and preserve the flag. ---
live_path = Path("backend/grantsgov_live.py")
live = live_path.read_text()
insert_after = '''def _parse_money(value: Any) -> float:
    raw = re.sub(r"[^0-9.]", "", str(value or ""))
    try:
        return float(raw) if raw else 0.0
    except ValueError:
        return 0.0
'''
addition = insert_after + '''\n\ndef _parse_boolish(value: Any) -> Optional[bool]:
    """Parse Grants.gov yes/no style fields without treating non-empty strings as True."""
    if isinstance(value, bool):
        return value
    raw = str(value or "").strip().lower()
    if raw in {"yes", "y", "true", "1", "required"}:
        return True
    if raw in {"no", "n", "false", "0", "not required"}:
        return False
    return None
'''
live = replace_once(live, insert_after, addition, "boolish helper")
old_cost = '        "cost_sharing_required": bool(synopsis.get("costSharing")) if synopsis.get("costSharing") is not None else None,'
new_cost = '        "cost_sharing_required": _parse_boolish(synopsis.get("costSharing")),'
live = replace_once(live, old_cost, new_cost, "cost sharing normalization")
live_path.write_text(live)


# --- Server: conservative additional-eligibility and geography restrictions. ---
server_path = Path("backend/v11_server.py")
server = server_path.read_text()

old_geo = '''def _geography_compatible(gr: Dict[str, Any], state_value: str) -> Tuple[bool, str]:
    state = _normalize_state(state_value)
    if not state:
        return False, "State is required to verify geographic eligibility."
    blob = " ".join([
        str(gr.get("title") or ""),
        str(gr.get("program") or ""),
        str(gr.get("agency") or ""),
        str(gr.get("eligibility_text") or ""),
    ]).lower()
    if "appalachian regional commission" in blob or re.search(r"\\barc\\b", blob):
        if state not in ARC_STATES:
            return False, "Applicant state is outside the Appalachian Regional Commission service area."
    return True, ""
'''
new_geo = '''def _geography_compatible(gr: Dict[str, Any], state_value: str) -> Tuple[bool, str]:
    state = _normalize_state(state_value)
    if not state:
        return False, "State is required to verify geographic eligibility."
    blob = " ".join([
        str(gr.get("title") or ""),
        str(gr.get("program") or ""),
        str(gr.get("agency") or ""),
        str(gr.get("eligibility_text") or ""),
        str(gr.get("summary") or ""),
    ]).lower()
    if "appalachian regional commission" in blob or re.search(r"\\barc\\b", blob):
        if state not in ARC_STATES:
            return False, "Applicant state is outside the Appalachian Regional Commission service area."

    # Catch common NOFO language that explicitly limits eligibility/service to a named state list.
    # This intentionally prefers a false negative over presenting a geographically impossible grant.
    restrictive_markers = (
        "in the states of", "within the states of", "limited to the states of",
        "eligible states include", "eligible states are", "only in the states of",
        "establish and operate", "available in the following states",
    )
    for marker in restrictive_markers:
        pos = blob.find(marker)
        if pos < 0:
            continue
        segment = blob[pos : pos + 900]
        named_codes = {
            code for code, name in US_STATE_NAMES.items()
            if re.search(rf"\\b{re.escape(name)}\\b", segment)
        }
        # Require at least two named jurisdictions before treating the passage as a list,
        # avoiding accidental rejection from a single example/location mention.
        if len(named_codes) >= 2 and state not in named_codes:
            return False, "The notice appears limited to named states that do not include the applicant state."
    return True, ""
'''
server = replace_once(server, old_geo, new_geo, "geography guardrail")

# Replace the current strict eligibility function with one that also respects restrictive free text.
start = server.index("def _is_eligible_for_applicant(")
end = server.index("\ndef shortlist(", start)
current = server[start:end]
new_elig = r'''def _eligibility_text_is_restrictive(text: str) -> bool:
    lowered = (text or "").lower()
    signals = (
        "eligible applicants are limited to",
        "eligible applicants include only",
        "applications may only be submitted by",
        "applications can only be submitted by",
        "applicants are limited to",
        "eligibility is limited to",
        "only eligible applicants",
        "may only apply",
        "must be one of",
        "must meet all of the following",
        "eligible to receive direct awards",
    )
    return any(signal in lowered for signal in signals)


def _is_eligible_for_applicant(gr: Dict[str, Any], applicant_type: str) -> bool:
    """Conservatively validate applicant eligibility against official codes and restrictions.

    Dedicated Grants.gov applicant codes establish the broad applicant class. When the NOFO's
    additional-eligibility text explicitly narrows that class, the applicant class must also be
    positively named in that restriction text. Code 25 (Others) always requires positive free-text
    confirmation. Student-applicant opportunities remain outside GrantForgeUSA scope.
    """
    if _student_applicant_opportunity(gr):
        return False

    code_map = {
        "EDU_K12": {"05", "99"},
        "HIGHER_ED": {"06", "20", "99"},
        "NONPROFIT_501C3": {"12", "99"},
        "NONPROFIT": {"12", "13", "99"},
        "SMALL_BUSINESS": {"23", "99"},
        "FOR_PROFIT": {"22", "99"},
        "GOV_LOCAL": {"01", "02", "04", "99"},
        "GOV_STATE": {"00", "99"},
        "TRIBAL": {"07", "11", "99"},
        "HOUSING": {"08", "99"},
        "INDIVIDUAL": {"21", "99"},
        "OTHER": {"99"},
    }
    codes = {
        str(code or "").strip().zfill(2)
        for code in (gr.get("eligibility_codes") or [])
        if str(code or "").strip()
    }
    free_text = str(gr.get("eligibility_text") or "").lower()
    needles = _eligibility_needles(applicant_type)

    # 'Others' is never treated as universal eligibility.
    if "25" in codes and not (codes & code_map.get(applicant_type, set())):
        if not free_text.strip():
            return False
        return any(term in free_text for term in needles)

    if codes & code_map.get(applicant_type, {"99"}):
        # A restrictive Additional Eligibility section can narrow a broad coded class.
        # If it does, require the submitted applicant class to be affirmatively represented.
        if free_text.strip() and _eligibility_text_is_restrictive(free_text):
            return any(term in free_text for term in needles)
        return True

    if codes:
        return False

    # Legacy/offline fixtures without numeric codes.
    title = (gr.get("title") or "").lower()
    tags = " ".join(normalized_tags(gr.get("tags", [])))
    elig = " ".join(str(e).lower() for e in gr.get("eligible_types", []))
    haystack = f"{title} {tags} {elig} {free_text}"
    if "unrestricted" in haystack and not _eligibility_text_is_restrictive(free_text):
        return True
    if "sbir" in haystack or "sttr" in haystack:
        return applicant_type == "SMALL_BUSINESS"
    if "cdbg" in haystack:
        return applicant_type == "GOV_LOCAL"
    return any(term in haystack for term in needles)

'''
server = server[:start] + new_elig + server[end:]

# Preserve cost-sharing signal in shortlist output.
old_match_line = '                    "requires_match_percent": gr.get("requires_match_percent", 0),\n'
new_match_line = '                    "requires_match_percent": gr.get("requires_match_percent", 0),\n                    "cost_sharing_required": gr.get("cost_sharing_required"),\n'
server = replace_once(server, old_match_line, new_match_line, "shortlist cost share flag")

# Narrative should warn accurately when Grants.gov says cost sharing is required but no percentage is known.
old_narrative_match = '''    g_match = int(_safe_float(grant.get("requires_match_percent"), 0))
'''
new_narrative_match = '''    g_match = int(_safe_float(grant.get("requires_match_percent"), 0))
    g_cost_share = grant.get("cost_sharing_required")
'''
server = replace_once(server, old_narrative_match, new_narrative_match, "narrative cost-share input")
old_match_text = '''    match_text = f" A {g_match}% match is listed and must be verified against the official notice." if g_match > 0 else ""
'''
new_match_text = '''    if g_match > 0:
        match_text = f" A {g_match}% match is listed and must be verified against the official notice."
    elif g_cost_share is True:
        match_text = " The Grants.gov synopsis indicates cost sharing or matching is required; the amount, basis, and any waiver must be verified in the official notice."
    elif g_cost_share is False:
        match_text = " The Grants.gov synopsis indicates cost sharing or matching is not required; verify the current official notice before submission."
    else:
        match_text = " Cost-sharing requirements were not conclusively captured from the synopsis and must be verified in the official notice."
'''
server = replace_once(server, old_match_text, new_match_text, "narrative cost-share warning")

# Sanitize/preserve the boolean when a selected grant comes back from the frontend.
old_sanitize = '''                "requires_match_percent": int(
                    _sanitize_numeric(v.get("requires_match_percent", 0), 0)
                ),
'''
new_sanitize = '''                "requires_match_percent": int(
                    _sanitize_numeric(v.get("requires_match_percent", 0), 0)
                ),
                "cost_sharing_required": v.get("cost_sharing_required") if isinstance(v.get("cost_sharing_required"), bool) else None,
                "opp_id": _sanitize_text(v.get("opp_id", ""), 120),
                "opportunity_id": _sanitize_text(v.get("opportunity_id", ""), 120),
                "source": _sanitize_text(v.get("source", ""), 120),
'''
server = replace_once(server, old_sanitize, new_sanitize, "selected grant stable fields")
server_path.write_text(server)


# --- Regression tests ---
test_path = Path("backend/tests/test_v11_server.py")
test = test_path.read_text()
extra = r'''


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
'''
if "test_restrictive_additional_eligibility_can_narrow_dedicated_code" not in test:
    test += extra
test_path.write_text(test)

print("final compliance hardening patched")
