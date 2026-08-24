"""Discovery state from the VLM.

Every semantic judgement — task type, labels, slot fill, readiness, whether the
user actually answered — is made by the model. This module only validates and
clamps the returned JSON into the API shape.
"""

from __future__ import annotations

from typing import Any

DISCOVERY_SLOTS = (
    "use_case",
    "task_type",
    "objects_or_defects",
    "environment",
    "throughput",
)

# Required before Generate Config: use case + task + labels/target, plus at least
# one of environment / throughput so the plan is not guesswork.
REQUIRED_SLOTS = ("use_case", "task_type", "objects_or_defects")
CONTEXT_SLOTS = ("environment", "throughput")

VALID_TASKS = frozenset(
    {
        "classification",
        "multi_label",
        "regression",
        "object_localization",
        "object_detection",
    }
)

ASSESS_SYSTEM = """You assess a VisionDock discovery chat (computer vision project setup).
Return JSON only. Decide from the conversation itself — do not assume a fixed vocabulary of objects,
and judge every language the user may write in.

Slots to track (mark true ONLY from USER answers, not from assistant guesses alone):
- use_case: user explained what they want the system to do (a real goal, not a greeting or a probe)
- task_type: one of classification | multi_label | regression | object_localization | object_detection is clear
- objects_or_defects: classes/labels OR a numeric target name are known (any language, any domain)
- environment: where cameras/images come from is known enough
- throughput: how fast results are needed is known enough

detected_task must be exactly one of: classification | multi_label | regression | object_localization | object_detection.
Follow the USER's latest correction, not an earlier assistant guess.
- classification = single-label / image classification / object recognition / one folder per class
- multi_label ONLY if the user wants several tags on the SAME photo at once
- Several class names (e.g. kingfisher and carp) is still classification unless the user said one photo can have multiple tags
- If the user says they do NOT want multi-label / detection, do not pick that rejected type

user_answered_substantively: true only if at least one USER message carries real project content.
Greetings, one-word probes, filler, or bare confirmations are not substance, in any language.

user_confirmed_summary: true if the USER accepted an assistant summary that already names the task
type and the labels/target.

ready_for_config=true when ALL of these hold:
1) use_case is filled from a substantive USER answer
2) task_type is clear
3) labels/target (objects_or_defects) are known from the USER (or clearly confirmed by the USER)
4) environment OR throughput is filled from the USER
5) the USER has said something substantive, or confirmed a summary that lists task type and labels

If those hold, ready_for_config MUST be true even when the user said everything in a single message.
Do not wait for extra confirmation or extra turns, and do not keep it false just to ask a nicer question.
ready_for_config must stay consistent with slots: true only if use_case, task_type and
objects_or_defects are true and at least one of environment / throughput is true.

ready_for_config=false when the chat is still probing, or when the user has only greeted or probed
without describing the vision problem. Images alone are not enough — the user must state the goal
and labels (or target) in text.

CRITICAL: Do NOT set ready_for_config=true merely because the assistant wrote a summary or mentioned
the Generate Config button. Judge readiness from USER substance or explicit USER confirmation.
If the assistant wrapped up too early, set ready_for_config=false and list the missing_slots.

progress_percent: 0-100 based on how complete discovery is (slot fill, not message count).
classes: label strings the user (or the assistant with explicit user confirmation) named; empty if none yet.
Return classes exactly as the user named them — do not shorten, translate, or drop any.
target_name: string for regression, else null.
"""

RESOLVE_TASK_SYSTEM = """You choose exactly one VisionDock task_type from a discovery chat.
Return JSON only: {"task_type": "<one value>"}.

Allowed values:
- classification — one category per photo (single-label, image classification, object recognition). User uploads one folder per class.
- multi_label — the SAME photo can have several tags at once. Photos + CSV list.
- regression — numeric target per photo
- object_localization — one object per photo with a bounding box
- object_detection — several objects with bounding boxes

Rules:
- Follow the USER's latest correction. Earlier assistant guesses do not win.
- If the user rejects multi-label / detection and asks for single-label, classification, or recognition, return classification.
- Several class names alone is NOT multi_label.
- multi_label only when the user wants several tags on one photo at the same time.
- task_type must be exactly one of: classification, multi_label, regression, object_localization, object_detection.
"""


def is_internal_message(message: dict[str, Any] | Any) -> bool:
    """UI-injected prompts carry an explicit flag — never inspect their wording."""
    if isinstance(message, dict):
        return bool(message.get("internal"))
    return bool(getattr(message, "internal", False))


def latest_assistant_message(transcript: list[dict[str, Any]] | None) -> str:
    for m in reversed(transcript or []):
        if (m.get("role") or "").lower() == "assistant":
            return (m.get("content") or "").strip()
    return ""


def visible_user_turns(transcript: list[dict[str, Any]] | None) -> int:
    """Count real user messages (UI-injected prompts excluded)."""
    return sum(
        1
        for m in transcript or []
        if (m.get("role") or "").lower() == "user"
        and (m.get("content") or "").strip()
        and not is_internal_message(m)
    )


def slots_support_ready(slots: dict[str, Any], *, task: str | None) -> bool:
    """Consistency check on the model's own JSON — no text inspection."""
    if not task:
        return False
    if not all(bool(slots.get(s)) for s in REQUIRED_SLOTS):
        return False
    if not any(bool(slots.get(s)) for s in CONTEXT_SLOTS):
        return False
    return True


def _transcript_lines(transcript: list[dict[str, Any]] | None, extra_assistant: str = "") -> str:
    lines: list[str] = []
    for m in transcript or []:
        role = (m.get("role") or "").upper()
        content = (m.get("content") or "").strip()
        if role in ("USER", "ASSISTANT") and content and not is_internal_message(m):
            lines.append(f"{role}: {content}")
    wrap = (extra_assistant or "").strip()
    if wrap and (not lines or lines[-1] != f"ASSISTANT: {wrap}"):
        lines.append(f"ASSISTANT: {wrap}")
    return "\n".join(lines) if lines else "(empty)"


def resolve_task_type_with_llm(
    client: Any,
    *,
    model: str,
    transcript: list[dict[str, Any]] | None,
    token_kwargs: dict[str, int],
    trace_kwargs: dict | None = None,
) -> str | None:
    """Ask the VLM which task_type the user currently wants."""
    import json

    from schemas.project_spec import coerce_known_task_type

    conv = _transcript_lines(transcript)
    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": RESOLVE_TASK_SYSTEM},
            {
                "role": "user",
                "content": (
                    "Conversation:\n"
                    f"{conv}\n\n"
                    "Return JSON with key task_type only."
                ),
            },
        ],
        response_format={"type": "json_object"},
        **token_kwargs,
        **(trace_kwargs or {}),
    )
    raw_text = completion.choices[0].message.content or "{}"
    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, dict):
        return None
    return coerce_known_task_type(raw.get("task_type") or raw.get("detected_task"))


def empty_discovery(user_turn_count: int = 0) -> dict[str, Any]:
    slots = {s: False for s in DISCOVERY_SLOTS}
    return {
        "ready_for_config": False,
        "detected_task": None,
        "user_turn_count": user_turn_count,
        "slots": slots,
        "missing_slots": list(DISCOVERY_SLOTS),
        # Progress follows slots only — do not inflate from message count.
        "progress_percent": 0,
        "vlm_ready_signal": False,
        "suggested_action": "continue_chat",
        "needs_class_list": True,
        "extracted_labels": [],
        "regression_target": None,
    }


def normalize_discovery(raw: dict[str, Any] | None, user_turn_count: int) -> dict[str, Any]:
    """Clamp/fill an LLM discovery payload into the API shape."""
    base = empty_discovery(user_turn_count)
    if not isinstance(raw, dict):
        return base

    task = raw.get("detected_task") or raw.get("task_type")
    if isinstance(task, str):
        from schemas.project_spec import coerce_known_task_type

        task = coerce_known_task_type(task)
    else:
        task = None

    slots_in = raw.get("slots") if isinstance(raw.get("slots"), dict) else {}
    slots = {s: bool(slots_in.get(s, False)) for s in DISCOVERY_SLOTS}
    if task:
        slots["task_type"] = True

    labels_raw = raw.get("classes") or raw.get("extracted_labels") or raw.get("labels") or []
    labels: list[str] = []
    if isinstance(labels_raw, list):
        for item in labels_raw:
            if isinstance(item, str) and item.strip():
                labels.append(item.strip())
    if labels:
        slots["objects_or_defects"] = True

    target = raw.get("target_name") or raw.get("regression_target")
    if isinstance(target, str) and target.strip():
        target = target.strip()
        slots["objects_or_defects"] = True
    else:
        target = None

    # The model reports whether the user actually answered; we only enforce that
    # a chat with no user messages at all can never be ready.
    has_substance = bool(raw.get("user_answered_substantively"))
    confirmed = bool(raw.get("user_confirmed_summary"))
    ready = bool(raw.get("ready_for_config"))
    if user_turn_count < 1:
        ready = False
    if not (has_substance or confirmed):
        ready = False
    # Keep the payload self-consistent in both directions: ready needs the slots the
    # model itself reported, and every slot filled means ready.
    if ready and not slots_support_ready(slots, task=task):
        ready = False
    if (
        not ready
        and (has_substance or confirmed)
        and task
        and user_turn_count >= 1
        and all(slots.get(s) for s in DISCOVERY_SLOTS)
    ):
        ready = True

    try:
        progress = int(raw.get("progress_percent", 0))
    except (TypeError, ValueError):
        progress = 0
    progress = max(0, min(100, progress))
    if ready:
        progress = max(progress, 90)
    elif progress == 0:
        progress = int(100 * sum(1 for v in slots.values() if v) / len(DISCOVERY_SLOTS))

    needs_class = bool(raw.get("needs_class_list"))
    if task in ("classification", "multi_label", "object_detection", "object_localization"):
        needs_class = not bool(labels)
    elif task == "regression":
        needs_class = False

    missing = [s for s in DISCOVERY_SLOTS if not slots[s]]

    return {
        "ready_for_config": ready,
        "detected_task": task,
        "user_turn_count": user_turn_count,
        "slots": slots,
        "missing_slots": missing,
        "progress_percent": progress,
        "vlm_ready_signal": ready,
        "suggested_action": "generate_config" if ready else "continue_chat",
        "needs_class_list": needs_class,
        "extracted_labels": labels,
        "regression_target": target,
    }


def assess_discovery_with_llm(
    client: Any,
    *,
    model: str,
    transcript: list[dict[str, str]],
    assistant_reply: str,
    token_kwargs: dict[str, int],
    trace_kwargs: dict | None = None,
) -> dict[str, Any]:
    """Ask the chat model for structured discovery JSON (text-only, cheap follow-up)."""
    import json

    user_turns = visible_user_turns(transcript)
    wrap = (assistant_reply or "").strip() or latest_assistant_message(transcript)
    conv = _transcript_lines(transcript, wrap)

    if user_turns < 1:
        return empty_discovery(user_turns)

    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": ASSESS_SYSTEM},
            {
                "role": "user",
                "content": (
                    "Conversation:\n"
                    f"{conv}\n\n"
                    "Return JSON with keys: ready_for_config (bool), detected_task (string|null), "
                    "slots (object of booleans for use_case,task_type,objects_or_defects,environment,throughput), "
                    "missing_slots (string[]), progress_percent (int), needs_class_list (bool), "
                    "classes (string[]), target_name (string|null), "
                    "user_answered_substantively (bool), user_confirmed_summary (bool)."
                ),
            },
        ],
        response_format={"type": "json_object"},
        **token_kwargs,
        **(trace_kwargs or {}),
    )
    raw_text = completion.choices[0].message.content or "{}"
    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError:
        raw = None
    if not isinstance(raw, dict):
        return empty_discovery(user_turns)
    return normalize_discovery(raw, user_turns)
