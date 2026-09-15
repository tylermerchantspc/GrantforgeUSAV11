from pathlib import Path

p = Path('backend/v11_server.py')
s = p.read_text()

old = '''    "clinical_health": (\n        "clinical trial", "clinical study", "patient", "medical", "therapeutic", "treatment",\n        "disease", "diabetes", "cancer", "glioblastoma", "obesity", "cardiovascular", "opioid",\n    ),\n'''
new = '''    "diabetes": ("diabetes", "type 2 diabetes", "glycemic"),\n    "opioid": ("opioid", "overdose", "naloxone", "substance use disorder", "opioid use disorder"),\n    "mental_health": ("suicide", "mental health", "behavioral health", "psychiatr"),\n    "obesity": ("obesity", "anti-obesity", "weight management"),\n    "cancer": ("cancer", "glioblastoma", "oncology", "tumor"),\n    "neurology": ("brain", "neurolog", "neuroscience"),\n    "aging": ("aging", "geriatric", "alzheimer", "older adults"),\n    "flood_mitigation": ("flood", "stormwater", "storm water", "drainage", "hazard mitigation"),\n    "apprenticeship": ("apprenticeship", "apprentice", "registered apprenticeship"),\n    "food_sovereignty": ("food sovereignty", "tribal food sovereignty", "indigenous food sovereignty"),\n    "pollinator": ("pollinator", "pollinators", "bee habitat", "monarch habitat"),\n    "career_education": ("career pathway", "career pathways", "education and workforce", "workforce development", "experiential learning"),\n    "clinical_health": (\n        "clinical trial", "clinical study", "patient", "medical", "therapeutic", "treatment",\n        "disease", "diabetes", "cancer", "glioblastoma", "obesity", "cardiovascular", "opioid",\n        "mental health", "behavioral health", "suicide",\n    ),\n'''
if old not in s:
    raise SystemExit('clinical group marker not found')
s = s.replace(old, new, 1)

old = '''_ANCHOR_REQUIRED_GROUPS = {\n    "water_infrastructure", "cybersecurity", "victim_services", "homelessness", "food_access",\n    "clinical_health", "conservation", "climate_earth", "housing", "arts_history",\n    "energy_efficiency", "business_rd",\n}\n'''
new = '''_ANCHOR_REQUIRED_GROUPS = {\n    "water_infrastructure", "cybersecurity", "victim_services", "homelessness", "food_access",\n    "clinical_health", "conservation", "climate_earth", "housing", "arts_history",\n    "energy_efficiency", "business_rd", "diabetes", "opioid", "mental_health", "obesity",\n    "cancer", "neurology", "aging", "flood_mitigation", "apprenticeship", "food_sovereignty",\n    "pollinator", "career_education",\n}\n\n# These project purposes are narrow enough that a broad parent domain is not sufficient.\n# Example: a diabetes project may not purchase a glioblastoma grant merely because both are health research.\n_STRICT_PURPOSE_GROUPS = {\n    "diabetes", "opioid", "mental_health", "obesity", "cancer", "neurology", "aging",\n    "flood_mitigation", "apprenticeship", "food_sovereignty", "pollinator", "career_education",\n}\n'''
if old not in s:
    raise SystemExit('anchor group marker not found')
s = s.replace(old, new, 1)

marker = '''    if client_groups and grant_groups and client_groups.isdisjoint(grant_groups):\n        return False, "Program purpose does not match the submitted project's subject matter."\n'''
insert = '''    # Foreign-mission annual program statements are location/purpose-specific. Generic cultural\n    # or arts language is not enough for a domestic local project to qualify.\n    grant_title = str(gr.get("title") or "").lower()\n    if "u.s. mission to " in grant_title and not any(term in client_blob for term in (\n        "international", "international exchange", "cultural exchange", "diplomacy",\n        "foreign affairs", "export", "australia", "embassy",\n    )):\n        return False, "Foreign-mission opportunity does not match the submitted domestic project purpose."\n\n    strict_client_groups = client_groups & _STRICT_PURPOSE_GROUPS\n    missing_strict_groups = strict_client_groups - grant_groups\n    if missing_strict_groups:\n        return False, "Opportunity misses required project-specific purpose: " + ", ".join(sorted(missing_strict_groups)) + "."\n\n    if client_groups and grant_groups and client_groups.isdisjoint(grant_groups):\n        return False, "Program purpose does not match the submitted project's subject matter."\n'''
if marker not in s:
    raise SystemExit('relevance insertion marker not found')
s = s.replace(marker, insert, 1)
p.write_text(s)

# Extend focused tests.
tp = Path('backend/tests/test_purpose_relevance.py')
t = tp.read_text()
extra = r'''

def test_diabetes_specificity_rejects_obesity_trial():
    ok, _ = check(
        grant("Anti-Obesity Medication Clinical Centers", "Clinical trials evaluating obesity medications in children and adolescents."),
        payload("Rural Diabetes Prevention Study", "diabetes prevention, type 2 diabetes, implementation science"),
        "HIGHER_ED_PRIVATE",
    )
    assert ok is False


def test_opioid_specificity_rejects_unrelated_brain_research():
    ok, _ = check(
        grant("BRAIN Circuits Research Program", "Neuroscience research on brain circuits and neural systems."),
        payload("Opioid Overdose Prevention Network", "opioid, overdose prevention, naloxone, substance use disorder"),
        "GOV_LOCAL",
    )
    assert ok is False


def test_mental_health_specificity_rejects_aging_award():
    ok, _ = check(
        grant("Emerging Leaders Career Development Award in Aging", "Research career development focused on aging and geriatric medicine."),
        payload("Rural Adolescent Suicide Prevention Research", "suicide prevention, adolescent mental health, behavioral health"),
        "HIGHER_ED_PRIVATE",
    )
    assert ok is False


def test_apprenticeship_rejects_agriculture_processing_program():
    ok, _ = check(
        grant("Meat and Poultry Processing Expansion", "Supports processing capacity for agricultural products and food supply chains."),
        payload("Advanced Manufacturing Registered Apprenticeship Expansion", "registered apprenticeship, workforce, manufacturing, skills"),
        "GOV_STATE",
    )
    assert ok is False


def test_food_sovereignty_rejects_generic_plant_pest_program():
    ok, _ = check(
        grant("Plant Pest and Disease Management", "Agricultural plant pest detection, prevention, and disease management."),
        payload("Tribal Food Sovereignty and Youth Agriculture", "tribal, food sovereignty, agriculture, youth, nutrition"),
        "TRIBAL",
    )
    assert ok is False


def test_pollinator_project_rejects_feral_swine_program():
    ok, _ = check(
        grant("Feral Swine Eradication and Control", "Agricultural conservation and control of invasive feral swine."),
        payload("Pollinator Habitat Restoration Research", "pollinator, habitat restoration, conservation, agriculture, ecology"),
        "HIGHER_ED_PUBLIC",
    )
    assert ok is False


def test_domestic_arts_project_rejects_foreign_mission_cultural_aps():
    ok, _ = check(
        grant("U.S. Mission to Australia Annual Program Statement", "Supports cultural heritage, arts exchanges, education, and bilateral engagement in Australia."),
        payload("Civil War Heritage Photography Book", "photography, history, Civil War, book publication, heritage"),
        "INDIVIDUAL",
    )
    assert ok is False


def test_ag_career_pathway_requires_career_education_purpose():
    ok, _ = check(
        grant("International Agricultural Trade Development", "Supports agricultural trade promotion and market development overseas."),
        payload("Rural Agricultural STEM Career Pathways", "STEM, agriculture, agricultural science, engineering, careers, career pathways"),
        "HIGHER_ED_PUBLIC",
    )
    assert ok is False


def test_ag_career_pathway_accepts_education_workforce_program():
    ok, _ = check(
        grant("Agriculture Education and Workforce Development", "Supports agricultural science education, experiential learning, and career pathways."),
        payload("Rural Agricultural STEM Career Pathways", "STEM, agriculture, agricultural science, engineering, careers, career pathways"),
        "HIGHER_ED_PUBLIC",
    )
    assert ok is True
'''
if 'test_diabetes_specificity_rejects_obesity_trial' not in t:
    tp.write_text(t + extra)
print('second-stage purpose specificity patch staged')
