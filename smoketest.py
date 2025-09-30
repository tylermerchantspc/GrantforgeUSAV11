from google.cloud import firestore

def main():
    db = firestore.Client()  # uses your Application Default Credentials
    doc = db.collection('smoketests').document('hello')
    doc.set({'status': 'it works!'})
    snap = doc.get()
    print('Read back:', snap.to_dict())

if __name__ == '__main__':
    main()
