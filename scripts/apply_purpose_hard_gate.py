from pathlib import Path

server_path = Path('backend/v11_server.py')
text = server_path.read_text()

start = text.index('def _relevance_compatible(')
end = text.index('\n\ndef _purchaseable_fit', start)
replacement = r'''def _purpose_text(gr: Dict[str, Any]) -> str:
    """Return only opportunity-purpose text; exclude applicant eligibility metadata."""
    labels = gr.get("sector_labels") or []
    if not isinstance(labels, list):
        labels = []
    return " ".join([
        str(gr.get("title") or ""),
        str(gr.get("program") or ""),
        str(gr.get("summary") or ""),
        " ".join(str(label) for label in labels),
    ]).lower()


def _client_purpose_text(payload: Dict[str, Any]) -> str:
    return " ".join([
        str(payload.get("projectTitle") or ""),
        str(payload.get("keywords") or ""),
        str(payload.get("need") or ""),
        str(payload.get("notes") or ""),
        str(payload.get("audience") or ""),
    ]).lower()


_PURPOSE_STOPWORDS = {
    "about", "access", "across", "agency", "applicant", "application", "available",
    "benefit", "benefits", "county", "community", "communities", "federal", "funding",
    "government", "grant", "grants", "health", "help", "improve", "improving", "initiative",
    "local", "million", "national", "nonprofit", "organization", "organizations", "people",
    "program", "programs", "project", "projects", "provide", "providing", "public", "research",
    "rural", "service", "services", "state", "states", "study", "support", "system", "systems",
    "technology", "training", "university", "workforce", "year", "years",
}

_PURPOSE_TOKEN_ALIASES = {
    "agricultural": "agriculture", "farming": "farm", "farms": "farm",
    "students": "student", "educators": "educator", "schools": "school",
    "cybersecurity": "cyber", "cyber-security": "cyber",
    "victims": "victim", "survivors": "survivor",
    "homelessness": "homeless", "historic": "history", "historical": "history",
    "photographic": "photography", "nutritional": "nutrition",
}

_PURPOSE_GROUPS = {
    "water_infrastructure": (
        "drinking water", "wastewater", "waste water", "sewer", "water main", "water mains",
        "lead service", "stormwater", "storm water", "water infrastructure", "water treatment",
    ),
    "cybersecurity": (
        "cybersecurity", "cyber security", "ransomware", "information security", "network security",
        "incident response", "security operations",
    ),
    "victim_services": (
        "domestic violence", "sexual assault", "victim services", "victim service", "crime victim",
        "legal advocacy", "safety planning", "human trafficking",
    ),
    "homelessness": (
        "homeless", "homelessness", "emergency shelter", "transitional shelter", "housing stability",
    ),
    "food_access": (
        "food insecurity", "food access", "mobile market", "food pantry", "food bank", "hunger",
        "nutrition assistance", "healthy food access",
    ),
    "agriculture": (
        "agriculture", "agricultural", "farming", " farm ", "farmer", "soil", "crop", "livestock",
        "food sovereignty", "precision agriculture",
    ),
    "clinical_health": (
        "clinical trial", "clinical study", "patient", "medical", "therapeutic", "treatment",
        "disease", "diabetes", "cancer", "glioblastoma", "obesity", "cardiovascular", "opioid",
    ),
    "conservation": (
        "endangered species", "wildlife", "habitat", "conservation", "forest", "forestry",
        "land acquisition", "ecosystem", "biodiversity",
    ),
    "climate_earth": (
        "climate", "earth system", "atmospheric", "ocean", "meteorological", "weather science",
    ),
    "education_stem": (
        "education", "educational", "school", "student", "teacher", "stem", "robotics", "classroom",
        "career pathway", "career pathways",
    ),
    "housing": (
        "public housing", "affordable housing", "housing rehabilitation", "housing rehab",
        "multifamily housing", "accessibility rehabilitation",
    ),
    "arts_history": (
        "photography", "museum", "history", "historic", "heritage", "humanities", "arts", "artistic",
        "book publication", "cultural heritage",
    ),
    "energy_efficiency": (
        "energy efficiency", "renewable energy", "rural energy", "energy use", "hvac",
        "equipment efficiency", "energy upgrade",
    ),
    "business_rd": (
        "sbir", "sttr", "prototype", "commercialization", "research and development", "r&d",
        "technology development", "proof of concept",
    ),
}

_ANCHOR_REQUIRED_GROUPS = {
    "water_infrastructure", "cybersecurity", "victim_services", "homelessness", "food_access",
    "clinical_health", "conservation", "climate_earth", "housing", "arts_history",
    "energy_efficiency", "business_rd",
}


def _purpose_groups(text: str) -> set[str]:
    padded = f" {str(text or '').lower()} "
    return {
        group for group, phrases in _PURPOSE_GROUPS.items()
        if any(phrase in padded for phrase in phrases)
    }


def _purpose_tokens(text: str) -> set[str]:
    out: set[str] = set()
    for raw in re.findall(r"[a-z0-9][a-z0-9-]+", str(text or "").lower()):
        token = _PURPOSE_TOKEN_ALIASES.get(raw, raw)
        if len(token) < 4 or token in _PURPOSE_STOPWORDS:
            continue
        if token.endswith("ies") and len(token) > 5:
            token = token[:-3] + "y"
        elif token.endswith("s") and len(token) > 5 and not token.endswith(("ss", "us", "is")):
            token = token[:-1]
        if token not in _PURPOSE_STOPWORDS:
            out.add(token)
    return out


def _purpose_overlap_terms(gr: Dict[str, Any], payload: Dict[str, Any]) -> set[str]:
    return _purpose_tokens(_purpose_text(gr)) & _purpose_tokens(_client_purpose_text(payload))


def _relevance_compatible(gr: Dict[str, Any], payload: Dict[str, Any], applicant_type: str) -> Tuple[bool, str]:
    """Hard program-purpose gate. Eligibility may narrow candidates but can never create relevance."""
    grant_blob = _purpose_text(gr)
    client_blob = _client_purpose_text(payload)
    client_groups = _purpose_groups(client_blob)
    grant_groups = _purpose_groups(grant_blob)
    overlap = _purpose_overlap_terms(gr, payload)

    conflict_terms = {"nuclear", "radioactive", "petroleum", "pipeline"}
    grant_terms = _purpose_tokens(grant_blob)
    client_terms = _purpose_tokens(client_blob)
    if (conflict_terms & grant_terms) and not (conflict_terms & client_terms):
        return False, "Opportunity subject matter conflicts with the submitted project."
    if ("oil" in grant_terms or ("natural" in grant_terms and "gas" in grant_terms)) and not any(x in client_blob for x in ("oil", "natural gas", "petroleum")):
        return False, "Opportunity is focused on oil/gas rather than the submitted project."

    if client_groups and grant_groups and client_groups.isdisjoint(grant_groups):
        return False, "Program purpose does not match the submitted project's subject matter."

    anchored_client_groups = client_groups & _ANCHOR_REQUIRED_GROUPS
    if anchored_client_groups and not (anchored_client_groups & grant_groups):
        return False, "Opportunity does not contain the project's required subject-matter anchor."
    if anchored_client_groups and not overlap:
        return False, "No project-specific topic anchor appears in the opportunity purpose."

    shared_groups = client_groups & grant_groups
    minimum_overlap = 1 if shared_groups & {"agriculture", "education_stem"} else 2
    if len(overlap) < minimum_overlap:
        return False, "Insufficient project-specific overlap in the opportunity purpose."

    rd_signals = (
        "research and development", "research & development", "r&d", "prototype",
        "pre-pilot", "prepilot", "pre-piloting", "scale-up", "scale up",
        "emerging chemical technolog", "technology demonstration", "proof of concept",
    )
    client_rd_signals = (
        "research", "r&d", "prototype", "pilot", "scale-up", "scale up",
        "chemical technolog", "demonstration", "proof of concept", "commercialization",
    )
    client_explicit_non_rd = any(term in client_blob for term in (
        "not an r&d", "not r&d", "not a research project", "not a pilot", "not a prototype",
        "capital equipment efficiency", "operational improvements", "equipment upgrade", "equipment replacement",
    ))
    client_has_rd_intent = any(term in client_blob for term in client_rd_signals) and not client_explicit_non_rd
    if any(term in grant_blob for term in rd_signals) and not client_has_rd_intent:
        return False, "Opportunity requires an R&D/pilot project not identified in the submitted project."

    return True, "Program-purpose gate passed: " + ", ".join(sorted(overlap)[:6]) + "."
'''
text = text[:start] + replacement + text[end:]

old = '''    category = payload.get("category") or payload.get("who") or ""\n    amount = _safe_float(payload.get("amountRequested"))\n    applicant_type = normalize_applicant_type(category)\n    kws = normalized_keywords(payload.get("keywords", ""))\n    requested_sector = infer_client_sector(kws)\n    state_value = payload.get("state") or payload.get("eligible_state") or ""\n'''
new = '''    category = payload.get("category") or payload.get("who") or ""\n    amount = _safe_float(payload.get("amountRequested"))\n    applicant_type = normalize_applicant_type(category)\n    project_context = ", ".join(filter(None, [\n        payload.get("projectTitle", ""), payload.get("keywords", ""), payload.get("need", ""),\n        payload.get("notes", ""), payload.get("audience", ""),\n    ]))\n    kws = normalized_keywords(project_context)\n    requested_sector = infer_client_sector(kws)\n    state_value = payload.get("state") or payload.get("eligible_state") or ""\n'''
if old not in text:
    raise SystemExit('shortlist context block not found')
text = text.replace(old, new, 1)

old = '''        live_query = " ".join(filter(None, [payload.get("projectTitle", ""), payload.get("keywords", "")])).strip()\n'''
new = '''        live_query = ", ".join(filter(None, [payload.get("projectTitle", ""), payload.get("keywords", ""), payload.get("need", "")])).strip()\n'''
if old not in text:
    raise SystemExit('live_query block not found')
text = text.replace(old, new, 1)

old = '''    tags = normalized_tags(gr.get("tags", []))\n'''
new = '''    # Live Grants.gov tags include applicant-eligibility language; never score that as project relevance.\n    tags = [] if str(gr.get("source") or "").startswith("Grants.gov") else normalized_tags(gr.get("tags", []))\n'''
if old not in text:
    raise SystemExit('score tags block not found')
text = text.replace(old, new, 1)

old = '''            purchasable = s["fit"] in ("Strong Match", "Possible Match")\n'''
new = '''            purchasable = relevance_ok and s["fit"] in ("Strong Match", "Possible Match")\n'''
if old not in text:
    raise SystemExit('purchase gate block not found')
text = text.replace(old, new, 1)

marker = '''    sector_rules = [\n        (\n            "agriculture / rural development",\n'''
insertion = '''    sector_rules = [\n        (\n            "water / infrastructure",\n            ["drinking water", "wastewater", "sewer", "water main", "lead service", "stormwater", "water infrastructure"],\n        ),\n        (\n            "cybersecurity / technology",\n            ["cybersecurity", "cyber security", "ransomware", "information security", "network security"],\n        ),\n        (\n            "victim services / justice",\n            ["domestic violence", "sexual assault", "victim services", "legal advocacy", "human trafficking"],\n        ),\n        (\n            "food access / nutrition",\n            ["food insecurity", "food access", "mobile market", "food pantry", "food bank", "hunger", "nutrition assistance"],\n        ),\n        (\n            "agriculture / rural development",\n'''
if marker not in text:
    raise SystemExit('sector rules marker not found')
text = text.replace(marker, insertion, 1)
server_path.write_text(text)

live_path = Path('backend/grantsgov_live.py')
live = live_path.read_text()
marker = '''SECTOR_FUNDING_CODES = {\n    "education / STEM": ["ED", "ST"],\n'''
insertion = '''SECTOR_FUNDING_CODES = {\n    "water / infrastructure": ["CD", "ENV", "NR"],\n    "cybersecurity / technology": ["ST", "LJL", "DPR"],\n    "victim services / justice": ["LJL"],\n    "food access / nutrition": ["FN", "AG", "CD"],\n    "education / STEM": ["ED", "ST"],\n'''
if marker not in live:
    raise SystemExit('funding code marker not found')
live = live.replace(marker, insertion, 1)
live_path.write_text(live)

tests = r'''import backend.v11_server as srv


def grant(title, summary, program="Federal Program"):
    return {"title": title, "summary": summary, "program": program, "sector_labels": [], "tags": [], "source": "Grants.gov live API"}


def payload(title, keywords, need="", notes="", audience="Residents"):
    return {"projectTitle": title, "keywords": keywords, "need": need, "notes": notes, "audience": audience}


def check(g, p, applicant="NONPROFIT"):
    return srv._relevance_compatible(g, p, applicant)


def test_water_rejects_global_health():
    ok, _ = check(grant("Advancing Global Health", "Supports global health systems, medical research, and clinical public health programs."), payload("Drinking Water Main Replacement and Lead Service Reduction", "drinking water, lead service lines, water infrastructure, public health", "Replace aging water mains and reduce lead exposure."), "GOV_LOCAL")
    assert ok is False


def test_water_accepts_water_infrastructure():
    ok, _ = check(grant("Drinking Water Infrastructure Improvement", "Replace drinking water mains, lead service lines, and treatment infrastructure."), payload("Drinking Water Main Replacement", "drinking water, lead service lines, water infrastructure"), "GOV_LOCAL")
    assert ok is True


def test_tribal_food_rejects_rare_disease_trial():
    ok, _ = check(grant("Clinical Studies of Orphan Products", "Clinical trials for rare diseases and therapeutic products."), payload("Tribal Food Sovereignty Program", "tribal, food sovereignty, agriculture, youth, nutrition", "Increase local food production and agricultural education."), "TRIBAL")
    assert ok is False


def test_ag_stem_accepts_agriculture_program():
    ok, _ = check(grant("Agriculture and Food Research Initiative Education and Workforce Development", "Agricultural science education, experiential learning, and workforce development."), payload("Rural Agricultural STEM Career Pathways", "STEM, agriculture, agricultural science, engineering, careers", "Expand agricultural science and engineering education."), "HIGHER_ED_PUBLIC")
    assert ok is True


def test_food_access_rejects_climate_science():
    ok, _ = check(grant("Earth System Science and Services Partnership", "Climate, ocean, atmospheric, and earth system science research."), payload("Rural Food Access Mobile Market", "food insecurity, rural, mobile market, nutrition, local food", "Improve healthy food access."))
    assert ok is False


def test_shelter_rejects_forest_conservation():
    ok, _ = check(grant("Community Forest and Open Space Conservation Program", "Acquire and conserve forest land and open space."), payload("Winter Emergency Shelter and Meal Program", "homelessness, emergency shelter, meals, housing stability"))
    assert ok is False


def test_cybersecurity_rejects_endangered_species():
    ok, _ = check(grant("Endangered Species Recovery Land Acquisition", "Conservation and land acquisition for endangered species habitat."), payload("Rural Local Government Cybersecurity Modernization", "cybersecurity, local government, critical infrastructure, incident response"), "GOV_STATE")
    assert ok is False


def test_diabetes_rejects_unrelated_cancer_research():
    ok, _ = check(grant("Glioblastoma Therapeutics Network", "Clinical trials and therapeutic research for glioblastoma brain cancer."), payload("Rural Diabetes Prevention Implementation Study", "diabetes prevention, rural health, implementation science, public health"), "HIGHER_ED_PRIVATE")
    assert ok is False


def test_diabetes_accepts_diabetes_prevention():
    ok, _ = check(grant("Diabetes Prevention Research Program", "Clinical and community diabetes prevention interventions for adults at risk of type 2 diabetes."), payload("Rural Diabetes Prevention Implementation Study", "diabetes prevention, rural health, implementation science, public health"), "HIGHER_ED_PRIVATE")
    assert ok is True


def test_history_book_rejects_generic_diplomacy_program():
    ok, _ = check(grant("U.S. Mission Annual Program Statement", "Supports bilateral diplomacy, exchanges, economic cooperation, and regional partnerships."), payload("Civil War Heritage Photography Book", "photography, history, Civil War, book publication, heritage"), "INDIVIDUAL")
    assert ok is False


def test_domestic_violence_rejects_climate_program():
    ok, _ = check(grant("Climate Program Office Partnership", "Climate and earth system science, atmospheric observations, and ocean research."), payload("Rural Domestic Violence Legal Advocacy", "domestic violence, victim services, legal advocacy, rural, safety planning"))
    assert ok is False


def test_domestic_violence_accepts_victim_services():
    ok, _ = check(grant("Rural Domestic Violence Victim Services", "Expands domestic violence victim services, legal advocacy, and safety planning in rural areas."), payload("Rural Domestic Violence Legal Advocacy", "domestic violence, victim services, legal advocacy, rural, safety planning"))
    assert ok is True
'''
Path('backend/tests/test_purpose_relevance.py').write_text(tests)
print('purpose hard-gate patch staged')
