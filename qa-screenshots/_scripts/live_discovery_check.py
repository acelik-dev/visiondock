"""Live VLM check: task type + readiness must come from the model, not keywords.

Run:  python3.14 live_discovery_check.py
Reads VLM_* from the Azure App Service settings (see DEPLOYMENT.md) or the env.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "api"))

for key in [k for k in os.environ if k.startswith("LANGFUSE_")]:
    os.environ.pop(key, None)


def _load_app_settings() -> None:
    if os.getenv("VLM_API_KEY"):
        return
    out = subprocess.run(
        [
            "az", "webapp", "config", "appsettings", "list",
            "-g", os.getenv("AZ_RG", "visiondock-rg"),
            "-n", os.getenv("AZ_APP", "visiondock-api-ataha"),
            "-o", "json",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    for item in json.loads(out):
        name = item.get("name") or ""
        if name.startswith("VLM_"):
            os.environ[name] = item.get("value") or ""


_load_app_settings()

from discovery import assess_discovery_with_llm, resolve_task_type_with_llm  # noqa: E402
from services.vlm_client import get_vlm_client, vlm_json_kwargs, vlm_model  # noqa: E402

client = get_vlm_client()
if client is None:
    sys.exit("VLM_API_KEY missing")

UI_PROMPT = {
    "role": "user",
    "content": "The user uploaded sample photos for a vision project. Ask what they want to detect.",
    "internal": True,
}

CASES: list[dict] = [
    {
        "name": "single-label correction (pond wildlife)",
        "transcript": [
            UI_PROMPT,
            {"role": "assistant", "content": "What should the model recognize in these photos?"},
            {"role": "user", "content": "I have a pond camera. I want to know if the photo shows a kingfisher or a carp."},
            {"role": "assistant", "content": "I suggest multi-label classification so a frame can be tagged kingfisher and carp."},
            {"role": "user", "content": "I dont want multi-label classification, I want single-label classification"},
            {"role": "assistant", "content": "Understood — single-label image classification with kingfisher and carp. Photos come from the pond camera and you review them daily, right?"},
            {"role": "user", "content": "yes, pond camera, I review the batch every evening"},
        ],
        "expect_task": "classification",
        "expect_ready": True,
    },
    {
        "name": "turkish single-label",
        "transcript": [
            UI_PROMPT,
            {"role": "assistant", "content": "Ne tespit etmek istiyorsunuz?"},
            {"role": "user", "content": "Fabrika hattındaki metal parçaların fotoğrafı sağlam mı çizik mi onu ayırmak istiyorum. Tepeden bakan kamera var, anlık uyarı lazım."},
        ],
        "expect_task": "classification",
        "expect_ready": True,
    },
    {
        "name": "genuine multi-label",
        "transcript": [
            UI_PROMPT,
            {"role": "assistant", "content": "What should we tag?"},
            {"role": "user", "content": "One drone photo can contain solar panel damage AND dirt AND cracks at the same time; I need every tag that applies. Drone flies weekly, results reviewed in batch."},
        ],
        "expect_task": "multi_label",
        "expect_ready": True,
    },
    {
        "name": "greeting only stays locked",
        "transcript": [
            UI_PROMPT,
            {"role": "assistant", "content": "Hi! What should we detect?"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "Here's what I suggest: image classification. You can use the Generate Config button."},
        ],
        "expect_task": None,
        "expect_ready": False,
    },
    {
        "name": "turkish greeting only stays locked",
        "transcript": [
            UI_PROMPT,
            {"role": "assistant", "content": "Merhaba! Ne tespit edelim?"},
            {"role": "user", "content": "selam"},
            {"role": "assistant", "content": "Önerim: görüntü sınıflandırma. Generate Config'e basabilirsiniz."},
        ],
        "expect_task": None,
        "expect_ready": False,
    },
    {
        "name": "labels that old filters would have dropped",
        "transcript": [
            UI_PROMPT,
            {"role": "assistant", "content": "What are the categories?"},
            {"role": "user", "content": "Classes: drone, bird, aerial camera platform. Photos come from a rooftop camera, I check results once a day."},
        ],
        "expect_task": "classification",
        "expect_ready": True,
        "expect_labels": ["drone", "bird"],
    },
]

failures: list[str] = []
for case in CASES:
    transcript = case["transcript"]
    reply = transcript[-1]["content"] if transcript[-1]["role"] == "assistant" else ""
    discovery = assess_discovery_with_llm(
        client,
        model=vlm_model(),
        transcript=transcript,
        assistant_reply=reply,
        token_kwargs=vlm_json_kwargs(2500),
    )
    task = resolve_task_type_with_llm(
        client,
        model=vlm_model(),
        transcript=transcript,
        token_kwargs=vlm_json_kwargs(1200),
    )
    ok = True
    if case["expect_ready"] != discovery["ready_for_config"]:
        ok = False
        failures.append(f"{case['name']}: ready={discovery['ready_for_config']} expected {case['expect_ready']}")
    if case["expect_task"] and task != case["expect_task"]:
        ok = False
        failures.append(f"{case['name']}: task={task} expected {case['expect_task']}")
    for want in case.get("expect_labels", []):
        if not any(want.lower() == str(l).lower() for l in discovery["extracted_labels"]):
            ok = False
            failures.append(f"{case['name']}: label '{want}' missing from {discovery['extracted_labels']}")
    print(
        f"[{'PASS' if ok else 'FAIL'}] {case['name']}\n"
        f"       task={task} ready={discovery['ready_for_config']} "
        f"progress={discovery['progress_percent']} labels={discovery['extracted_labels']}"
    )

print()
if failures:
    print("FAILURES:")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("all live discovery checks passed")
