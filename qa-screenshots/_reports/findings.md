# VisionDock comprehensive CV-task QA findings

Base URL: https://visiondock-api-ataha.azurewebsites.net
Finished (UTC): 2026-08-11 16:51:42Z
Execution: **parallel** Playwright workers (isolated browser contexts) + classification solo + multi_label solo retry after VLM contention.
Scope: for each CV task — prepare data → VLM chat → Generate Config → dataset upload → **Step 3 review**. Training was **not** started.

## Results summary

- **classification**: PASS · project `prj-884a6c04` · 16 screenshots under `qa-screenshots/classification/`
- **multi_label**: PASS · project `prj-e6eb9f1c` · 22 screenshots under `qa-screenshots/multi_label/`
- **regression**: PASS · project `prj-6ac540fd` · 22 screenshots under `qa-screenshots/regression/`
- **object_detection**: PASS · project `prj-03a8ace7` · 18 screenshots under `qa-screenshots/object_detection/`
- **object_localization**: PASS · project `prj-24a7a46f` · 19 screenshots under `qa-screenshots/object_localization/`

## Stage directories (per task)

`00-prep` → `01-login-home` → `02-new-workspace` → `03-sample-upload` → `04-vlm-chat` → `05-generate-config` → `06-dataset-step` → `07-training-review` → `08-ui-details`

## High-signal defects (punctuation / copy / logic)

1. **Localization ZIP explainer hardcodes detection** — Step 2: `This task is object detection` even when badge is `Find one object`.
2. **Cost estimate currency glitch** — `$ $0.29-$0.41` or `$ 0.22–$0.31` (extra space / double `$`).
3. **Locale decimal in Confidence** — `0,5` on classification review.
4. **Class list pollution** — chat sentences become extra class chips; `Classes (3)` with only OK/Defect intended.
5. **Toast grammar** — `Upload your pre-labeled sort into one group dataset.` (lowercased TASK_LABELS).
6. **Mixed dashes** — em dash `—` in body copy vs spaced hyphen ` - ` in AI banner / sidebar.
7. **Inconsistent counters** — `10/10` vs `10 / 10` on the same Step 1 screen.
8. **Step 3 title vs CTA** — H3 `Start training` but button is `Complete setup >`.
9. **Ellipsis mix** — typographic `…` in chat placeholders vs ASCII `...` in search / some hints.

## Per-task notes

### classification

- **[NOTE]** `04-vlm-chat` — Generate Config mentioned in UI after turn
  - turn=1
- **[NOTE]** `04-vlm-chat` — Mixed dash styles (em dash and spaced hyphen)
  - Both '—' and ' - ' appear on page
- **[NOTE]** `05-generate-config` — Mixed dash styles (em dash and spaced hyphen)
  - Both '—' and ' - ' appear on page
- **[NOTE]** `06-dataset-step` — Mixed dash styles (em dash and spaced hyphen)
  - Both '—' and ' - ' appear on page
- **[NOTE]** `07-training-review` — Mixed dash styles (em dash and spaced hyphen)
  - Both '—' and ' - ' appear on page
- **[NOTE]** `07-training-review` — Step 3 H3 is 'Start training' while CTA may also start training
  - Header copy: 'Start training' — may confuse with the action button.
  - Exact UI: `Start training`
- **[NOTE]** `08-ui-details` — Mixed dash styles (em dash and spaced hyphen)
  - Both '—' and ' - ' appear on page
- **[FAIL]** `07-training-review` — Double currency marker in cost estimate
  - Shows '$ $0.29-$0.41' (space + duplicated $).
  - Exact UI: `$ $0.29-$0.41`
- **[FAIL]** `07-training-review` — Confidence uses comma decimal
  - English UI shows 0,5 instead of 0.5.
  - Exact UI: `0,5`
- **[FAIL]** `07-training-review` — Classes(3) includes chat prose chip
  - Extra class chip like 'OK or Defect. These are top-down photos…' merged from transcript.
  - Exact UI: `Classes (3)`
- **[FAIL]** `07-training-review` — Toast lowercases TASK_LABEL awkwardly
  - Toast: 'Step 2: Upload your pre-labeled sort into one group dataset.'
  - Exact UI: `sort into one group`

### multi_label

- **[NOTE]** `01-login-home` — Mixed dash styles (em dash and spaced hyphen)
  - Both '—' and ' - ' appear on page
- **[NOTE]** `04-vlm-chat` — Generate Config mentioned in UI after turn
  - turn=1
- **[NOTE]** `04-vlm-chat` — Mixed dash styles (em dash and spaced hyphen)
  - Both '—' and ' - ' appear on page
- **[FAIL]** `05-generate-config` — Config generation timed out
  - Continue stayed disabled
- **[BLOCKED]** `error` — Task aborted
  - Page.wait_for_function: Timeout 120000ms exceeded.
- **[NOTE]** `05-generate-config` — Mixed dash styles (em dash and spaced hyphen)
  - Both '—' and ' - ' appear on page
- **[NOTE]** `07-training-review` — Step 3 H3 is 'Start training' while CTA may also start training
  - Header copy: 'Start training' — may confuse with the action button.
  - Exact UI: `Start training`

### regression

- **[NOTE]** `01-login-home` — Mixed dash styles (em dash and spaced hyphen)
  - Both '—' and ' - ' appear on page
- **[NOTE]** `04-vlm-chat` — Generate Config mentioned in UI after turn
  - turn=1
- **[NOTE]** `04-vlm-chat` — Mixed dash styles (em dash and spaced hyphen)
  - Both '—' and ' - ' appear on page
- **[NOTE]** `05-generate-config` — Mixed dash styles (em dash and spaced hyphen)
  - Both '—' and ' - ' appear on page
- **[NOTE]** `07-training-review` — Step 3 H3 is 'Start training' while CTA may also start training
  - Header copy: 'Start training' — may confuse with the action button.
  - Exact UI: `Start training`
- **[NOTE]** `07-training-review` — Cost formatting has spaced dollar
  - Shows '$ 0.22–$0.31' (space after first $).
  - Exact UI: `$ 0.22–$0.31`

### object_detection

- **[NOTE]** `01-login-home` — Mixed dash styles (em dash and spaced hyphen)
  - Both '—' and ' - ' appear on page
- **[NOTE]** `04-vlm-chat` — Generate Config mentioned in UI after turn
  - turn=1
- **[NOTE]** `04-vlm-chat` — Mixed dash styles (em dash and spaced hyphen)
  - Both '—' and ' - ' appear on page
- **[NOTE]** `05-generate-config` — Mixed dash styles (em dash and spaced hyphen)
  - Both '—' and ' - ' appear on page
- **[NOTE]** `06-dataset-step` — Mixed dash styles (em dash and spaced hyphen)
  - Both '—' and ' - ' appear on page
- **[NOTE]** `07-training-review` — Mixed dash styles (em dash and spaced hyphen)
  - Both '—' and ' - ' appear on page
- **[NOTE]** `07-training-review` — Step 3 H3 is 'Start training' while CTA may also start training
  - Header copy: 'Start training' — may confuse with the action button.
  - Exact UI: `Start training`
- **[NOTE]** `08-ui-details` — Mixed dash styles (em dash and spaced hyphen)
  - Both '—' and ' - ' appear on page

### object_localization

- **[NOTE]** `01-login-home` — Mixed dash styles (em dash and spaced hyphen)
  - Both '—' and ' - ' appear on page
- **[NOTE]** `04-vlm-chat` — Generate Config mentioned in UI after turn
  - turn=1
- **[NOTE]** `04-vlm-chat` — Mixed dash styles (em dash and spaced hyphen)
  - Both '—' and ' - ' appear on page
- **[NOTE]** `05-generate-config` — Mixed dash styles (em dash and spaced hyphen)
  - Both '—' and ' - ' appear on page
- **[FAIL]** `06-dataset-step` — Localization ZIP explainer hardcodes 'object detection'
  - Step 2 note says 'This task is object detection' even when task is Find one object.
  - Exact UI: `This task is object detection`
- **[NOTE]** `06-dataset-step` — Mixed dash styles (em dash and spaced hyphen)
  - Both '—' and ' - ' appear on page
- **[NOTE]** `07-training-review` — Mixed dash styles (em dash and spaced hyphen)
  - Both '—' and ' - ' appear on page
- **[NOTE]** `07-training-review` — Step 3 H3 is 'Start training' while CTA may also start training
  - Header copy: 'Start training' — may confuse with the action button.
  - Exact UI: `Start training`
- **[NOTE]** `08-ui-details` — Mixed dash styles (em dash and spaced hyphen)
  - Both '—' and ' - ' appear on page
- **[NOTE]** `07-training-review` — Cost formatting has spaced dollar
  - Shows '$ 0.92–$1.31'.
  - Exact UI: `$ 0.92–$1.31`

### all

- **[NOTE]** `07-training-review` — Primary CTA is 'Complete setup' not Start training
  - Header says Start training; footer CTA is Complete setup >. Training was not clicked.
  - Exact UI: `Complete setup >`
- **[NOTE]** `ui` — Search placeholder ellipsis
  - Header search: 'Search resources...'
  - Exact UI: `Search resources...`

