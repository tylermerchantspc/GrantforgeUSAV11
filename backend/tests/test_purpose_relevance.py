import backend.v11_server as srv


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
