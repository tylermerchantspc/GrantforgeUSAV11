from pathlib import Path

p = Path('backend/v11_server.py')
s = p.read_text()

marker = '''_STRICT_PURPOSE_GROUPS = {\n    "diabetes", "opioid", "mental_health", "obesity", "cancer", "neurology", "aging",\n    "flood_mitigation", "apprenticeship", "food_sovereignty", "pollinator", "career_education",\n}\n'''
insert = '''_STRICT_PURPOSE_GROUPS = {\n    "diabetes", "opioid", "mental_health", "obesity", "cancer", "neurology", "aging",\n    "flood_mitigation", "apprenticeship", "food_sovereignty", "pollinator", "career_education",\n}\n\n_TITLE_REQUIRED_PURPOSES = {\n    "diabetes": ("diabetes", "glycemic"),\n    "opioid": ("opioid", "overdose", "substance use", "addiction"),\n    "mental_health": ("suicide", "mental health", "behavioral health", "psychiatr"),\n    "obesity": ("obesity", "anti-obesity", "weight management"),\n    "cancer": ("cancer", "glioblastoma", "oncology", "tumor"),\n    "neurology": ("brain", "neurolog", "neuroscience"),\n    "aging": ("aging", "geriatric", "alzheimer"),\n    "apprenticeship": ("apprentice", "apprenticeship"),\n    "food_sovereignty": ("food sovereignty",),\n    "pollinator": ("pollinator", "bee", "monarch"),\n    "career_education": ("education", "workforce", "career", "extension"),\n}\n'''
if marker not in s:
    raise SystemExit('strict purpose marker not found')
s = s.replace(marker, insert, 1)

marker = '''    strict_client_groups = client_groups & _STRICT_PURPOSE_GROUPS\n    missing_strict_groups = strict_client_groups - grant_groups\n    if missing_strict_groups:\n        return False, "Opportunity misses required project-specific purpose: " + ", ".join(sorted(missing_strict_groups)) + "."\n\n    if client_groups and grant_groups and client_groups.isdisjoint(grant_groups):\n'''
insert = '''    strict_client_groups = client_groups & _STRICT_PURPOSE_GROUPS\n    missing_strict_groups = strict_client_groups - grant_groups\n    if missing_strict_groups:\n        return False, "Opportunity misses required project-specific purpose: " + ", ".join(sorted(missing_strict_groups)) + "."\n\n    # Narrow clinical and program-specific projects require title-level evidence. This keeps an\n    # incidental mention in a broad synopsis from turning an unrelated program into a match.\n    for purpose in strict_client_groups:\n        title_terms = _TITLE_REQUIRED_PURPOSES.get(purpose)\n        if title_terms and not any(term in grant_title for term in title_terms):\n            return False, f"Opportunity title does not identify the required {purpose} purpose."\n\n    # Named tribal-college programs are institution-specific; generic higher-ed eligibility is not enough.\n    if "tribal college" in grant_title:\n        applicant_blob = " ".join([\n            str(payload.get("organization") or ""), str(payload.get("notes") or ""),\n            str(payload.get("category") or ""),\n        ]).lower()\n        if "tribal college" not in applicant_blob and "1994 institution" not in applicant_blob:\n            return False, "Opportunity is specifically for tribal colleges/1994 institutions."\n\n    if client_groups and grant_groups and client_groups.isdisjoint(grant_groups):\n'''
if marker not in s:
    raise SystemExit('strict relevance block marker not found')
s = s.replace(marker, insert, 1)
p.write_text(s)

tp=Path('backend/tests/test_purpose_relevance.py')
t=tp.read_text()
extra=r'''

def test_diabetes_incidental_summary_mention_does_not_override_wrong_title():
    ok, _ = check(
        grant("Anti-Obesity Medication Clinical Centers", "Obesity treatment research that may track diabetes and metabolic outcomes."),
        payload("Rural Diabetes Prevention Study", "diabetes prevention, type 2 diabetes, implementation science"),
        "HIGHER_ED_PRIVATE",
    )
    assert ok is False


def test_opioid_incidental_summary_mention_does_not_override_wrong_title():
    ok, _ = check(
        grant("BRAIN Circuits Program", "Neuroscience research relevant to addiction and opioid-related brain pathways."),
        payload("Opioid Overdose Prevention Network", "opioid, overdose prevention, naloxone, substance use disorder"),
        "GOV_LOCAL",
    )
    assert ok is False


def test_tribal_college_title_requires_tribal_college_applicant_context():
    gr = grant("Tribal Colleges Extension Program Special Emphasis", "Agricultural extension and education for tribal colleges.")
    p = payload("Rural Agricultural STEM Career Pathways", "agriculture, STEM, career pathways, education")
    p['organization'] = 'Prairie State University'
    p['category'] = 'Public College / University'
    ok, _ = check(gr, p, "HIGHER_ED_PUBLIC")
    assert ok is False


def test_career_pathway_rejects_generic_ag_trade_even_if_summary_mentions_workforce():
    ok, _ = check(
        grant("Coordinating Agricultural Development and International Trade", "Agricultural market development with workforce capacity building overseas."),
        payload("Rural Agricultural STEM Career Pathways", "agriculture, STEM, career pathways, education and workforce development"),
        "HIGHER_ED_PUBLIC",
    )
    assert ok is False
'''
if 'test_diabetes_incidental_summary_mention_does_not_override_wrong_title' not in t:
    tp.write_text(t+extra)
print('third-stage title specificity patch staged')
