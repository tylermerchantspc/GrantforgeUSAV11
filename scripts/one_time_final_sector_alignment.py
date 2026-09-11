from pathlib import Path


def replace_once(text, old, new, label):
    n = text.count(old)
    if n != 1:
        raise SystemExit(f"{label}: expected 1 occurrence, found {n}")
    return text.replace(old, new, 1)

p = Path("backend/v11_server.py")
s = p.read_text()
old = '''    sector_rules = [
        (
            "energy / manufacturing efficiency",
'''
new = '''    sector_rules = [
        (
            "agriculture / rural development",
            [
                "agriculture",
                "agricultural",
                "farming",
                "farm operation",
                "ranching",
                "food systems",
                "agricultural science",
                "agricultural education",
                "rural development",
            ],
        ),
        (
            "energy / manufacturing efficiency",
'''
s = replace_once(s, old, new, "agriculture sector precedence")
s = replace_once(
    s,
    '        "refund_policy": "All sales final. No refunds.",',
    '        "refund_policy": "Final once customized generation begins; exceptions required by law or nondelivery.",',
    "checkout metadata refund policy",
)
p.write_text(s)

tp = Path("backend/tests/test_v11_server.py")
t = tp.read_text()
extra = '''\n\ndef test_agriculture_sector_precedes_generic_stem_or_workforce_terms():\n    kws = srv.normalized_keywords("STEM, agriculture, rural youth, agricultural science, engineering, careers")\n    assert srv.infer_client_sector(kws) == "agriculture / rural development"\n\ndef test_flat_price_remains_4999_after_sector_routing_changes():\n    assert srv.price_for("College / University / Research Institution", 50000000) == pytest.approx(49.99)\n'''
if "test_agriculture_sector_precedes_generic_stem_or_workforce_terms" not in t:
    t += extra
tp.write_text(t)
print("final sector alignment patched")
