from google.cloud import firestore
db = firestore.Client()
doc = db.collection("grants_cache").document("education").get()
print("exists:", doc.exists)
if doc.exists:
    d = doc.to_dict()
    print("items_len:", len(d.get("items", [])))
    print("sample_title:", d["items"][0].get("title"))
