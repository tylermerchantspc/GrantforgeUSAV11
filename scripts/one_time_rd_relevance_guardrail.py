from pathlib import Path


def rep(text, old, new, label):
    n = text.count(old)
    if n != 1:
        raise SystemExit(f"{label}: expected 1 occurrence, found {n}")
    return text.replace(old, new, 1)

p = Path('backend/v11_server.py')
s = p.read_text()
old = '''    if "tribal" in grant_terms and "tribal" not in client_blob:
        return False, "Opportunity is focused on Tribal programs not identified in the intake."

    # Education and small-business searches are especially vulnerable to broad R&D terms.
'''
new = '''    if "tribal" in grant_terms and "tribal" not in client_blob:
        return False, "Opportunity is focused on Tribal programs not identified in the intake."

    # Do not confuse capital/operational improvement projects with research, prototype,
    # emerging-technology, scale-up, or pre-pilot funding simply because both mention
    # manufacturing, energy, equipment, or technology.
    rd_signals = (
        "research and development", "research & development", "r&d", "prototype",
        "pre-pilot", "prepilot", "pre-piloting", "scale-up", "scale up",
        "emerging chemical technolog", "technology demonstration", "proof of concept",
    )
    client_rd_signals = (
        "research", "r&d", "prototype", "pilot", "scale-up", "scale up",
        "chemical technolog", "demonstration", "proof of concept", "commercialization",
    )
    if any(term in grant_blob for term in rd_signals) and not any(term in client_blob for term in client_rd_signals):
        return False, "Opportunity requires an R&D/pilot project not identified in the submitted project."

    # Education and small-business searches are especially vulnerable to broad R&D terms.
'''
s = rep(s, old, new, 'R&D conflict gate')
p.write_text(s)

p = Path('backend/tests/test_v11_server.py')
s = p.read_text()
extra = '''\n\ndef test_capital_energy_upgrade_does_not_match_unrelated_rd_pilot():\n    grant = {\n        "title": "Accelerating Scale-up and Pre-piloting of Emerging Chemical Technologies",\n        "summary": "Supports research and development, scale-up, pre-piloting, and technology demonstration for emerging chemical technologies in industrial manufacturing.",\n        "tags": ["energy", "manufacturing", "technology", "chemical", "scale-up", "pilot"],\n        "sector": "energy / manufacturing efficiency",\n    }\n    payload = {\n        "projectTitle": "Rural Manufacturing Energy Upgrade",\n        "keywords": "small business, rural energy, energy efficiency, manufacturing",\n        "need": "Reduce energy use by upgrading efficient production equipment.",\n        "notes": "Capital equipment efficiency and operational improvements.",\n    }\n    ok, note = srv._relevance_compatible(grant, payload, "SMALL_BUSINESS")\n    assert ok is False\n    assert "R&D/pilot" in note\n\ndef test_true_rd_project_can_pass_rd_domain_gate_when_specific_terms_overlap():\n    grant = {\n        "title": "Industrial Chemical Technology Demonstration",\n        "summary": "Research and development and prototype demonstration of chemical process technology.",\n        "tags": ["chemical", "prototype", "demonstration", "process"],\n        "sector": "entrepreneurship / innovation",\n    }\n    payload = {\n        "projectTitle": "Chemical Process Prototype Demonstration",\n        "keywords": "chemical process, prototype, demonstration, research",\n        "need": "Pilot a new chemical process prototype for commercialization.",\n        "notes": "R&D pilot and technology demonstration.",\n    }\n    ok, _ = srv._relevance_compatible(grant, payload, "SMALL_BUSINESS")\n    assert ok is True\n'''
if 'test_capital_energy_upgrade_does_not_match_unrelated_rd_pilot' not in s:
    s += extra
p.write_text(s)
print('R&D relevance guardrail patched')
