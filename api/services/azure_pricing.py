"""Azure retail rates → VisionDock credits.

Rates are Sweden Central / Azure OpenAI list prices (approx, Jul 2026).
1 credit = $0.01 of mapped Azure cost (no platform markup by default).
Membership package prices are separate and set later via plans.
"""

from __future__ import annotations

import math
import os
from typing import Any

# 1 credit maps to this many USD of Azure cost.
CREDIT_USD = float(os.getenv("CREDIT_USD", "0.01"))
# Optional platform multiplier (>1 adds margin on top of Azure).
PLATFORM_MARKUP = float(os.getenv("CREDIT_PLATFORM_MARKUP", "1.0"))

# Linux PAYG $/hour — Sweden Central (azurespeed / CloudPrice, 2026).
VM_HOURLY_USD: dict[str, float] = {
    "Standard_NC4as_T4_v3": 0.558,
    "Standard_NC8as_T4_v3": 1.116,
    "Standard_NC16as_T4_v3": 2.232,
    "Standard_D2s_v3": 0.102,
    "Standard_D4s_v3": 0.204,
    "Standard_D8s_v3": 0.408,
    "Standard_DS3_v2": 0.224,
}

# Azure OpenAI gpt-4.1-mini (global standard list).
GPT41_MINI_INPUT_PER_1M = 0.40
GPT41_MINI_OUTPUT_PER_1M = 1.60

# Typical token budgets for product actions (prompt + tools + reply).
VLM_ANALYZE_TOKENS = {"input": 2500, "output": 800}
GENERATE_CONFIG_TOKENS = {"input": 6000, "output": 2500}
PIPELINE_TUNE_TOKENS = {"input": 4000, "output": 1200}

# Managed online endpoint instance $/hour — Sweden Central list (2026).
INFERENCE_VM_HOURLY_USD: dict[str, float] = {
    "Standard_F2s_v2": 0.099,
    "Standard_F4s_v2": 0.198,
    "Standard_F8s_v2": 0.396,
    "Standard_DS2_v2": 0.156,
    "Standard_DS3_v2": 0.312,
    "Standard_E2s_v3": 0.151,
    "Standard_NC4as_T4_v3": 0.578,
    "Standard_NC6s_v3": 3.823,
}
# Endpoint provisioning floor: container pull + node warm-up before it serves traffic.
INFERENCE_DEPLOY_BASE_MINUTES = float(os.getenv("INFERENCE_DEPLOY_BASE_MINUTES", "15"))
# Larger model artifacts add upload/registration/pull time on top of the floor.
INFERENCE_DEPLOY_MINUTES_PER_GB = float(os.getenv("INFERENCE_DEPLOY_MINUTES_PER_GB", "10"))
# A managed endpoint bills by the hour once it is up; charge this much uptime at deploy.
INFERENCE_ENDPOINT_BILLED_HOURS = float(os.getenv("INFERENCE_ENDPOINT_BILLED_HOURS", "2"))
# Model size assumed for the catalog estimate shown before a model exists.
INFERENCE_DEPLOY_REFERENCE_BYTES = 60 * 1024 * 1024
# Per predict on a warm CPU/GPU scoring node (includes egress/overhead floor).
INFERENCE_PREDICT_USD = 0.01

# Minimum billed training duration when Azure reports none (node spin-up floor).
TRAINING_MIN_SECONDS = 15 * 60
# Balance check before submit: reserve this many minutes of compute.
TRAINING_RESERVE_MINUTES = int(os.getenv("TRAINING_CREDIT_RESERVE_MINUTES", "30"))


def usd_to_credits(usd: float) -> int:
    """Convert Azure USD cost to whole credits (ceil, minimum 1 if usd > 0)."""
    if usd <= 0:
        return 0
    raw = (usd * PLATFORM_MARKUP) / max(CREDIT_USD, 1e-9)
    return max(1, int(math.ceil(raw)))


def llm_usd(*, input_tokens: int, output_tokens: int) -> float:
    return (input_tokens / 1_000_000) * GPT41_MINI_INPUT_PER_1M + (
        output_tokens / 1_000_000
    ) * GPT41_MINI_OUTPUT_PER_1M


def action_azure_usd(reason: str) -> float:
    """Fixed-action Azure cost estimates (training settle uses duration instead)."""
    if reason == "vlm_analyze":
        return llm_usd(
            input_tokens=VLM_ANALYZE_TOKENS["input"],
            output_tokens=VLM_ANALYZE_TOKENS["output"],
        )
    if reason == "generate_config":
        return llm_usd(
            input_tokens=GENERATE_CONFIG_TOKENS["input"],
            output_tokens=GENERATE_CONFIG_TOKENS["output"],
        )
    if reason == "pipeline_tune":
        return llm_usd(
            input_tokens=PIPELINE_TUNE_TOKENS["input"],
            output_tokens=PIPELINE_TUNE_TOKENS["output"],
        )
    if reason == "inference_deploy":
        return inference_deploy_usd()
    if reason == "inference_predict":
        return INFERENCE_PREDICT_USD
    if reason == "training_submit":
        return training_reserve_usd()
    return 0.0


def action_credits(reason: str) -> int:
    return usd_to_credits(action_azure_usd(reason))


def configured_vm_size() -> str:
    return (os.getenv("AZURE_ML_VM_SIZE") or "Standard_D4s_v3").strip()


def vm_hourly_usd(vm_size: str | None = None) -> float:
    size = (vm_size or configured_vm_size()).strip()
    if size in VM_HOURLY_USD:
        return VM_HOURLY_USD[size]
    # Heuristic: treat unknown NCas as T4-class, else CPU D4s.
    if "NC" in size.upper() or "ND" in size.upper() or "NV" in size.upper():
        return VM_HOURLY_USD["Standard_NC4as_T4_v3"]
    return VM_HOURLY_USD["Standard_D4s_v3"]


def configured_inference_vm() -> str:
    return (os.getenv("AZURE_ML_INFERENCE_VM") or "Standard_F2s_v2").strip()


def inference_vm_hourly_usd(vm_size: str | None = None) -> float:
    size = (vm_size or configured_inference_vm()).strip()
    if size in INFERENCE_VM_HOURLY_USD:
        return INFERENCE_VM_HOURLY_USD[size]
    return vm_hourly_usd(size)


def inference_deploy_minutes(model_bytes: int | None = None) -> float:
    gigabytes = max(float(model_bytes or INFERENCE_DEPLOY_REFERENCE_BYTES), 0.0) / (1024**3)
    return INFERENCE_DEPLOY_BASE_MINUTES + gigabytes * INFERENCE_DEPLOY_MINUTES_PER_GB


def inference_deploy_usd(
    *,
    model_bytes: int | None = None,
    vm_size: str | None = None,
) -> float:
    """Provisioning + initial endpoint uptime — scales with model size and endpoint VM."""
    hours = inference_deploy_minutes(model_bytes) / 60.0 + INFERENCE_ENDPOINT_BILLED_HOURS
    return hours * inference_vm_hourly_usd(vm_size)


def inference_deploy_credits(
    *,
    model_bytes: int | None = None,
    vm_size: str | None = None,
) -> tuple[int, float]:
    usd = inference_deploy_usd(model_bytes=model_bytes, vm_size=vm_size)
    return usd_to_credits(usd), usd


def training_reserve_usd(vm_size: str | None = None) -> float:
    hours = TRAINING_RESERVE_MINUTES / 60.0
    return hours * vm_hourly_usd(vm_size)


def training_compute_usd(
    duration_seconds: float | None,
    *,
    vm_size: str | None = None,
) -> float:
    seconds = float(duration_seconds or 0)
    if seconds <= 0:
        seconds = float(TRAINING_MIN_SECONDS)
    hours = seconds / 3600.0
    return hours * vm_hourly_usd(vm_size)


def training_compute_credits(
    duration_seconds: float | None,
    *,
    vm_size: str | None = None,
) -> tuple[int, float]:
    usd = training_compute_usd(duration_seconds, vm_size=vm_size)
    return usd_to_credits(usd), usd


def pricing_catalog() -> dict[str, Any]:
    """Public catalog for /api/credits/costs and billing UI."""
    costs = {
        "vlm_analyze": action_credits("vlm_analyze"),
        "generate_config": action_credits("generate_config"),
        "pipeline_tune": action_credits("pipeline_tune"),
        "training_submit": action_credits("training_submit"),
        "inference_deploy": action_credits("inference_deploy"),
        "inference_predict": action_credits("inference_predict"),
    }
    vm = configured_vm_size()
    inference_vm = configured_inference_vm()
    return {
        "costs": costs,
        "credit_usd": CREDIT_USD,
        "platform_markup": PLATFORM_MARKUP,
        "region_note": "Sweden Central Azure list rates (approx)",
        "vm_size": vm,
        "vm_hourly_usd": vm_hourly_usd(vm),
        "training_billing": "charged_on_job_end",
        "training_reserve_minutes": TRAINING_RESERVE_MINUTES,
        "inference_vm_size": inference_vm,
        "inference_vm_hourly_usd": inference_vm_hourly_usd(inference_vm),
        "inference_deploy_billing": "charged_on_deploy_from_model_size",
        "azure_rates": {
            "gpt_4_1_mini_input_per_1m_usd": GPT41_MINI_INPUT_PER_1M,
            "gpt_4_1_mini_output_per_1m_usd": GPT41_MINI_OUTPUT_PER_1M,
            "vm_hourly_usd": dict(VM_HOURLY_USD),
            "inference_vm_hourly_usd": dict(INFERENCE_VM_HOURLY_USD),
            "inference_predict_usd": INFERENCE_PREDICT_USD,
        },
        "cost_notes": {
            "vlm_analyze": "Azure OpenAI gpt-4.1-mini token estimate",
            "generate_config": "Azure OpenAI gpt-4.1-mini token estimate",
            "pipeline_tune": "Azure OpenAI gpt-4.1-mini token estimate",
            "training_submit": (
                f"Balance reserve (~{TRAINING_RESERVE_MINUTES} min of {vm}); "
                "actual debit = job duration × VM $/hr when the job ends"
            ),
            "inference_deploy": (
                f"Provisioning (~{INFERENCE_DEPLOY_BASE_MINUTES:.0f} min + "
                f"{INFERENCE_DEPLOY_MINUTES_PER_GB:.0f} min/GB of model) plus "
                f"{INFERENCE_ENDPOINT_BILLED_HOURS:g} h of {inference_vm} endpoint uptime; "
                "actual debit uses your model size"
            ),
            "inference_predict": "Per-request scoring estimate",
        },
    }
