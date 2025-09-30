# list_models.py
import os
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()  # reads .env in project root
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise SystemExit("GEMINI_API_KEY not found. Put it in .env like: GEMINI_API_KEY=your_key_here")

genai.configure(api_key=api_key)

print("Models that support generateContent:\n")
for m in genai.list_models():
    if "generateContent" in getattr(m, "supported_generation_methods", []):
        print(m.name)