from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from dotenv import load_dotenv
import google.generativeai as genai
from google.cloud import firestore
import uuid
from datetime import datetime

# -------------------------------
# Load environment variables
# -------------------------------
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY not set in .env")

genai.configure(api_key=GEMINI_API_KEY)

# Use the working model name from your list_models.py output
MODEL_NAME = "models/gemini-2.0-flash"
model = genai.GenerativeModel(MODEL_NAME)

# Firestore client (Cloud Run will use its service account)
db = firestore.Client()  # Project auto-detected via env on Cloud Run

# -------------------------------
# Flask setup
# -------------------------------
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# -------------------------------
# Health Check
# -------------------------------
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "ok": True,
        "service": "grantforgeusa-api",
        "project": os.environ.get("GOOGLE_CLOUD_PROJECT", "unknown"),
        "ts": datetime.utcnow().isoformat() + "Z"
    })

# -------------------------------
# Find Grants (demo only)
# -------------------------------
@app.route("/find-grants", methods=["POST"])
def find_grants():
    data = request.get_json(silent=True) or {}
    keywords = data.get("keywords", "")
    org = data.get("organization", "Unknown Org")

    dummy = [
        {"id": "g1", "title": "STEM Education Grant", "agency": "Dept. of Education"},
        {"id": "g2", "title": "Rural Development Grant", "agency": "USDA"},
        {"id": "g3", "title": "Community Health Grant", "agency": "HHS"}
    ]
    return jsonify({"ok": True, "organization": org, "keywords": keywords, "results": dummy})

# -------------------------------
# AI Draft Generator (persists to Firestore)
# -------------------------------
@app.route("/ai-draft", methods=["POST"])
def ai_draft():
    try:
        data = request.get_json(silent=True) or {}
        org = (data.get("organization") or "Unknown Organization").strip()
        keywords = (data.get("keywords") or "").strip()
        grant = data.get("grant") or {}

        grant_title = (grant.get("title") or "Untitled Grant").strip()
        grant_agency = (grant.get("agency") or "Unknown Agency").strip()

        prompt = f"""
Write a professional 500–700 word grant proposal draft for the organization "{org}".
Target Grant: "{grant_title}" from {grant_agency}.
Emphasize keywords/context: {keywords}.

Include:
- brief problem statement tied to the context
- goals and measurable outcomes
- planned activities/work plan
- evaluation approach
- budget overview and sustainability

Tone: professional, clear, persuasive. Use short paragraphs, avoid long bullet lists unless necessary.
"""

        response = model.generate_content(prompt)
        ai_text = (response.text or "").strip()
        if not ai_text:
            return jsonify({"ok": False, "error": "Empty response from model"}), 502

        draft_id = str(uuid.uuid4())
        draft_doc = {
            "id": draft_id,
            "organization": org,
            "keywords": keywords,
            "grant": {"title": grant_title, "agency": grant_agency},
            "content": ai_text,
            "model": MODEL_NAME,
            "created": datetime.utcnow().isoformat() + "Z",
        }

        # Save to Firestore: drafts/{id}
        db.collection("drafts").document(draft_id).set(draft_doc)

        return jsonify({"ok": True, "draft": draft_doc})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# -------------------------------
# Get Draft by ID (reads from Firestore)
# -------------------------------
@app.route("/draft/<draft_id>", methods=["GET"])
def get_draft(draft_id):
    try:
        doc = db.collection("drafts").document(draft_id).get()
        if not doc.exists:
            return jsonify({"ok": False, "error": "Draft not found"}), 404
        return jsonify({"ok": True, "draft": doc.to_dict()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500