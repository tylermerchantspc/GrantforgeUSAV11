from pathlib import Path


def rep(text, old, new, label):
    n = text.count(old)
    if n != 1:
        raise SystemExit(f"{label}: expected 1 occurrence, found {n}")
    return text.replace(old, new, 1)

p = Path('backend/v11_server.py')
s = p.read_text()
old = '''    if any(term in grant_blob for term in rd_signals) and not any(term in client_blob for term in client_rd_signals):
        return False, "Opportunity requires an R&D/pilot project not identified in the submitted project."
'''
new = '''    client_explicit_non_rd = any(
        term in client_blob
        for term in (
            "not an r&d", "not r&d", "not a research project", "not a pilot",
            "not a prototype", "capital equipment efficiency", "operational improvements",
            "equipment upgrade", "equipment replacement",
        )
    )
    client_has_rd_intent = any(term in client_blob for term in client_rd_signals) and not client_explicit_non_rd
    if any(term in grant_blob for term in rd_signals) and not client_has_rd_intent:
        return False, "Opportunity requires an R&D/pilot project not identified in the submitted project."
'''
s = rep(s, old, new, 'R&D negation logic')
p.write_text(s)

p = Path('backend/tests/test_v11_server.py')
t = p.read_text()
extra = '''\n\ndef test_explicit_not_rd_language_does_not_create_rd_intent():\n    grant = {\n        "title": "Emerging Chemical Technology Pre-pilot",\n        "summary": "Research and development, prototype demonstration, and pre-piloting of emerging chemical technologies.",\n        "tags": ["chemical", "manufacturing", "energy", "prototype"],\n        "sector": "energy / manufacturing efficiency",\n    }\n    payload = {\n        "projectTitle": "Plant Energy Equipment Upgrade",\n        "keywords": "energy efficiency, manufacturing, equipment",\n        "need": "Replace inefficient equipment to reduce energy use.",\n        "notes": "This is not an R&D, prototype, or pilot project; it is an operational equipment upgrade.",\n    }\n    ok, note = srv._relevance_compatible(grant, payload, "SMALL_BUSINESS")\n    assert ok is False\n    assert "R&D/pilot" in note\n'''
if 'test_explicit_not_rd_language_does_not_create_rd_intent' not in t:
    t += extra
p.write_text(t)
print('R&D negation guardrail patched')
