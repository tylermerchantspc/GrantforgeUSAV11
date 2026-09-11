from pathlib import Path


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 occurrence, found {count}")
    return text.replace(old, new, 1)


# Expand live-search recall to include Grants.gov applicant code 25 (Others).
# Code 25 is NOT treated as universally eligible later; free-text eligibility must confirm fit.
live_path = Path("backend/grantsgov_live.py")
live = live_path.read_text()
old_codes = '''APPLICANT_ELIGIBILITY_CODES = {
    "EDU_K12": ["05", "99"],
    "HIGHER_ED": ["06", "20", "99"],
    "NONPROFIT_501C3": ["12", "99"],
    "NONPROFIT": ["12", "13", "99"],
    "SMALL_BUSINESS": ["23", "99"],
    "FOR_PROFIT": ["22", "99"],
    "GOV_LOCAL": ["01", "02", "04", "99"],
    "GOV_STATE": ["00", "99"],
    "TRIBAL": ["07", "11", "99"],
    "HOUSING": ["08", "99"],
    "INDIVIDUAL": ["21", "99"],
    "OTHER": ["25", "99"],
}'''
new_codes = '''APPLICANT_ELIGIBILITY_CODES = {
    # Include code 25 (Others) for recall because many notices place legitimate
    # applicant types in Additional Information on Eligibility instead of a
    # dedicated applicant code. The server-side eligibility gate must then
    # positively confirm the applicant in that free-text field before sale.
    "EDU_K12": ["05", "25", "99"],
    "HIGHER_ED": ["06", "20", "25", "99"],
    "NONPROFIT_501C3": ["12", "25", "99"],
    "NONPROFIT": ["12", "13", "25", "99"],
    "SMALL_BUSINESS": ["23", "25", "99"],
    "FOR_PROFIT": ["22", "25", "99"],
    "GOV_LOCAL": ["01", "02", "04", "25", "99"],
    "GOV_STATE": ["00", "25", "99"],
    "TRIBAL": ["07", "11", "25", "99"],
    "HOUSING": ["08", "25", "99"],
    "INDIVIDUAL": ["21", "25", "99"],
    "OTHER": ["25", "99"],
}'''
live = replace_once(live, old_codes, new_codes, "live applicant-code map")
live_path.write_text(live)


server_path = Path("backend/v11_server.py")
server = server_path.read_text()
start = server.index("def _is_eligible_for_applicant(")
end = server.index("\ndef shortlist(", start)
replacement = r'''def _student_applicant_opportunity(gr: Dict[str, Any]) -> bool:
    """Return True only when the funding notice appears to require a student as applicant.

    GrantForgeUSA intentionally does not offer student-aid or student-applicant services.
    Generic grants that merely serve students are not excluded.
    """
    text = " ".join(
        str(gr.get(key) or "")
        for key in ("title", "eligibility_text", "summary")
    ).lower()
    if not text.strip():
        return False

    # Direct financial-aid / student-aid surfaces are always out of scope.
    if any(term in text for term in ("fafsa", "federal pell grant", "student financial aid")):
        return True

    # Restrictive applicant language: the student is the applicant, not merely a beneficiary.
    patterns = (
        r"(?:seeking|invites?)\s+(?:applications?|proposals?)\s+from[^.]{0,180}\bstudents?\b",
        r"\bapplicants?\b[^.]{0,100}\bmust\b[^.]{0,80}\bstudents?\b",
        r"\bonly\b[^.]{0,80}\bstudents?\b[^.]{0,80}\b(?:apply|applicant)",
        r"\bstudents?\b[^.]{0,140}\b(?:eligible to apply|may apply|to apply for)\b",
    )
    return any(re.search(pattern, text, flags=re.I) for pattern in patterns)


def _eligibility_needles(applicant_type: str) -> Tuple[str, ...]:
    return {
        "EDU_K12": ("independent school district", "school district", "local education agency", "education agency", "k-12 school", "k12 school"),
        "HIGHER_ED": ("institution of higher education", "institutions of higher education", "college", "colleges", "university", "universities", "higher education"),
        "NONPROFIT_501C3": ("501(c)(3)", "501c3", "nonprofit", "non-profit"),
        "NONPROFIT": ("nonprofit", "non-profit", "community-based organization", "community organization", "faith-based organization"),
        "SMALL_BUSINESS": ("small business", "small businesses", "sbir", "sttr"),
        "FOR_PROFIT": ("for-profit", "for profit", "commercial organization", "businesses"),
        "GOV_LOCAL": ("local government", "county government", "city or township government", "municipality", "special district", "units of local government"),
        "GOV_STATE": ("state government", "state governments", "state agency", "state agencies"),
        "TRIBAL": ("tribal government", "tribal governments", "tribal organization", "tribal organizations", "indian tribe", "native american tribal"),
        "HOUSING": ("public housing authority", "public housing authorities", "indian housing authority", "housing authority"),
        "INDIVIDUAL": ("individual applicant", "individual applicants", "individuals"),
        "OTHER": ("other eligible applicant", "other eligible applicants"),
    }.get(applicant_type, ())


def _is_eligible_for_applicant(gr: Dict[str, Any], applicant_type: str) -> bool:
    """Conservatively validate applicant eligibility against codes and free-text restrictions.

    Explicit Grants.gov applicant codes are authoritative for the coded category. Code 25
    (Others) is a recall mechanism only: the free-text eligibility must positively name the
    applicant class. Student-applicant opportunities are always outside GrantForgeUSA scope.
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

    # A dedicated eligible-applicant code (or unrestricted 99) is enough to pass this layer.
    if codes & code_map.get(applicant_type, {"99"}):
        return True

    # 'Others' is intentionally NOT universal. Require positive evidence in the notice text.
    if "25" in codes:
        free_text = str(gr.get("eligibility_text") or "").lower()
        if not free_text.strip():
            return False
        return any(term in free_text for term in _eligibility_needles(applicant_type))

    # Legacy/offline fixtures may not carry numeric eligibility codes.
    if codes:
        return False

    title = (gr.get("title") or "").lower()
    tags = " ".join(normalized_tags(gr.get("tags", [])))
    elig = " ".join(str(e).lower() for e in gr.get("eligible_types", []))
    free_text = str(gr.get("eligibility_text") or "").lower()
    haystack = f"{title} {tags} {elig} {free_text}"
    if "unrestricted" in haystack:
        return True
    if "sbir" in haystack or "sttr" in haystack:
        return applicant_type == "SMALL_BUSINESS"
    if "cdbg" in haystack:
        return applicant_type == "GOV_LOCAL"
    return any(term in haystack for term in _eligibility_needles(applicant_type))

'''
server = server[:start] + replacement + server[end:]

# Exclude student-applicant opportunities before any ranking/purchase logic.
old_loop = '''        for gr in grants:
            # hide expired unless explicitly requested
            close_date = gr.get("close_date") or gr.get("deadline") or ""'''
new_loop = '''        for gr in grants:
            # GrantForgeUSA does not sell student-aid or student-applicant services.
            if _student_applicant_opportunity(gr):
                continue

            # hide expired unless explicitly requested
            close_date = gr.get("close_date") or gr.get("deadline") or ""'''
server = replace_once(server, old_loop, new_loop, "shortlist student-scope gate")
server_path.write_text(server)


# Add deterministic regression tests for the free-text and student-scope guardrails.
test_path = Path("backend/tests/test_v11_server.py")
test = test_path.read_text()
new_tests = r'''


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
'''
if "test_other_code_requires_free_text_confirmation_for_higher_ed" not in test:
    test += new_tests
test_path.write_text(test)

# Add adapter-level assertion so future refactors preserve code-25 recall.
live_test_path = Path("backend/tests/test_grantsgov_live.py")
if live_test_path.exists():
    live_test = live_test_path.read_text()
    addition = r'''


def test_higher_ed_search_includes_other_code_for_free_text_eligibility():
    assert "25" in live.APPLICANT_ELIGIBILITY_CODES["HIGHER_ED"]
    assert "06" in live.APPLICANT_ELIGIBILITY_CODES["HIGHER_ED"]
    assert "20" in live.APPLICANT_ELIGIBILITY_CODES["HIGHER_ED"]
'''
    if "test_higher_ed_search_includes_other_code_for_free_text_eligibility" not in live_test:
        live_test += addition
    live_test_path.write_text(live_test)

print("strict eligibility guardrails patched")
