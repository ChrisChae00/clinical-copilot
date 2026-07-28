import json
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent

API_URL = "http://localhost:8000/draft-action"
API_KEY = "api-key-placeholder"

payload = {
    "action": {
        "type": "referral",
        "title": "Referral letter",
        "description": "Refer patient to cardiology for chest pain workup.",
    },
    "context": "## patient info ##\n patient_name: Joe Mama\n age: 45 \ndiagnosis: Hypertension \nHistory: 2 weeks of intermittent chest pain on exertion.",
}

headers = {
    "Content-Type": "application/json",
    "X-API-Key": API_KEY,
}

response = requests.post(
    API_URL,
    headers=headers,
    json=payload,
    timeout=180,
)

print("Status:", response.status_code)

output_path = BASE_DIR / "draft_action_response.json"

try:
    response_json = response.json()
    print(json.dumps(response_json, indent=2))
    output_path.write_text(json.dumps(response_json, indent=2), encoding="utf-8")
except Exception:
    print(response.text)
    output_path.write_text(response.text, encoding="utf-8")
