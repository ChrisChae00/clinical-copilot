import base64
import json
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent

API_URL = "http://localhost:8000/autofill"
API_KEY = "api-key-placeholder"

image_path = BASE_DIR / "test_report.png"

image_b64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")

payload = {
    "prompt": "Fill the form using the patient report. If possible, fill reason for visit as severe headache.",
    "context": "## patient info ##\n patient_name: Joe Mama\n age: 45 \ndiagnosis: Hypertension \n## chat history ## \nuser: Please help fill the form from the report.",
    "images_b64": [image_b64],
    "fields": [
        {
            "id": "patient_name",
            "label": "Patient Name",
            "type": "text",
        },
        {
            "id": "age",
            "label": "Age",
            "type": "number",
        },
        {
            "id": "reason_for_visit",
            "label": "Reason for Visit",
            "type": "textarea",
        },
        {
            "id": "diagnosis",
            "label": "Diagnosis",
            "type": "text",
        },
        {
            "id": "visit_type",
            "label": "Visit Type",
            "type": "select",
            "options": [
                {
                    "value": "routine",
                    "label": "Routine Visit",
                },
                {
                    "value": "urgent",
                    "label": "Urgent Visit",
                },
                {
                    "value": "follow_up",
                    "label": "Follow-up",
                },
            ],
        },
        {
            "id": "has_headache",
            "label": "Headache",
            "type": "checkbox",
        },
        {
            "id": "symptoms",
            "label": "Symptoms",
            "type": "checkbox_group",
            "options": [
                {
                    "value": "headache",
                    "label": "Headache",
                },
                {
                    "value": "nausea",
                    "label": "Nausea",
                },
                {
                    "value": "dizziness",
                    "label": "Dizziness",
                },
            ],
        },
    ],
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

output_path = BASE_DIR / "autofill_response.json"

try:
    response_json = response.json()
    print(json.dumps(response_json, indent=2))
    output_path.write_text(json.dumps(response_json, indent=2), encoding="utf-8")
except Exception:
    print(response.text)
    output_path.write_text(response.text, encoding="utf-8")
