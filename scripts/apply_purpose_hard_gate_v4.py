from pathlib import Path

server_path = Path('backend/v11_server.py')
s = server_path.read_text()

marker = '''def _purpose_overlap_terms(gr: Dict[str, Any], payload: Dict[str, Any]) -> set[str]:\n    return _purpose_tokens(_purpose_text(gr)) & _purpose_tokens(_client_purpose_text(payload))\n\n\ndef _relevance_compatible(gr: Dict[str, Any], payload: Dict[str, Any], applicant_type: str) -> Tuple[bool, str]:\n'''
insert = '''def _purpose_overlap_terms(gr: Dict[str, Any], payload: Dict[str, Any]) -> set[str]:\n    return _purpose_tokens(_purpose_text(gr)) & _purpose_tokens(_client_purpose_text(payload))\n\n\ndef _grant_requires_research_mode(gr: Dict[str, Any]) -> bool:\n    \"\"\"Identify opportunities whose award mechanism is specifically research/clinical-study work.\"\"\"\n    title = str(gr.get("title") or "")\n    upper = title.upper()\n    if re.search(r"\\b(?:R01|R03|R15|R21|R34|R35|R61|R33|P50|P30|U01|U19|UG3|UH3)\\b", upper):\n        return True\n    lowered = title.lower()\n    return any(term in lowered for term in (\n        "clinical trial", "clinical neuroscience research", "research center",\n        "research centers", "investigator-initiated research", "translational research",\n    ))\n\n\ndef _client_has_research_mode(payload: Dict[str, Any]) -> bool:\n    blob = _client_purpose_text(payload)\n    return any(term in blob for term in (\n        "research", " study", "study ", "clinical trial", "clinical research",\n        "investigator", "evaluate", "evaluation", "r&d", "research and development",\n        "prototype", "proof of concept", "commercialization", "experimental",\n    ))\n\n\ndef _relevance_compatible(gr: Dict[str, Any], payload: Dict[str, Any], applicant_type: str) -> Tuple[bool, str]:\n'''
if marker not in s:
    raise SystemExit('purpose overlap marker not found')
s = s.replace(marker, insert, 1)

marker = '''    if any(term in grant_blob for term in rd_signals) and not client_has_rd_intent:\n        return False, "Opportunity requires an R&D/pilot project not identified in the submitted project."\n\n    # Foreign-mission annual program statements are location/purpose-specific. Generic cultural\n'''
insert = '''    if any(term in grant_blob for term in rd_signals) and not client_has_rd_intent:\n        return False, "Opportunity requires an R&D/pilot project not identified in the submitted project."\n\n    # A service-delivery or capital project must never become purchasable merely because its\n    # subject appears in a clinical/research NOFO. Research mechanisms require explicit research intent.\n    if _grant_requires_research_mode(gr) and not _client_has_research_mode(payload):\n        return False, "Opportunity requires a research/clinical-study project, but the submitted project is operational/service delivery."\n\n    # Foreign-mission annual program statements are location/purpose-specific. Generic cultural\n'''
if marker not in s:
    raise SystemExit('research insertion marker not found')
s = s.replace(marker, insert, 1)
server_path.write_text(s)

live_path = Path('backend/grantsgov_live.py')
live = live_path.read_text()
start = live.index('def _canonical_sector(')
end = live.index('\n\ndef _detail_to_grant', start)
replacement = r'''def _canonical_sector(activity_codes: Iterable[str], title: str = "", summary: str = "") -> str:
    """Classify the opportunity by its actual purpose first, then use Grants.gov category codes as fallback."""
    blob = f"{title} {summary}".lower()

    text_rules = [
        ("victim services / justice", ("domestic violence", "sexual assault", "victim service", "crime victim", "violence and abuse", "violence against women")),
        ("cybersecurity / technology", ("cybersecurity", "cyber security", "ransomware", "information security", "network security")),
        ("water / infrastructure", ("drinking water", "wastewater", "sewer", "water main", "lead service", "stormwater", "water infrastructure")),
        ("food access / nutrition", ("food insecurity", "food pantry", "food bank", "mobile market", "hunger", "nutrition assistance", "food access")),
        ("agriculture / rural development", ("agriculture", "agricultural", "farming", "farmer", "crop", "livestock", "soil", "food research initiative")),
        ("public safety / emergency management", ("firefighter", "fire department", "wildland fire", "emergency response", "disaster preparedness")),
        ("conservation / environment", ("endangered species", "wildlife", "habitat", "conservation", "pollinator", "ecosystem", "forestry")),
        ("arts / culture", ("arts", "artistic", "humanities", "cultural heritage", "museum", "historic preservation")),
        ("housing / community development", ("public housing", "affordable housing", "housing rehabilitation", "homeless", "emergency shelter")),
        ("energy / manufacturing efficiency", ("energy efficiency", "renewable energy", "energy use", "manufacturing efficiency")),
        ("workforce development", ("apprenticeship", "apprentice", "workforce development", "job training", "employment training")),
        ("education / STEM", ("education", "student", "school", "teacher", "literacy", "classroom", "career pathway")),
        ("telehealth / healthcare", ("clinical", "medical", "disease", "diabetes", "opioid", "substance use", "mental health", "behavioral health", "healthcare", "health care")),
        ("entrepreneurship / innovation", ("small business innovation", "sbir", "sttr", "commercialization", "technology development", "prototype")),
    ]
    for sector, phrases in text_rules:
        if any(phrase in blob for phrase in phrases):
            return sector

    code_set = {str(code or "").strip() for code in activity_codes}
    fallback = [
        ("victim services / justice", {"LJL"}),
        ("agriculture / rural development", {"AG", "RD"}),
        ("food access / nutrition", {"FN"}),
        ("telehealth / healthcare", {"HL"}),
        ("housing / community development", {"HO", "CD"}),
        ("public safety / emergency management", {"DPR"}),
        ("conservation / environment", {"ENV", "NR"}),
        ("arts / culture", {"AR", "HU"}),
        ("energy / manufacturing efficiency", {"EN"}),
        ("workforce development", {"ELT"}),
        ("education / STEM", {"ED"}),
        ("entrepreneurship / innovation", {"BC", "ST"}),
    ]
    for sector, codes in fallback:
        if code_set.intersection(codes):
            return sector
    return ""
'''
live = live[:start] + replacement + live[end:]
old = '        "sector": _canonical_sector(activity_codes),\n'
new = '        "sector": _canonical_sector(activity_codes, title, summary),\n'
if old not in live:
    raise SystemExit('sector call marker not found')
live = live.replace(old, new, 1)
live_path.write_text(live)

# Focused regression tests for research-mode compatibility.
tp = Path('backend/tests/test_purpose_relevance.py')
t = tp.read_text()
extra = r'''

def test_operational_opioid_program_rejects_clinical_research_mechanism():
    ok, _ = check(
        grant("Exploratory Clinical Neuroscience Research on Substance Use Disorders (R61/R33 Clinical Trial Optional)", "Clinical neuroscience research on substance use disorders."),
        payload("Rural Opioid Overdose Prevention and Recovery Network", "opioid, overdose prevention, substance use disorder, recovery, naloxone", "Reduce fatal overdoses and expand evidence-based treatment and recovery navigation.", "County health department partnering with EMS and behavioral-health providers."),
        "GOV_LOCAL",
    )
    assert ok is False


def test_explicit_opioid_research_study_can_use_research_mechanism():
    ok, _ = check(
        grant("Exploratory Clinical Neuroscience Research on Substance Use Disorders (R61/R33 Clinical Trial Optional)", "Clinical neuroscience research on substance use disorders and addiction."),
        payload("Opioid Recovery Intervention Research Study", "opioid, substance use disorder, clinical research", "Evaluate a clinical intervention for opioid use disorder.", "University investigators will conduct the research study."),
        "HIGHER_ED_PUBLIC",
    )
    assert ok is True


def test_ag_education_research_initiative_name_does_not_force_research_mode():
    gr = grant("Agriculture and Food Research Initiative Competitive Grants Program Education and Workforce Development", "Agricultural education, experiential learning, and workforce development.")
    assert srv._grant_requires_research_mode(gr) is False
'''
if 'test_operational_opioid_program_rejects_clinical_research_mechanism' not in t:
    tp.write_text(t + extra)

sector_tests = r'''from backend.grantsgov_live import _canonical_sector


def test_agriculture_code_and_text_classifies_as_agriculture():
    assert _canonical_sector(["AG"], "Agriculture and Food Research Initiative Education and Workforce Development", "Agricultural education and workforce development") == "agriculture / rural development"


def test_ovw_violence_program_classifies_as_victim_services():
    assert _canonical_sector(["LJL"], "Training and Services to End Violence and Abuse", "Services for survivors of domestic violence and abuse") == "victim services / justice"


def test_cybersecurity_text_overrides_broad_science_code():
    assert _canonical_sector(["ST"], "State Cybersecurity Modernization", "Cybersecurity and network security capacity") == "cybersecurity / technology"


def test_food_pantry_classifies_as_food_access():
    assert _canonical_sector(["FN", "CD"], "Community Food Pantry Expansion", "Food insecurity and food access") == "food access / nutrition"
'''
Path('backend/tests/test_grantsgov_sector.py').write_text(sector_tests)
print('stage-4 research-mode and sector hardening staged')
