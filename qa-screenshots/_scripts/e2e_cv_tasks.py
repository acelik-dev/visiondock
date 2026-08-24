#!/usr/bin/env python3
"""Comprehensive VisionDock CV-task QA: VLM → dataset → training review (no train start)."""

from __future__ import annotations

import json
import os
import re
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PwTimeout, sync_playwright

BASE = "https://visiondock-api-ataha.azurewebsites.net"
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "_datasets"
REPORT = ROOT / "_reports"
FINDINGS_PATH = REPORT / "findings.md"
JSON_PATH = REPORT / "run-log.json"

USER = "admin@visiondock.local"
PASSWORD = "UZtI2r4Iz7CccM"

# When running a single task as a worker, write isolated artifacts.
WORKER_TAG = os.environ.get("QA_WORKER_TAG", "").strip()

STAGES = [
    "00-prep",
    "01-login-home",
    "02-new-workspace",
    "03-sample-upload",
    "04-vlm-chat",
    "05-generate-config",
    "06-dataset-step",
    "07-training-review",
    "08-ui-details",
]


@dataclass
class Finding:
    task: str
    severity: str  # PASS | FAIL | NOTE | BLOCKED
    stage: str
    title: str
    detail: str
    exact_ui: str = ""


@dataclass
class TaskResult:
    task: str
    ok: bool
    project_id: str | None = None
    error: str | None = None
    screenshots: list[str] = field(default_factory=list)
    ui_snippets: list[str] = field(default_factory=list)


FINDINGS: list[Finding] = []
RESULTS: list[TaskResult] = []


def ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def note(task: str, severity: str, stage: str, title: str, detail: str, exact_ui: str = ""):
    FINDINGS.append(Finding(task, severity, stage, title, detail, exact_ui))
    print(f"[{severity}] {task}/{stage}: {title} — {detail[:160]}")


def ss(page: Page, task: str, stage: str, name: str, full_page: bool = True) -> str:
    out_dir = ROOT / task / stage
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.png"
    page.screenshot(path=str(path), full_page=full_page)
    rel = str(path.relative_to(ROOT))
    print(f"  SS → {rel}")
    return rel


def visible_text(page: Page) -> str:
    return page.evaluate(
        """() => {
      const skip = new Set(['SCRIPT','STYLE','NOSCRIPT']);
      const walk = (n) => {
        if (!n) return '';
        if (n.nodeType === 3) return n.textContent || '';
        if (n.nodeType !== 1) return '';
        if (skip.has(n.tagName)) return '';
        const style = window.getComputedStyle(n);
        if (style && (style.display === 'none' || style.visibility === 'hidden')) return '';
        let t = '';
        for (const c of n.childNodes) t += walk(c);
        return t;
      };
      return walk(document.body).replace(/\\s+/g, ' ').trim();
    }"""
    )


def dump_ui(page: Page, task: str, stage: str, name: str) -> str:
    text = visible_text(page)
    out = ROOT / task / stage / f"{name}.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n", encoding="utf-8")
    return text


def analyze_copy(task: str, stage: str, text: str):
    """Flag punctuation / copy issues."""
    checks = [
        (r"\s{2,}", "Double spaces in visible UI text"),
        (r"\.\.\.", "ASCII ellipsis '...' (prefer typographic '…' if elsewhere used)"),
        (r"\?\?", "Double question mark"),
        (r"!!", "Double exclamation"),
        (r"\s,", "Space before comma"),
        (r"\s\.", "Space before period"),
        (r",,", "Double comma"),
        (r"\.\s*\.", "Odd double period"),
        (r"\u00a0", "Non-breaking space present"),
    ]
    for pat, title in checks:
        m = re.search(pat, text)
        if m:
            start = max(0, m.start() - 40)
            end = min(len(text), m.end() + 40)
            note(task, "NOTE", stage, title, f"Around: …{text[start:end]}…", text[start:end])

    # Specific known/interesting strings
    interesting = [
        "Upload sample images (10 required)",
        "Define Your Vision Task",
        "Generate Config",
        "Review setup",
        "Start training",
        "Still missing steps",
        "Why a ZIP (not per-group photo upload)?",
        "This task is object detection",
        "Sort into one group",
        "Several tags per photo",
        "Predict a number",
        "Find one object",
        "Find several objects",
        "Attached images:",
        "Ready to build your plan",
        "Understanding your project",
        "Loading your projects…",
        "No projects yet. Create your first workspace to get started.",
        "Send −",
        "Config −",
    ]
    for s in interesting:
        if s in text:
            note(task, "PASS", stage, f"Copy present: {s!r}", "Observed exact string", s)

    # Localization copy bug: localization step still says object detection
    if task == "object_localization" and "This task is object detection" in text:
        note(
            task,
            "FAIL",
            stage,
            "Localization ZIP explainer hardcodes 'object detection'",
            "Step 2 note says 'This task is object detection' even when task is Find one object.",
            "This task is object detection",
        )

    # Em dash / en dash / hyphen mix
    if "—" in text and " - " in text:
        note(task, "NOTE", stage, "Mixed dash styles (em dash and spaced hyphen)", "Both '—' and ' - ' appear on page")


def login(page: Page) -> None:
    page.goto(f"{BASE}/", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(1500)
    # Already logged in?
    if page.locator("text=Start with AI discovery").count() > 0 or page.locator("text=Create workspace").count() > 0:
        return
    if page.locator("#email").count() == 0:
        page.goto(f"{BASE}/", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(1000)
    page.fill("#email", USER)
    page.fill("#password", PASSWORD)
    page.click('button[type="submit"]')
    page.wait_for_selector("text=Start with AI discovery", timeout=30000)
    page.wait_for_timeout(800)


def ensure_home(page: Page, task: str) -> None:
    # Prefer clicking Home in nav if present
    home = page.locator("button, a").filter(has_text=re.compile(r"^Home$"))
    if home.count():
        home.first.click()
        page.wait_for_timeout(800)
    else:
        page.goto(f"{BASE}/", wait_until="domcontentloaded")
        page.wait_for_timeout(1200)
    ss(page, task, "01-login-home", "01-home")
    dump = dump_ui(page, task, "01-login-home", "01-home-ui")
    analyze_copy(task, "01-login-home", dump)


def start_new_workspace(page: Page, task: str) -> str | None:
    # Always force a brand-new project so parallel/sequential runs never reuse another task.
    page.evaluate(
        """() => {
          for (const k of Object.keys(localStorage)) {
            if (k === 'visiondock_active_project_id' || k.startsWith('visiondock_active_project_id:')) {
              localStorage.removeItem(k);
            }
          }
          sessionStorage.setItem('visiondock_force_new_project', '1');
        }"""
    )
    page.goto(f"{BASE}/", wait_until="domcontentloaded")
    page.wait_for_timeout(800)
    btn = page.locator("button").filter(has_text="Create workspace")
    if btn.count() == 0:
        open_btn = page.locator("button").filter(has_text="Open VLM chat")
        if open_btn.count():
            open_btn.first.click()
            page.wait_for_timeout(800)
        create = page.locator("button").filter(has_text=re.compile(r"Create workspace|New workspace|Fresh", re.I))
        if create.count():
            create.first.click()
        else:
            page.evaluate("() => sessionStorage.setItem('visiondock_force_new_project', '1')")
            page.goto(f"{BASE}/", wait_until="domcontentloaded")
            page.wait_for_timeout(500)
            page.locator("button").filter(has_text="Create workspace").first.click()
    else:
        btn.first.click()
    page.wait_for_selector("text=Define Your Vision Task", timeout=45000)
    page.wait_for_timeout(1500)
    # Project id may live in breadcrumb / sidebar rather than localStorage (prod bundle variance).
    pid = page.evaluate(
        """() => {
          const fromLs = localStorage.getItem('visiondock_active_project_id');
          if (fromLs) return fromLs;
          const m = document.body.innerText.match(/prj-[a-f0-9]+/i);
          return m ? m[0] : null;
        }"""
    )
    if pid:
        page.evaluate("(id) => localStorage.setItem('visiondock_active_project_id', id)", pid)
    page.wait_for_timeout(500)
    ss(page, task, "02-new-workspace", "01-empty-discovery")
    dump = dump_ui(page, task, "02-new-workspace", "01-empty-discovery-ui")
    analyze_copy(task, "02-new-workspace", dump)
    ta = page.locator("textarea").first
    if ta.count():
        ph = ta.get_attribute("placeholder") or ""
        note(task, "PASS" if "…" in ph or "..." in ph else "NOTE", "02-new-workspace", "Chat placeholder", ph, ph)
        if "..." in ph and "…" not in ph:
            note(task, "NOTE", "02-new-workspace", "Placeholder uses ASCII ellipsis", ph, ph)
    return pid


def upload_samples(page: Page, task: str) -> None:
    samples = sorted((DATA / "vlm_samples").glob("*.jpg"))
    assert len(samples) >= 10, "Need 10 VLM sample images"
    # Prefer the discovery header file input (accept=image/*, multiple)
    inp = page.locator('input[type="file"][accept="image/*"][multiple]').first
    if inp.count() == 0:
        inp = page.locator('input[type="file"][accept="image/*"]').first
    inp.set_input_files([str(p) for p in samples[:10]])
    page.wait_for_timeout(2000)
    # UI uses both "10/10" and "10 / 10"
    try:
        page.wait_for_function(
            """() => {
              const t = document.body.innerText || '';
              return /\\b10\\s*\\/\\s*10\\b/.test(t) || t.includes('10/10 ✓');
            }""",
            timeout=90000,
        )
    except PwTimeout:
        ss(page, task, "03-sample-upload", "99-samples-incomplete")
        dump_ui(page, task, "03-sample-upload", "99-samples-ui")
        raise RuntimeError("Sample upload did not reach 10/10")
    page.wait_for_timeout(800)
    ss(page, task, "03-sample-upload", "01-samples-10-of-10")
    dump = dump_ui(page, task, "03-sample-upload", "01-samples-ui")
    analyze_copy(task, "03-sample-upload", dump)
    if re.search(r"10\s*/\s*10", dump):
        note(task, "PASS", "03-sample-upload", "Sample counter shows 10/10", "Samples complete", "10/10")
    if "Attached images:" in dump:
        note(task, "PASS", "03-sample-upload", "Label uses colon after Attached images", "Exact: 'Attached images:'", "Attached images:")
    # Punctuation inconsistency: spaced vs unspaced counters
    if "10 / 10" in dump and "10/10" in dump:
        note(
            task,
            "NOTE",
            "03-sample-upload",
            "Inconsistent sample counter spacing",
            "Page shows both '10 / 10' and '10/10'.",
        )


def send_chat(page: Page, message: str, timeout_ms: int = 120000) -> str:
    ta = page.locator("textarea").first
    ta.fill(message)
    page.locator("button").filter(has_text=re.compile(r"^Send$")).first.click()
    # Wait until analyzing ends — Send enabled again or assistant bubble grows
    page.wait_for_timeout(1500)
    try:
        page.wait_for_function(
            """() => {
              const btns = [...document.querySelectorAll('button')];
              const send = btns.find(b => (b.textContent||'').trim() === 'Send');
              return send && !send.disabled;
            }""",
            timeout=timeout_ms,
        )
    except PwTimeout:
        pass
    page.wait_for_timeout(800)
    return visible_text(page)


def run_vlm_chat(page: Page, task: str, turns: list[str]) -> None:
    for i, msg in enumerate(turns, 1):
        text = send_chat(page, msg)
        ss(page, task, "04-vlm-chat", f"{i:02d}-after-turn-{i}")
        dump_ui(page, task, "04-vlm-chat", f"{i:02d}-chat-ui")
        analyze_copy(task, "04-vlm-chat", text)
        # Capture assistant invitation strings
        if "Generate Config" in text:
            note(task, "NOTE", "04-vlm-chat", "Generate Config mentioned in UI after turn", f"turn={i}")
        # Check curly apostrophe in notify / helper
        if "you're" in text.lower() or "you’re" in text:
            note(task, "NOTE", "04-vlm-chat", "Apostrophe form in UI", "Observed you're/you’re")


def generate_config(page: Page, task: str) -> None:
    btn = page.locator("button").filter(has_text="Generate Config")
    # If disabled, send one more wrap-up turn
    for attempt in range(3):
        if btn.count() and btn.first.is_enabled():
            break
        send_chat(
            page,
            "That covers it: labels confirmed, fixed factory camera, near real-time alerts. "
            "Please unlock Generate Config so I can build the training plan.",
        )
        ss(page, task, "04-vlm-chat", f"90-unlock-attempt-{attempt+1}")
        page.wait_for_timeout(500)
    if not btn.count() or not btn.first.is_enabled():
        # Force click via evaluate if UI says ready but button stuck — still try click
        note(task, "FAIL", "05-generate-config", "Generate Config still disabled", "Could not enable after wrap-up turns")
        ss(page, task, "05-generate-config", "01-generate-disabled")
        dump_ui(page, task, "05-generate-config", "01-disabled-ui")
        raise RuntimeError("Generate Config disabled")
    ss(page, task, "05-generate-config", "01-before-click")
    btn.first.click()
    # Wait for config panel / Continue enabled / task badge
    page.wait_for_timeout(2000)
    try:
        page.wait_for_selector("text=Continue", timeout=120000)
        page.wait_for_function(
            """() => {
              const btns = [...document.querySelectorAll('button')];
              const c = btns.find(b => (b.textContent||'').trim().startsWith('Continue'));
              return c && !c.disabled;
            }""",
            timeout=120000,
        )
    except PwTimeout:
        note(task, "FAIL", "05-generate-config", "Config generation timed out", "Continue stayed disabled")
        ss(page, task, "05-generate-config", "02-timeout")
        raise
    page.wait_for_timeout(1000)
    ss(page, task, "05-generate-config", "02-config-ready")
    dump = dump_ui(page, task, "05-generate-config", "02-config-ui")
    analyze_copy(task, "05-generate-config", dump)
    # Task badge expectations
    expected_badges = {
        "classification": "Sort into one group",
        "multi_label": "Several tags per photo",
        "regression": "Predict a number",
        "object_detection": "Find several objects",
        "object_localization": "Find one object",
    }
    badge = expected_badges[task]
    if badge in dump:
        note(task, "PASS", "05-generate-config", f"Task badge shows {badge!r}", "Exact match", badge)
    else:
        note(task, "FAIL", "05-generate-config", f"Expected task badge {badge!r} missing", dump[:500], badge)


def go_dataset_step(page: Page, task: str) -> None:
    page.locator("button").filter(has_text=re.compile(r"^Continue$")).first.click()
    page.wait_for_timeout(1500)
    # Wait for step-2 upload controls for this task type.
    # File inputs are often hidden — wait attached, or wait for visible copy.
    waits = {
        "classification": ("text=Add photos to each group", "visible"),
        "multi_label": ("#multi-label-images", "attached"),
        "regression": ("#regression-images", "attached"),
        "object_detection": ("#annotated-zip", "attached"),
        "object_localization": ("#annotated-zip", "attached"),
    }
    sel, state = waits.get(task, (None, None))
    if sel:
        try:
            page.wait_for_selector(sel, state=state, timeout=30000)
        except PwTimeout:
            # Fallback: task copy on step 2
            fallbacks = {
                "multi_label": "text=Add all photos",
                "regression": "text=Add the measurement list",
                "object_detection": "text=Upload your labeled package",
                "object_localization": "text=Upload your labeled package",
                "classification": "text=Add photos to each group",
            }
            fb = fallbacks.get(task)
            if fb:
                try:
                    page.wait_for_selector(fb, timeout=10000)
                except PwTimeout:
                    note(task, "FAIL", "06-dataset-step", f"Step 2 selector missing: {sel}", visible_text(page)[:500])
                    ss(page, task, "06-dataset-step", "00-missing-upload-ui")
                    raise
            else:
                note(task, "FAIL", "06-dataset-step", f"Step 2 selector missing: {sel}", visible_text(page)[:500])
                ss(page, task, "06-dataset-step", "00-missing-upload-ui")
                raise
    page.wait_for_timeout(500)
    ss(page, task, "06-dataset-step", "01-dataset-empty")
    dump = dump_ui(page, task, "06-dataset-step", "01-dataset-ui")
    analyze_copy(task, "06-dataset-step", dump)


def upload_dataset(page: Page, task: str) -> None:
    if task == "classification":
        for cls in ("ok", "defect"):
            folder = DATA / "classification" / cls
            files = sorted(folder.glob("*.jpg"))
            # Find the class card heading
            # Prefer clicking the zone then set files on its input
            heading = page.locator("h4").filter(has_text=re.compile(rf"^{cls}$", re.I))
            if heading.count() == 0:
                # Config may use OK/Defect capitalization
                alt = "OK" if cls == "ok" else "Defect"
                heading = page.locator("h4").filter(has_text=re.compile(rf"^{alt}$", re.I))
            if heading.count() == 0:
                # Any group card — match by text containing class
                heading = page.locator("h4").filter(has_text=re.compile(cls, re.I))
            card = heading.first.locator("xpath=ancestor::div[contains(@class,'cursor-pointer')][1]")
            inp = card.locator('input[type="file"]')
            if inp.count() == 0:
                # Fallback: all class file inputs in order
                inputs = page.locator('input[type="file"][accept="image/*"]')
                # skip sample inputs if any remain
                inp = inputs.nth(0 if cls == "ok" else 1)
            inp.set_input_files([str(p) for p in files])
            page.wait_for_timeout(2500)
            ss(page, task, "06-dataset-step", f"02-uploaded-{cls}")
    elif task == "multi_label":
        imgs = sorted((DATA / "multi_label" / "images").glob("*.jpg"))
        page.locator("#multi-label-images").set_input_files([str(p) for p in imgs])
        page.wait_for_timeout(2500)
        ss(page, task, "06-dataset-step", "02-images-uploaded")
        page.locator("#multi-label-manifest").set_input_files(str(DATA / "multi_label" / "labels.csv"))
        page.wait_for_timeout(3000)
        ss(page, task, "06-dataset-step", "03-manifest-uploaded")
    elif task == "regression":
        imgs = sorted((DATA / "regression" / "images").glob("*.jpg"))
        page.locator("#regression-images").set_input_files([str(p) for p in imgs])
        page.wait_for_timeout(2500)
        ss(page, task, "06-dataset-step", "02-images-uploaded")
        page.locator("#regression-targets").set_input_files(str(DATA / "regression" / "targets.csv"))
        page.wait_for_timeout(3000)
        ss(page, task, "06-dataset-step", "03-targets-uploaded")
    elif task == "object_detection":
        page.locator("#annotated-zip").set_input_files(str(DATA / "object_detection" / "detection_package.zip"))
        page.wait_for_timeout(4000)
        ss(page, task, "06-dataset-step", "02-zip-uploaded")
    elif task == "object_localization":
        page.locator("#annotated-zip").set_input_files(
            str(DATA / "object_localization" / "localization_package.zip")
        )
        page.wait_for_timeout(4000)
        ss(page, task, "06-dataset-step", "02-zip-uploaded")

    # Wait for Ready / Review setup enabled
    for _ in range(30):
        dump = visible_text(page)
        btn = page.locator("button").filter(has_text="Review setup")
        if btn.count() and btn.first.is_enabled():
            break
        page.wait_for_timeout(1000)
    else:
        dump = dump_ui(page, task, "06-dataset-step", "99-not-ready-ui")
        ss(page, task, "06-dataset-step", "99-not-ready")
        note(task, "FAIL", "06-dataset-step", "Review setup stayed disabled", dump[:800])
        raise RuntimeError("Dataset not ready")

    dump = dump_ui(page, task, "06-dataset-step", "04-ready-ui")
    ss(page, task, "06-dataset-step", "04-dataset-ready")
    analyze_copy(task, "06-dataset-step", dump)
    if "Ready" in dump:
        note(task, "PASS", "06-dataset-step", "Status shows Ready", "Dataset ready indicator", "Ready")
    if "Still missing steps" in dump:
        note(task, "NOTE", "06-dataset-step", "Still seeing 'Still missing steps' copy nearby", dump[-400:])


def go_training_review(page: Page, task: str) -> None:
    page.locator("button").filter(has_text="Review setup").first.click()
    page.wait_for_timeout(1500)
    page.wait_for_selector("text=Start training", timeout=30000)
    ss(page, task, "07-training-review", "01-training-review-initial")
    # Wait for auto-tune banner to settle (up to ~45s) so final SS is cleaner
    for _ in range(15):
        t = visible_text(page)
        if "Analyzing dataset images" not in t:
            break
        page.wait_for_timeout(3000)
    page.wait_for_timeout(800)
    ss(page, task, "07-training-review", "01-training-review")
    dump = dump_ui(page, task, "07-training-review", "01-review-ui")
    analyze_copy(task, "07-training-review", dump)

    # Critical: do NOT start training — verify CTA exists but leave it unclicked
    train_cta = page.locator("button").filter(
        has_text=re.compile(r"Train|Start training|Launch|Begin|Submit", re.I)
    )
    cta_labels = []
    for i in range(min(train_cta.count(), 8)):
        t = (train_cta.nth(i).inner_text() or "").strip().replace("\n", " ")
        if t:
            cta_labels.append(t)
    note(
        task,
        "PASS",
        "07-training-review",
        "Reached Step 3 without starting training",
        f"CTA candidates left unclicked: {cta_labels}",
    )

    # Header says "Start training" which is slightly aggressive for a review step
    if "Start training" in dump and "Pipeline settings are chosen automatically" in dump:
        note(
            task,
            "NOTE",
            "07-training-review",
            "Step 3 H3 is 'Start training' while CTA may also start training",
            "Header copy: 'Start training' — may confuse with the action button.",
            "Start training",
        )

    # Detailed copy bugs observed on Step 3
    if re.search(r"\$\s*\$", dump):
        note(
            task,
            "FAIL",
            "07-training-review",
            "Double dollar sign in cost estimate",
            "UI shows '$ $…' instead of a single currency marker.",
            re.search(r"\$\s*\$[\d.,\-$]+", dump).group(0) if re.search(r"\$\s*\$[\d.,\-$]+", dump) else "$ $",
        )
    if re.search(r"\b0,5\b", dump) or re.search(r"Confidence[:\s]*0,", dump):
        note(
            task,
            "FAIL",
            "07-training-review",
            "Confidence uses comma decimal (0,5)",
            "Likely locale formatting bug; English UI should show 0.5.",
            "0,5",
        )
    m_classes = re.search(r"Classes\s*\((\d+)\)", dump)
    if m_classes and int(m_classes.group(1)) > 2 and task == "classification":
        note(
            task,
            "FAIL",
            "07-training-review",
            f"Classes count inflated ({m_classes.group(1)})",
            "Chat prose may have been merged into class list.",
            m_classes.group(0),
        )
    toastish = re.search(r"Step 2: Upload your pre-labeled .{5,80}? dataset\.", dump)
    if toastish:
        note(
            task,
            "FAIL",
            "07-training-review",
            "Toast lowercases TASK_LABELS awkwardly",
            toastish.group(0),
            toastish.group(0),
        )
    if "Analyzing dataset images" in dump:
        note(
            task,
            "NOTE",
            "07-training-review",
            "Pipeline auto-tune banner visible on Step 3",
            "Analyzing dataset images… may linger; capture whether it resolves.",
        )

    # UI details pass: scroll and capture more
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(500)
    ss(page, task, "08-ui-details", "01-bottom")
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(400)
    ss(page, task, "08-ui-details", "02-top")
    dump2 = dump_ui(page, task, "08-ui-details", "02-full-ui")
    analyze_copy(task, "08-ui-details", dump2)

    # Capture exact punctuation of key sentences
    for sentence in [
        "Pipeline settings are chosen automatically from your dataset images — review below, then start training.",
        "Upload and validate your labeled photos in Step 2 before starting training.",
        "Go back to Step 1 and use Generate Config after chatting with the assistant.",
    ]:
        if sentence in dump2:
            note(task, "PASS", "08-ui-details", "Exact sentence match", sentence, sentence)


TASK_SCRIPTS: dict[str, list[str]] = {
    "classification": [
        "I need binary image classification for product QC. Each photo should get exactly one label: OK or Defect. These are top-down photos of painted metal parts.",
        "Images come from a fixed overhead camera on a factory conveyor line, about 1280x720, indoor LED lighting.",
        "We need near real-time alerts (1–3 seconds per image). The only class names are OK and Defect.",
        "I have answered everything. Please unlock the configuration button now.",
    ],
    "multi_label": [
        "I need multi-label tagging: each photo can have several tags at once among rust, scratch, and dent on metal panels. Not single-class classification.",
        "Photos are handheld phone shots of outdoor storage racks, mixed lighting.",
        "Batch processing is fine (minutes). The only tags are rust, scratch, and dent.",
        "I have answered everything. Please unlock the configuration button now.",
    ],
    "regression": [
        "I need regression: predict a continuous age number from face photos. Target column name should be age.",
        "Images are outdoor selfie-style photos from a mobile app, varied backgrounds.",
        "Batch overnight processing is fine. The numeric target is age in years.",
        "I have answered everything. Please unlock the configuration button now.",
    ],
    "object_detection": [
        "I need object detection with bounding boxes for multiple objects per image: jumper and canopy. Find several objects, not one.",
        "Fixed CCTV camera overlooking a worksite, daytime.",
        "Near real-time alerts. The only classes are jumper and canopy.",
        "I have answered everything. Please unlock the configuration button now.",
    ],
    "object_localization": [
        "I need object localization: find exactly one widget object per photo with a single bounding box (not multi-object detection).",
        "Fixed industrial camera above a fixture, indoor.",
        "Real-time under 1 second. The only class is widget.",
        "I have answered everything. Please unlock the configuration button now.",
    ],
}


def run_task(page: Page, task: str) -> TaskResult:
    result = TaskResult(task=task, ok=False)
    print(f"\n======== TASK: {task} ========")
    try:
        # Prep marker
        (ROOT / task / "00-prep").mkdir(parents=True, exist_ok=True)
        (ROOT / task / "00-prep" / "README.txt").write_text(
            f"Task={task}\nStarted={ts()}\nBase={BASE}\n", encoding="utf-8"
        )
        ensure_home(page, task)
        pid = start_new_workspace(page, task)
        result.project_id = pid
        note(task, "PASS", "02-new-workspace", "Project created", f"project_id={pid}")
        upload_samples(page, task)
        run_vlm_chat(page, task, TASK_SCRIPTS[task])
        generate_config(page, task)
        go_dataset_step(page, task)
        upload_dataset(page, task)
        go_training_review(page, task)
        result.ok = True
        note(task, "PASS", "07-training-review", "Flow complete (no training started)", f"project_id={pid}")
    except Exception as e:
        result.error = f"{e}\n{traceback.format_exc()}"
        note(task, "BLOCKED", "error", "Task aborted", str(e))
        try:
            ss(page, task, "08-ui-details", "99-error-state")
            dump_ui(page, task, "08-ui-details", "99-error-ui")
        except Exception:
            pass
    return result


def write_report(results: list[TaskResult], suffix: str = ""):
    REPORT.mkdir(parents=True, exist_ok=True)
    findings_path = REPORT / (f"findings{suffix}.md" if suffix else "findings.md")
    json_path = REPORT / (f"run-log{suffix}.json" if suffix else "run-log.json")
    lines = [
        "# VisionDock comprehensive CV-task QA findings",
        "",
        f"Base URL: {BASE}",
        f"Run finished (UTC): {ts()}",
        f"Worker: {WORKER_TAG or 'main'}",
        "Scope: VLM chat → dataset upload → training review (Step 3). **Training was not started.**",
        "Screenshots: `qa-screenshots/<task>/<stage>/`",
        "",
        "## Results summary",
        "",
    ]
    for r in results:
        status = "PASS" if r.ok else "FAIL/BLOCKED"
        err = f" — {(r.error or '').splitlines()[0]}" if r.error else ""
        lines.append(f"- **{r.task}**: {status} (project `{r.project_id}`){err}")
    lines += ["", "## Findings (detail)", ""]
    by_task: dict[str, list[Finding]] = {}
    for f in FINDINGS:
        by_task.setdefault(f.task, []).append(f)
    for task, items in by_task.items():
        lines.append(f"### {task}")
        lines.append("")
        for f in items:
            lines.append(f"- **[{f.severity}]** `{f.stage}` — {f.title}")
            lines.append(f"  - {f.detail}")
            if f.exact_ui:
                lines.append(f"  - Exact UI: `{f.exact_ui}`")
        lines.append("")
    findings_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {
                "finished": ts(),
                "worker": WORKER_TAG or "main",
                "results": [r.__dict__ for r in results],
                "findings": [f.__dict__ for f in FINDINGS],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nReport → {findings_path}")


def main() -> int:
    tasks = [t for t in sys.argv[1:] if not t.startswith("-")] or [
        "classification",
        "multi_label",
        "regression",
        "object_detection",
        "object_localization",
    ]
    suffix = f"-{WORKER_TAG}" if WORKER_TAG else (f"-{tasks[0]}" if len(tasks) == 1 else "")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Fresh context per process so parallel workers do not share cookies/storage.
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=1,
        )
        page = context.new_page()
        page.set_default_timeout(45000)
        login(page)
        ss(page, tasks[0], "01-login-home", "00-after-login")
        for task in tasks:
            RESULTS.append(run_task(page, task))
        browser.close()
    write_report(RESULTS, suffix=suffix)
    return 0 if all(r.ok for r in RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
