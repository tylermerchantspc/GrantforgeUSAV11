from pathlib import Path


def rep(text, old, new, label):
    n = text.count(old)
    if n != 1:
        raise SystemExit(f"{label}: expected 1 occurrence, found {n}")
    return text.replace(old, new, 1)

# Frontend applicant categories + confirmation language.
p = Path('frontend/grantforge-frontend/src/App.jsx')
s = p.read_text()
s = rep(s,
    '                    <option>College / University / Research Institution</option>',
    '                    <option>Public College / University</option>\n                    <option>Private College / University</option>\n                    <option>Research Institution / University Research Foundation</option>',
    'higher ed options')
s = rep(s,
    '                  {form.category === "College / University / Research Institution" && (\n                    <small className="field-guidance">Use the institution as the applicant and the professor, principal investigator, dean, or grant administrator as the contact.</small>\n                  )}',
    '                  {["Public College / University", "Private College / University", "Research Institution / University Research Foundation"].includes(form.category) && (\n                    <small className="field-guidance">Use the legal institution as the applicant and the professor, principal investigator, dean, or grant administrator as the contact. Choose the applicant type that matches the entity that will actually submit the application.</small>\n                  )}',
    'higher ed guidance')
s = rep(s,
    'I have checked my information and selected grant. I agree to the <a href="/terms" target="_blank">Terms</a>, authorize GrantForgeUSA to begin the customized drafting service immediately after payment, and understand the $49.99 service is final and non-refundable once generation begins except where required by law or if GrantForgeUSA fails to deliver the purchased service. Funding is not guaranteed.',
    'I have checked my information and selected grant, opened the official opportunity notice, and confirm the applicant appears to meet its eligibility requirements. I agree to the <a href="/terms" target="_blank">Terms</a>, authorize GrantForgeUSA to begin the customized drafting service immediately after payment, and understand the $49.99 service is final and non-refundable once generation begins except where required by law or if GrantForgeUSA fails to deliver the purchased service. GrantForgeUSA screening is preliminary and funding is not guaranteed.',
    'purchase confirmation')
p.write_text(s)

# Backend type map and eligibility precision.
p = Path('backend/v11_server.py')
s = p.read_text()
s = rep(s,
    '    "college / university / research institution": "HIGHER_ED",',
    '    "public college / university": "HIGHER_ED_PUBLIC",\n    "private college / university": "HIGHER_ED_PRIVATE",\n    "research institution / university research foundation": "RESEARCH_INSTITUTION",\n    "college / university / research institution": "HIGHER_ED",',
    'intake map')
# Required project-specific overlap.
s = s.replace(
    '("EDU_K12", "HIGHER_ED", "SMALL_BUSINESS", "FOR_PROFIT")',
    '("EDU_K12", "HIGHER_ED", "HIGHER_ED_PUBLIC", "HIGHER_ED_PRIVATE", "RESEARCH_INSTITUTION", "SMALL_BUSINESS", "FOR_PROFIT")')
# Eligibility needles.
s = rep(s,
    '        "HIGHER_ED": ("institution of higher education", "institutions of higher education", "college", "colleges", "university", "universities", "higher education"),',
    '        "HIGHER_ED": ("institution of higher education", "institutions of higher education", "college", "colleges", "university", "universities", "higher education"),\n        "HIGHER_ED_PUBLIC": ("public institution of higher education", "public institutions of higher education", "state controlled institution", "public college", "public university", "college", "colleges", "university", "universities"),\n        "HIGHER_ED_PRIVATE": ("private institution of higher education", "private institutions of higher education", "private college", "private university", "college", "colleges", "university", "universities"),\n        "RESEARCH_INSTITUTION": ("research institution", "research institutions", "research organization", "research organizations", "university research foundation", "research foundation", "research foundations"),',
    'eligibility needles')
# Numeric code map. 25 remains handled as free-text only.
s = rep(s,
    '        "HIGHER_ED": {"06", "20", "99"},',
    '        "HIGHER_ED": {"06", "20", "99"},\n        "HIGHER_ED_PUBLIC": {"06", "99"},\n        "HIGHER_ED_PRIVATE": {"20", "99"},\n        "RESEARCH_INSTITUTION": {"99"},',
    'eligibility code map')
# Narrative profiles.
s = rep(s,
    '        "HIGHER_ED": ("higher-education or research institution", "research, teaching, institutional, or sponsored-program delivery", "the identified research, education, or community beneficiaries"),',
    '        "HIGHER_ED": ("higher-education or research institution", "research, teaching, institutional, or sponsored-program delivery", "the identified research, education, or community beneficiaries"),\n        "HIGHER_ED_PUBLIC": ("public college or university", "research, teaching, institutional, extension, or sponsored-program delivery", "the identified research, education, or community beneficiaries"),\n        "HIGHER_ED_PRIVATE": ("private college or university", "research, teaching, institutional, or sponsored-program delivery", "the identified research, education, or community beneficiaries"),\n        "RESEARCH_INSTITUTION": ("research institution or university research foundation", "research or sponsored-program delivery", "the identified research or community beneficiaries"),',
    'narrative profiles')
# Safer fit-note phrasing.
s = rep(s,
    '    fit_notes.append(f"Eligibility matched for {applicant_type}.")',
    '    fit_notes.append(f"Applicant category passed preliminary Grants.gov synopsis screening for {applicant_type}; all additional eligibility conditions still require verification in the official notice.")',
    'fit note')
p.write_text(s)

# Live Grants.gov search codes.
p = Path('backend/grantsgov_live.py')
s = p.read_text()
s = rep(s,
    '    "HIGHER_ED": ["06", "20", "25", "99"],',
    '    "HIGHER_ED": ["06", "20", "25", "99"],\n    "HIGHER_ED_PUBLIC": ["06", "25", "99"],\n    "HIGHER_ED_PRIVATE": ["20", "25", "99"],\n    "RESEARCH_INSTITUTION": ["25", "99"],',
    'live higher ed codes')
p.write_text(s)

# Frontend tests.
p = Path('frontend/grantforge-frontend/tests/integration.test.mjs')
s = p.read_text()
s = s.replace(
    'assert.ok(appSource.includes("College / University / Research Institution"));',
    'assert.ok(appSource.includes("Public College / University"));\n  assert.ok(appSource.includes("Private College / University"));\n  assert.ok(appSource.includes("Research Institution / University Research Foundation"));')
if 'opened the official opportunity notice' not in s:
    marker = 'test("public intake includes higher education and no student-aid surface", () => {'
    # Existing block will continue to cover no student aid; add a separate assertion near EOF.
    s += '\n\ntest("checkout requires official eligibility review before customized drafting", () => {\n  assert.ok(appSource.includes("opened the official opportunity notice"));\n  assert.ok(appSource.includes("screening is preliminary"));\n});\n'
p.write_text(s)

# Backend tests.
p = Path('backend/tests/test_v11_server.py')
s = p.read_text()
extra = '''\n\ndef test_public_and_private_higher_ed_codes_are_not_interchangeable():\n    public = {"eligibility_codes": ["06"]}\n    private = {"eligibility_codes": ["20"]}\n    assert srv._is_eligible_for_applicant(public, "HIGHER_ED_PUBLIC") is True\n    assert srv._is_eligible_for_applicant(public, "HIGHER_ED_PRIVATE") is False\n    assert srv._is_eligible_for_applicant(private, "HIGHER_ED_PRIVATE") is True\n    assert srv._is_eligible_for_applicant(private, "HIGHER_ED_PUBLIC") is False\n\ndef test_research_institution_requires_unrestricted_or_other_text_confirmation():\n    research_other = {"eligibility_codes": ["25"], "eligibility_text": "Eligible applicants include other research institutions and organizations and university research foundations."}\n    generic_public = {"eligibility_codes": ["06"]}\n    assert srv._is_eligible_for_applicant(research_other, "RESEARCH_INSTITUTION") is True\n    assert srv._is_eligible_for_applicant(generic_public, "RESEARCH_INSTITUTION") is False\n'''
if 'test_public_and_private_higher_ed_codes_are_not_interchangeable' not in s:
    s += extra
p.write_text(s)
print('higher-ed precision patched')
