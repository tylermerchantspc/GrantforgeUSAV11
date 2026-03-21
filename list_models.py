"""List available Google Generative Language models for a configured API key."""

from dotenv import load_dotenv
import google.generativeai as genai

from runtime_config import load_google_api_key

load_dotenv()
api_key = load_google_api_key()

genai.configure(api_key=api_key)

print("Models that support generateContent:\n")
for m in genai.list_models():
    if "generateContent" in getattr(m, "supported_generation_methods", []):
        print(m.name)
