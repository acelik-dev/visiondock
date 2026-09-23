from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Any, List, Optional
import logging
import os
from sqlalchemy.orm import Session

from discovery import (
    assess_discovery_with_llm,
    empty_discovery,
    resolve_task_type_with_llm,
    visible_user_turns,
)
from db.database import get_db
from routers import admin as admin_router
from routers import auth as auth_router
from routers import credits as credits_router
from routers import inference as inference_router
from routers import marketplace as marketplace_router
from routers import projects as projects_router
from routers import skills as skills_router
from routers import training as training_router
from schemas.project_spec import (
    ProjectSpec,
    apply_resolved_task_type,
    parse_project_spec,
)
from services.credits import check_from_request, debit_from_request
from services.project_access import require_project_access, session_user
from services.project_store import ProjectStore
from services.vlm_client import (
    ensure_langfuse_client,
    flush_langfuse,
    get_vlm_client,
    langfuse_enabled,
    trace_user_id,
    vlm_json_kwargs,
    vlm_model,
    vlm_token_kwargs,
    vlm_trace_kwargs,
)
from session_auth import auth_enabled, install_session_auth

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)
logger = logging.getLogger("visiondock")


def _load_local_env() -> None:
    """Load api/.env into os.environ if present (does not override existing vars)."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val


_load_local_env()

if auth_enabled():
    logger.info("Session login enabled")

@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """Warm Azure ML client in background so first training submit is not blocked."""
    import threading

    def _warm_aml() -> None:
        try:
            from routers.training import _use_mock
            from services.azure_ml_service import get_ml_service

            if not _use_mock():
                get_ml_service()
                logger.info("Azure ML client warmed up")
        except Exception as exc:
            logger.debug("AML warmup skipped: %s", exc)

    threading.Thread(target=_warm_aml, name="aml-warmup", daemon=True).start()

    def _warm_catalog() -> None:
        try:
            from services.marketplace_store import get_marketplace_store

            get_marketplace_store().get_catalog()
            logger.info("Marketplace catalog cached")
        except Exception as exc:
            logger.debug("Catalog warmup skipped: %s", exc)

    threading.Thread(target=_warm_catalog, name="catalog-warmup", daemon=True).start()

    try:
        from db.database import init_db
        from services.wipe_users import maybe_wipe_users_on_startup

        init_db()
        logger.info("Database initialized")
        maybe_wipe_users_on_startup()
        if langfuse_enabled():
            # Seed singleton with flush_at=1 before any VLM call so the OpenAI
            # wrapper reuses an eager-flush client (first get() wins).
            ensure_langfuse_client()
            logger.info("Langfuse observability active")
    except Exception as exc:
        logger.warning("Database init skipped: %s", exc)

    yield

    flush_langfuse()


app = FastAPI(title="VisionDock AI API", lifespan=_lifespan)

def _cors_origins() -> list[str]:
    raw = os.getenv("CORS_ALLOW_ORIGINS", "")
    if raw.strip():
        return [o.strip() for o in raw.split(",") if o.strip()]
    return [
        "https://visiondock-api.azurewebsites.net",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
install_session_auth(app)
app.include_router(auth_router.router)
app.include_router(credits_router.router)
app.include_router(projects_router.router)
app.include_router(training_router.router)
app.include_router(inference_router.router)
app.include_router(marketplace_router.router)
app.include_router(skills_router.router)
app.include_router(admin_router.router)

_project_store = ProjectStore()

if not os.getenv("VLM_API_KEY"):
    logger.warning("VLM_API_KEY not set — analysis endpoints return 503")


class ChatMessage(BaseModel):
    role: str
    content: str
    # UI-injected discovery prompt; flagged so no code has to recognize its wording.
    internal: bool = False


def _transcript_dicts(messages: List[ChatMessage]) -> list[dict[str, Any]]:
    return [
        {"role": m.role, "content": m.content, "internal": m.internal}
        for m in messages
        if m.content.strip()
    ]


def _completion_text(completion: Any) -> str:
    """Extract assistant text; Azure sometimes returns None content with a refusal."""
    if not completion or not getattr(completion, "choices", None):
        return ""
    message = completion.choices[0].message
    content = getattr(message, "content", None)
    if isinstance(content, str) and content.strip():
        return content
    refusal = getattr(message, "refusal", None)
    if isinstance(refusal, str) and refusal.strip():
        return refusal
    # Some SDKs return multipart content blocks.
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
            else:
                text = getattr(block, "text", None)
                if text:
                    parts.append(str(text))
        return "\n".join(p for p in parts if p.strip())
    return ""


class VLMRequest(BaseModel):
    messages: List[ChatMessage]
    images: Optional[List[str]] = None
    project_id: Optional[str] = None


class GenerateConfigRequest(VLMRequest):
    force: bool = False


def _build_openai_messages(request: VLMRequest) -> list:
    """Full text history; images only on the last user message (vision)."""
    history = [m for m in request.messages if m.role in ("user", "assistant") and m.content.strip()]
    if not history:
        history = [ChatMessage(role="user", content="Analyze these images and help me define my vision task.")]

    user_count = sum(1 for m in history if m.role == "user")

    system = """You are a friendly Vision AI guide for factory, safety, and quality teams. Most users are not engineers.

VisionDock is NOT a labeling tool. Users bring pre-labeled datasets. Your job is to identify the task type and expected data format.

Supported task types:
1) Image classification (also called object recognition) — one category per image; user uploads photos into one folder per class
2) Multi-label classification — multiple tags on the SAME photo; photos + CSV list
3) Regression — numeric target per image (CSV with image,target)
4) Object localization — one object per image with bounding box (YOLO/COCO/VOC ZIP)
5) Object detection — multiple objects with bounding boxes (YOLO/COCO/VOC ZIP)

Follow the USER's latest correction. Single-label / image classification / object recognition = image classification
(one folder per class). Multi-label only when the user wants several tags on the SAME photo.
If they reject multi-label or detection, do not pick the rejected type. Several class names alone is not multi-label.

Collect, in plain language (any language the user uses):
- what they want the system to do
- which task type fits
- class/label names OR numeric target (any domain — do not assume a fixed word list)
- where images/cameras come from
- how fast they need answers

Read the full conversation and do not repeat questions they already answered.

Style:
- Short, clear sentences. No acronyms unless explained.
- Do not mention hyperparameters, preprocessing pipelines, or export formats.
- Never suggest annotating, labeling, or drawing boxes inside VisionDock.
- Sound like a helpful consultant.

Flow:
1) First reply: Briefly describe what you see. Suggest the most likely task type and ask up to three simple questions about labels/targets, camera location, and speed needs.
2) Later replies: Confirm task type and collect missing answers. Keep asking until the USER has substantively answered your questions.
3) Do not write "ready for configuration" or "ready to generate" — the app enables Generate Config automatically from your assessment.
4) If the user agrees with your summary, treat details as confirmed and give the wrap-up.

Saturation rule (CRITICAL):
- Give a wrap-up and mention the Generate Config button ONLY when the USER has largely answered your questions:
  use case / goal, task type, class labels OR numeric target, and camera/environment OR speed needs.
- Greetings, "hello", "test", "ok", "yes", or other one-word fillers are NOT enough — keep asking.
- Images alone are NOT enough; the user must confirm the goal and labels/target in text.
- If answers are still thin, ask the next missing question. Do NOT wrap up early.

When giving a wrap-up, start with "Here's what I suggest:" and name the task type once using the exact product names above
(e.g. "image classification" for object recognition, "object detection" only when bounding boxes are needed).
List EVERY class/label the user named — never drop labels or reinterpret them as attributes/flags.
Tell them they can use the Generate Config button. Do not ask new questions in that message.
"""
    if user_count == 1:
        system += (
            "\nThis is the first reply after images or the first user message. "
            "Help identify the best vision task type. Ask clarifying questions. "
            "Do NOT mention Generate Config yet. "
            "Users bring pre-labeled datasets — never suggest annotating inside VisionDock."
        )

    out: list = [{"role": "system", "content": system.strip()}]

    for i, m in enumerate(history):
        is_last = i == len(history) - 1
        if m.role == "assistant":
            out.append({"role": "assistant", "content": m.content})
        else:
            if is_last and request.images:
                parts: list = [{"type": "text", "text": m.content}]
                for img_base64 in _prepare_vlm_images(request.images):
                    parts.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": img_base64, "detail": "low"},
                        }
                    )
                out.append({"role": "user", "content": parts})
            else:
                out.append({"role": "user", "content": m.content})
    return out


def _friendly_vlm_error(exc: Exception) -> HTTPException:
    """Map Azure OpenAI failures to short user-facing messages."""
    msg = str(exc).lower()
    if "rate_limit" in msg or "429" in msg or "too many requests" in msg:
        return HTTPException(
            status_code=429,
            detail=(
                "The vision assistant is busy (rate limit). "
                "Wait a few seconds and try again — or send a short text message without re-uploading photos."
            ),
        )
    if (
        "content_filter" in msg
        or "content management policy" in msg
        or "responsibleaipolicyviolation" in msg
        or "jailbreak" in msg
    ):
        return HTTPException(
            status_code=422,
            detail=(
                "Azure content safety blocked this analysis. "
                "Please try sending a short text message in the chat describing your goal "
                "(for example: monitor helmets and cones on a construction site), then send again."
            ),
        )
    logger.exception("VLM request failed: %s", exc)
    return HTTPException(
        status_code=503,
        detail="Vision assistant is temporarily unavailable. Please try again in a moment.",
    )


def _prepare_vlm_images(images: list[str] | None, limit: int = 2) -> list[str]:
    """Cap and keep only reasonably small data-URL / http images."""
    if not images:
        return []
    out: list[str] = []
    for img in images:
        if not isinstance(img, str):
            continue
        s = img.strip()
        if not s.startswith(("data:image/", "http://", "https://")):
            continue
        # Huge base64 payloads burn free-tier vision quota and trip 429/503.
        if s.startswith("data:") and len(s) > 280_000:
            continue
        out.append(s)
        if len(out) >= limit:
            break
    return out


def _images_from_project_samples(project_id: str, limit: int = 2) -> list[str]:
    """Load a couple of stored samples as data URLs (skip oversized files)."""
    import base64

    out: list[str] = []
    try:
        for sample_id in _project_store.list_samples(project_id)[:8]:
            row = _project_store.read_sample(project_id, sample_id)
            if not row:
                continue
            data, ctype = row
            # Skip multi-MB originals; free-tier vision cannot afford them.
            if len(data) > 450_000:
                continue
            b64 = base64.b64encode(data).decode("ascii")
            out.append(f"data:{ctype};base64,{b64}")
            if len(out) >= limit:
                break
    except Exception:
        logger.exception("Failed loading project samples for VLM")
    return out


def _resolve_vlm_images(request: VLMRequest, *, allow_images: bool) -> list[str]:
    if not allow_images:
        return []
    if request.project_id:
        from_store = _images_from_project_samples(request.project_id, limit=2)
        if from_store:
            return from_store
    return _prepare_vlm_images(request.images, limit=2)


def _is_retryable_vision_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(
        token in msg
        for token in (
            "rate_limit",
            "429",
            "too many requests",
            "timeout",
            "timed out",
            "vision",
            "image",
            "invalid_image",
            "max_tokens",
            "unsupported",
        )
    )


STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


@app.get("/api/health")
def health():
    from storage.blob_store import get_blob_store

    store = get_blob_store()
    payload = {"status": "VisionDock AI API is running", "storage_backend": store.backend}
    if langfuse_enabled():
        payload["langfuse"] = "enabled"
    return payload


@app.post("/api/vlm/analyze")
async def analyze_with_vlm(
    body: VLMRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    if body.project_id:
        user = session_user(request)
        require_project_access(_project_store.get_meta(body.project_id), body.project_id, user)
    try:
        client = get_vlm_client()
        if client is None:
            raise HTTPException(
                status_code=503,
                detail="VLM_API_KEY is not configured. Set it in the environment to enable analysis.",
            )

        check_from_request(request, db, "vlm_analyze")

        # Only attach vision on early discovery turns (saves quota on follow-ups).
        user_turns = sum(1 for m in body.messages if m.role == "user" and (m.content or "").strip())
        allow_images = user_turns <= 1
        images = _resolve_vlm_images(body, allow_images=allow_images)
        effective = body.model_copy(update={"images": images or None})
        messages = _build_openai_messages(effective)
        uid = trace_user_id(request)
        trace = vlm_trace_kwargs(
            name="vlm-analyze",
            project_id=body.project_id,
            user_id=uid,
            tags=["vlm", "discovery"],
            metadata={"user_turns": user_turns, "has_images": bool(images)},
        )

        try:
            completion = client.chat.completions.create(
                model=vlm_model(),
                messages=messages,
                **vlm_token_kwargs(2500 if images else 1500),
                **trace,
            )
        except Exception as vision_exc:
            if images and _is_retryable_vision_error(vision_exc):
                logger.warning("Vision call failed (%s); retrying text-only", vision_exc)
                effective = body.model_copy(update={"images": None})
                messages = _build_openai_messages(effective)
                completion = client.chat.completions.create(
                    model=vlm_model(),
                    messages=messages,
                    **vlm_token_kwargs(1500),
                    **trace,
                )
            else:
                raise

        reply = _completion_text(completion)
        if not reply.strip():
            # Empty content happens with filters / token budget — retry once text-only.
            logger.warning(
                "Empty VLM reply (finish=%s); retrying with clarifying nudge",
                getattr(completion.choices[0], "finish_reason", None) if completion.choices else None,
            )
            nudge = list(messages) + [
                {
                    "role": "user",
                    "content": (
                        "Your previous reply was empty. Answer the user's last message in plain "
                        "English with 2–4 short sentences and a concrete next question. "
                        "Do not say ready for configuration."
                    ),
                }
            ]
            completion = client.chat.completions.create(
                model=vlm_model(),
                messages=nudge,
                **vlm_token_kwargs(1500),
                **trace,
            )
            reply = _completion_text(completion)

        transcript = _transcript_dicts(body.messages)
        try:
            discovery = assess_discovery_with_llm(
                client,
                model=vlm_model(),
                transcript=transcript,
                assistant_reply=reply,
                token_kwargs=vlm_json_kwargs(2500),
                trace_kwargs=vlm_trace_kwargs(
                    name="vlm-discovery-assess",
                    project_id=body.project_id,
                    user_id=uid,
                    tags=["vlm", "discovery"],
                ),
            )
        except Exception:
            logger.exception("Discovery assessment failed; leaving Generate Config locked")
            discovery = empty_discovery(visible_user_turns(transcript))

        response_text = reply.strip()

        if not response_text:
            raise HTTPException(
                status_code=502,
                detail="Vision assistant returned an empty reply. Please send your message again.",
            )

        # Charge only after a live non-empty VLM response is produced.
        credits = debit_from_request(
            request,
            db,
            "vlm_analyze",
            ref=body.project_id,
            note="VLM discovery chat",
        )

        return {
            "success": True,
            "response": response_text,
            "ready_for_config": discovery["ready_for_config"],
            "detected_task": discovery["detected_task"],
            "discovery": discovery,
            "credits": credits,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise _friendly_vlm_error(e)
    finally:
        flush_langfuse()


def _conversation_transcript(messages: List[ChatMessage]) -> str:
    lines: List[str] = []
    for m in messages:
        if m.role in ("user", "assistant") and m.content.strip() and not m.internal:
            lines.append(f"{m.role.upper()}: {m.content.strip()}")
    return "\n".join(lines) if lines else "(no transcript)"


def _dedupe_labels(names: list[str]) -> list[str]:
    """Trim + case-insensitive dedupe. No filtering — the model owns the label set."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in names:
        cleaned = str(raw).strip()
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
    return out


def _merge_spec_classes(spec: ProjectSpec, extra: list[str]) -> ProjectSpec:
    """Union of config classes and the labels the assess model already extracted."""
    merged = _dedupe_labels([*(spec.classes or []), *extra])
    if merged == list(spec.classes or []):
        return spec
    return spec.model_copy(update={"classes": merged})


@app.post("/api/vlm/generate-config")
async def generate_config(
    body: GenerateConfigRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Generate structured JSON configuration from chat context"""
    if body.project_id:
        user = session_user(request)
        require_project_access(_project_store.get_meta(body.project_id), body.project_id, user)
    try:
        client = get_vlm_client()
        if client is None:
            raise HTTPException(
                status_code=503,
                detail="VLM_API_KEY is not configured. Set it in the environment to enable config generation.",
            )

        transcript = _transcript_dicts(body.messages)
        uid = trace_user_id(request)
        last_assistant = ""
        for m in reversed(transcript):
            if m.get("role") == "assistant" and (m.get("content") or "").strip():
                last_assistant = m["content"]
                break
        try:
            discovery = assess_discovery_with_llm(
                client,
                model=vlm_model(),
                transcript=transcript,
                assistant_reply=last_assistant,
                token_kwargs=vlm_json_kwargs(2500),
                trace_kwargs=vlm_trace_kwargs(
                    name="vlm-generate-config-assess",
                    project_id=body.project_id,
                    user_id=uid,
                    tags=["vlm", "generate-config"],
                ),
            )
        except Exception:
            logger.exception("Discovery assessment failed on generate-config")
            discovery = empty_discovery(visible_user_turns(transcript))
        if not body.force and not discovery["ready_for_config"]:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Discovery incomplete — continue the chat until the assistant confirms readiness.",
                    "missing_slots": discovery["missing_slots"],
                    "progress_percent": discovery["progress_percent"],
                },
            )

        check_from_request(request, db, "generate_config")

        import json

        config_prompt = """Based on the conversation and images, generate a complete training project JSON for VisionDock.

The user is NOT technical — choose all training/preprocessing/postprocessing/hardware values yourself from the dialogue (sensible defaults for industrial vision). Do not leave placeholders.

VisionDock is NOT a labeling tool. Users upload pre-labeled data. Pick exactly ONE task_type from:
- classification — one category per image; per-class folders. Use this for "object recognition" / "recognition".
- multi_label — multiple tags on the SAME photo; images + CSV/JSON manifest. Only if the user said a photo can have several tags at once.
- regression — numeric target per image; images + CSV (image,target)
- object_localization — one object per image with bbox; annotated YOLO/COCO/VOC ZIP
- object_detection — multiple objects with bboxes; annotated YOLO/COCO/VOC ZIP

Follow the USER's latest correction. Single-label / "not multi-label" / object recognition / classification → classification.
Having several class names does NOT mean multi_label.

Return ONLY a valid JSON object with this structure:
{
  "project_name": "string",
  "task_type": "classification|multi_label|regression|object_localization|object_detection",
  "recommended_model": "string",
  "description": "brief description",
  "classes": ["class1", "class2", ...],
  "target_name": "string (regression only, e.g. defect_score)",
  "target_unit": "string (regression only, e.g. percent)",
  "estimated_dataset_size": "e.g., 1000-5000 images",
  "training_config": { "epochs": 50, "batch_size": 16, "image_size": "224x224", ... },
  "preprocessing": { "resize": "224x224", "grayscale": false, ... },
  "postprocessing": { "confidence_threshold": 0.5, "export_format": ["onnx"], ... },
  "enabled_skills": ["pre.resize", "pre.normalize", "..."],
  "hardware_requirements": { ... }
}

IMPORTANT field formats:
- preprocessing.resize MUST be a string like "224x224" or "640x640" (NOT an object)
- preprocessing.normalize MUST be an object like {"mean":[0.485,0.456,0.406],"std":[0.229,0.224,0.225]} (NOT true/false)
- training_config.image_size MUST also be a string like "224x224" or "640x640"
- training_config.augmentation / mixup / cutmix MUST be booleans (true/false), NOT nested objects
- postprocessing.export_format MUST be an array like ["onnx","torchscript"] (NOT a single string)
- hardware_requirements.gpu MUST be a string like "NVIDIA T4" (NOT an object)
- hardware_requirements.vram_gb MUST be an integer like 16
- enabled_skills MUST be an array of skill ids from the AVAILABLE PIPELINE SKILLS list below

Rules by task_type:
- classification: list categories in "classes"; EfficientNet-B0; image 224x224; nms_iou_threshold 0.0
- multi_label: list all possible labels in "classes"; EfficientNet-B0; image 224x224
- regression: set target_name and target_unit; classes may be empty; EfficientNet-B0; image 224x224
- object_localization: list object classes in "classes"; YOLOv8n; image 640x640; nms ~0.5
- object_detection: list object classes in "classes"; YOLOv8m; image 640x640; nms ~0.5
- description: one sentence a non-engineer would understand; mention they upload pre-labeled data
- classes MUST include EVERY label/category the user named in the chat (do not drop any)"""

        transcript_text = _conversation_transcript(body.messages)
        known_labels = _dedupe_labels(
            [str(x) for x in (discovery.get("extracted_labels") or []) if str(x).strip()]
        )
        label_hint = ""
        if known_labels:
            label_hint = (
                "\n\nLabels the assessment model already read from this conversation "
                "(include ALL of them in classes): " + json.dumps(known_labels)
            )
        resolved_task = None
        try:
            resolved_task = resolve_task_type_with_llm(
                client,
                model=vlm_model(),
                transcript=transcript,
                token_kwargs=vlm_json_kwargs(1200),
                trace_kwargs=vlm_trace_kwargs(
                    name="vlm-resolve-task-type",
                    project_id=body.project_id,
                    user_id=uid,
                    tags=["vlm", "generate-config", "task-type"],
                ),
            )
        except Exception:
            logger.exception("VLM task_type resolve failed; falling back to discovery/config JSON")
        if not resolved_task:
            resolved_task = discovery.get("detected_task")
        task_lock = (
            f'\n\nHARD REQUIREMENT: task_type MUST be "{resolved_task}". '
            "Do not pick another type. The user already confirmed this in chat."
            if resolved_task
            else ""
        )
        skills_section = ""
        try:
            from services.skills_store import get_skills_store

            skills_section = get_skills_store().format_prompt_section(
                str(resolved_task) if resolved_task else None
            )
        except Exception:
            logger.exception("Failed to load skills prompt section")
        combined = (
            f"{config_prompt}{skills_section}{label_hint}{task_lock}"
            f"\n\nConversation transcript:\n{transcript_text}"
        )

        messages = [
            {
                "role": "system",
                "content": "You are a technical AI assistant that generates structured training configurations. Always return valid JSON.",
            },
            {"role": "user", "content": combined},
        ]

        if body.images:
            user_content: list = [{"type": "text", "text": combined}]
            for img_base64 in _prepare_vlm_images(body.images):
                user_content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": img_base64, "detail": "low"},
                    }
                )
            messages[1]["content"] = user_content

        completion = client.chat.completions.create(
            model=vlm_model(),
            messages=messages,
            **vlm_json_kwargs(6000),
            response_format={"type": "json_object"},
            **vlm_trace_kwargs(
                name="vlm-generate-config",
                project_id=body.project_id,
                user_id=uid,
                tags=["vlm", "generate-config"],
                metadata={"force": body.force},
            ),
        )

        raw = json.loads(completion.choices[0].message.content or "{}")
        raw.pop("evaluation", None)
        spec = parse_project_spec(raw)
        spec = apply_resolved_task_type(spec, resolved_task)
        # Never lose labels the assess model already confirmed.
        spec = _merge_spec_classes(spec, known_labels)

        if body.project_id:
            try:
                _project_store.save_spec(body.project_id, spec)
                _project_store.save_chat(
                    body.project_id,
                    [{"role": m.role, "content": m.content} for m in body.messages],
                )
            except KeyError:
                raise HTTPException(status_code=404, detail="Project not found")

        credits = debit_from_request(
            request,
            db,
            "generate_config",
            ref=body.project_id,
            note="Generate ProjectSpec",
        )

        return {
            "success": True,
            "config": spec.model_dump(),
            "spec_version": spec.spec_version,
            "credits": credits,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        flush_langfuse()


def _spa_index():
    index = os.path.join(STATIC_DIR, "index.html")
    if os.path.isfile(index):
        return FileResponse(
            index,
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )
    return None


def _static_file(relative_path: str) -> FileResponse | None:
    candidate = os.path.join(STATIC_DIR, relative_path)
    if not os.path.isfile(candidate):
        return None
    headers: dict[str, str] = {}
    if relative_path.startswith("assets/"):
        headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return FileResponse(candidate, headers=headers)


@app.get("/")
def root():
    spa = _spa_index()
    if spa is not None:
        return spa
    return {"status": "VisionDock AI API is running"}


@app.get("/{full_path:path}")
def spa_fallback(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")
    if full_path.startswith("assets/"):
        static = _static_file(full_path)
        if static is not None:
            return static
        raise HTTPException(status_code=404, detail="Not found")
    if "." in os.path.basename(full_path):
        static = _static_file(full_path)
        if static is not None:
            return static
        raise HTTPException(status_code=404, detail="Not found")
    spa = _spa_index()
    if spa is not None:
        return spa
    raise HTTPException(status_code=404, detail="Not found")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
