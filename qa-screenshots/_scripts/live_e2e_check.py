"""End-to-end check against the deployed app: chat → readiness → generated spec.

Run: python3.14 live_e2e_check.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "api"))

import requests

BASE = os.getenv("VD_BASE", "https://visiondock-api-ataha.azurewebsites.net")
USER = os.getenv("VD_USER", "admin@visiondock.local")
PASSWORD = os.getenv("VD_PASSWORD") or sys.exit("set VD_PASSWORD")

UI_PROMPT = {
    "role": "user",
    "content": "The user uploaded sample photos for a vision project. Ask what they want to detect.",
    "internal": True,
}

POND_CHAT = [
    UI_PROMPT,
    {"role": "assistant", "content": "What should the model recognize in these photos?"},
    {
        "role": "user",
        "content": "Pond camera. I want to know whether a photo shows a kingfisher or a carp.",
    },
    {
        "role": "assistant",
        "content": "I suggest multi-label classification so a frame can be tagged kingfisher and carp.",
    },
    {
        "role": "user",
        "content": "I dont want multi-label classification, I want single-label classification",
    },
    {
        "role": "assistant",
        "content": "Understood — single-label image classification with kingfisher and carp. Photos come from the pond camera, reviewed daily?",
    },
    {"role": "user", "content": "yes, pond camera, I review the batch every evening"},
]

GREETING_CHAT = [
    UI_PROMPT,
    {"role": "assistant", "content": "Hi! What should we detect?"},
    {"role": "user", "content": "hello"},
]

s = requests.Session()
r = s.post(f"{BASE}/api/auth/login", json={"username": USER, "password": PASSWORD}, timeout=60)
r.raise_for_status()
print("login ok")

r = s.post(f"{BASE}/api/projects", json={"name": "manual-scan-e2e"}, timeout=60)
r.raise_for_status()
project_id = r.json().get("id") or r.json().get("project", {}).get("id")
print("project", project_id)

failures: list[str] = []


def analyze(messages: list[dict]) -> dict:
    resp = s.post(
        f"{BASE}/api/vlm/analyze",
        json={"messages": messages, "project_id": project_id},
        timeout=180,
    )
    resp.raise_for_status()
    return resp.json()


greeting = analyze(GREETING_CHAT)
print(f"greeting  ready={greeting['ready_for_config']} progress={greeting['discovery']['progress_percent']}")
if greeting["ready_for_config"]:
    failures.append("greeting-only chat unlocked Generate Config")

pond = analyze(POND_CHAT)
print(
    f"pond      ready={pond['ready_for_config']} task={pond['detected_task']} "
    f"labels={pond['discovery']['extracted_labels']}"
)
if not pond["ready_for_config"]:
    failures.append(f"pond chat stayed locked: missing={pond['discovery']['missing_slots']}")

resp = s.post(
    f"{BASE}/api/vlm/generate-config",
    json={"messages": POND_CHAT, "project_id": project_id},
    timeout=240,
)
if resp.status_code != 200:
    failures.append(f"generate-config failed: {resp.status_code} {resp.text[:300]}")
else:
    config = resp.json()["config"]
    classes = [c.lower() for c in config.get("classes") or []]
    print(f"config    task_type={config['task_type']} classes={config.get('classes')}")
    if config["task_type"] != "classification":
        failures.append(f"task_type={config['task_type']}, expected classification")
    for want in ("kingfisher", "carp"):
        if want not in classes:
            failures.append(f"class '{want}' missing from {config.get('classes')}")

print()
if failures:
    print("FAILURES:")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("live e2e passed")
