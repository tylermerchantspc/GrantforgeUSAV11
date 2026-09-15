from backend.grantsgov_live import _canonical_sector


def test_agriculture_code_and_text_classifies_as_agriculture():
    assert _canonical_sector(["AG"], "Agriculture and Food Research Initiative Education and Workforce Development", "Agricultural education and workforce development") == "agriculture / rural development"


def test_ovw_violence_program_classifies_as_victim_services():
    assert _canonical_sector(["LJL"], "Training and Services to End Violence and Abuse", "Services for survivors of domestic violence and abuse") == "victim services / justice"


def test_cybersecurity_text_overrides_broad_science_code():
    assert _canonical_sector(["ST"], "State Cybersecurity Modernization", "Cybersecurity and network security capacity") == "cybersecurity / technology"


def test_food_pantry_classifies_as_food_access():
    assert _canonical_sector(["FN", "CD"], "Community Food Pantry Expansion", "Food insecurity and food access") == "food access / nutrition"
