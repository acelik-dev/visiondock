#!/usr/bin/env python3
"""E2E test: login + training submit + poll until Azure ML job is queued."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar

BASE = os.getenv("VISIONDOCK_API", "https://visiondock-api.azurewebsites.net")
PROJECT_ID = os.getenv("TEST_PROJECT_ID", "prj-f8c34586")
MAX_WAIT = int(os.getenv("TEST_MAX_WAIT", "600"))


def load_env() -> tuple[str, str]:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(root, "api", ".env")
    user = password = ""
    if os.path.isfile(env_path):
        for line in open(env_path, encoding="utf-8"):
            line = line.strip()
            if line.startswith("AUTH_USERNAME="):
                user = line.split("=", 1)[1]
            elif line.startswith("AUTH_PASSWORD="):
                password = line.split("=", 1)[1]
    user = os.getenv("AUTH_USERNAME", user)
    password = os.getenv("AUTH_PASSWORD", password)
    return user, password


def request(
    jar: CookieJar,
    method: str,
    path: str,
    body: dict | None = None,
    timeout: float = 60,
) -> tuple[int, dict]:
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    try:
        with opener.open(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            payload = json.loads(raw) if raw.strip() else {"detail": raw[:300]}
        except json.JSONDecodeError:
            payload = {"detail": raw[:300]}
        return e.code, payload


def main() -> int:
    user, password = load_env()
    if not user or not password:
        print("Set AUTH_USERNAME / AUTH_PASSWORD in api/.env", file=sys.stderr)
        return 1

    jar = CookieJar()
    code, login = request(jar, "POST", "/api/auth/login", {"username": user, "password": password})
    print("login", code, login.get("authenticated"))
    if code != 200:
        return 1

    code, info = request(jar, "GET", "/api/training/info")
    print("training/info", code, info)

    t0 = time.time()
    code, submit = request(
        jar,
        "POST",
        "/api/training/submit",
        {
            "project_id": PROJECT_ID,
            "task_type": "object_detection",
            "config": {"epochs": 2, "imgsz": 640, "batch": 4, "nodes": 1},
        },
        timeout=90,
    )
    elapsed = time.time() - t0
    print(f"submit {code} in {elapsed:.1f}s", json.dumps(submit, indent=2)[:500])
    if code != 200 or not submit.get("success"):
        print("SUBMIT FAILED", submit.get("detail", submit), file=sys.stderr)
        return 1

    job_id = (submit.get("data") or {}).get("job_id")
    if not job_id:
        print("No job_id", file=sys.stderr)
        return 1

    print("job_id", job_id)
    deadline = time.time() + MAX_WAIT
    while time.time() < deadline:
        code, st = request(jar, "GET", f"/api/training/status/{job_id}", timeout=60)
        status = (st.get("data") or {}).get("status", "?")
        print("status", status)
        if status in ("Queued", "Starting", "Running", "Completed", "Preparing", "Finalizing"):
            print("SUCCESS — job reached Azure ML:", status)
            return 0
        if status == "Failed":
            print("JOB FAILED", json.dumps(st, indent=2), file=sys.stderr)
            return 1
        if code >= 500:
            print("ERROR", st.get("detail", st), file=sys.stderr)
            return 1
        time.sleep(5)

    print("TIMEOUT waiting for job", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
