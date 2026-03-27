import urllib.request
import os
import json
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
try:
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode())
        
    with open("available_models.txt", "w", encoding="utf-8") as f:
        for m in data.get("models", []):
            if "generateContent" in m.get("supportedGenerationMethods", []):
                f.write(m["name"] + "\n")
    print("Successfully wrote available models to available_models.txt")
except Exception as e:
    with open("available_models.txt", "w", encoding="utf-8") as f:
        f.write(str(e))
    print("Failed to get models")
