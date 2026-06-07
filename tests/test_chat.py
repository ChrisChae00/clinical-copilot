import base64
import json
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent

API_URL = "http://localhost:8000/chat"
API_KEY = "api-key-placeholder"

html_path = BASE_DIR / "testpage1.html"
image_path = BASE_DIR / "test_report.png"

raw_html = html_path.read_text(encoding="utf-8")

image_b64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")

payload = {
    "prompt": "What is the patient's name? and what does his report say? and help me fill this form",
    "raw_html": raw_html,
    "images_b64": [image_b64],
}

headers = {
    "Content-Type": "application/json",
    "X-API-Key": API_KEY,
}

response = requests.post(API_URL, headers=headers, json=payload, timeout=180)

print("Status:", response.status_code)

# save to file for inspection
output_path = BASE_DIR / "response.json"
output_path.write_text(json.dumps(response.json(), indent=2), encoding="utf-8")
