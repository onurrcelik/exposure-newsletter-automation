import os
import json
import firebase_admin
from firebase_admin import credentials, firestore

_db = None


def get_db():
    global _db
    if _db is None:
        if not firebase_admin._apps:
            creds_json = os.environ.get("FIREBASE_CREDENTIALS")
            if creds_json:
                cred = credentials.Certificate(json.loads(creds_json))
            else:
                # Local fallback: place serviceAccountKey.json in project root
                cred = credentials.Certificate("serviceAccountKey.json")
            firebase_admin.initialize_app(cred)
        _db = firestore.client()
    return _db


def editions_col():
    return get_db().collection("editions")
