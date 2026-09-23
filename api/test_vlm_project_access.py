"""Exercise real endpoint bodies without importing main's service startup."""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException
from starlette.requests import Request

from services.project_access import require_project_access, session_user


def _endpoint(name: str):
    # Compile the complete handler, unchanged, but omit route registration and
    # dependency defaults. Importing main would initialize unrelated services.
    tree = ast.parse(Path(__file__).with_name("main.py").read_text())
    node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == name)
    node.decorator_list = []
    node.args.defaults = []
    for arg in node.args.args:
        arg.annotation = None
    node.returns = None
    namespace = {
        "session_user": session_user,
        "require_project_access": require_project_access,
        "HTTPException": HTTPException,
        "_project_store": Mock(),
    }
    for key in (
        "get_vlm_client", "check_from_request", "debit_from_request",
        "_resolve_vlm_images", "assess_discovery_with_llm",
        "resolve_task_type_with_llm", "parse_project_spec", "flush_langfuse",
    ):
        namespace[key] = Mock(name=key)
    namespace["get_vlm_client"].return_value = None
    exec(compile(ast.Module(body=[node], type_ignores=[]), "main.py", "exec"), namespace)
    return namespace[name], namespace


class VlmProjectAccessTests(unittest.IsolatedAsyncioTestCase):
    async def _check(self, *, session, meta, project_id="p", status=404, force=False, images=None):
        for name in ("analyze_with_vlm", "generate_config"):
            with self.subTest(endpoint=name, project_id=project_id):
                handler, ns = _endpoint(name)
                ns["_project_store"].get_meta.return_value = meta
                body = SimpleNamespace(project_id=project_id, force=force, images=images, messages=[])
                request = Request({"type": "http", "session": session})
                with self.assertRaises(HTTPException) as caught:
                    await handler(body, request, None)
                self.assertEqual(caught.exception.status_code, status)
                if status in (401, 404):
                    self.assertEqual(
                        caught.exception.detail,
                        "Not authenticated" if status == 401 else "Project not found",
                    )
                    ns["get_vlm_client"].assert_not_called()
                    ns["flush_langfuse"].assert_not_called()
                else:
                    # Reaching the existing 503 proves authorized/projectless
                    # calls entered the unchanged body, without real VLM work.
                    ns["get_vlm_client"].assert_called_once_with()
                    ns["flush_langfuse"].assert_called_once_with()
                for key in (
                    "check_from_request", "debit_from_request", "_resolve_vlm_images",
                    "assess_discovery_with_llm", "resolve_task_type_with_llm", "parse_project_spec",
                ):
                    ns[key].assert_not_called()
                expected_reads = 1 if project_id and status != 401 else 0
                self.assertEqual(ns["_project_store"].get_meta.call_count, expected_reads)
                # No other ProjectStore method, including sample reads/writes.
                self.assertEqual(len(ns["_project_store"].mock_calls), expected_reads)

    async def test_owner_enters_existing_body(self):
        await self._check(session={"user": "owner@test", "user_id": 1},
                          meta={"owner_email": "owner@test", "owner_user_id": 1}, status=503)

    async def test_other_user_rejected_even_with_force_and_images(self):
        await self._check(session={"user": "other@test", "user_id": 1},
                          meta={"owner_email": "owner@test", "owner_user_id": 1},
                          force=True, images=["data:image/png;base64,AAAA"])

    async def test_nonexistent_project(self):
        await self._check(session={"user": "owner@test"}, meta=None)

    async def test_missing_session(self):
        await self._check(session={}, meta={"owner_email": "owner@test"}, status=401)

    async def test_projectless_null_empty_and_omitted_default(self):
        # VLMRequest defaults omitted project_id to None.
        for project_id in (None, ""):
            await self._check(session={}, meta=None, project_id=project_id, status=503)

    async def test_legacy_owner_uses_existing_contract(self):
        with patch.dict("os.environ", {"AUTH_USERNAME": "legacy@test"}):
            await self._check(session={"user": "legacy@test"}, meta={}, status=503)


if __name__ == "__main__":
    unittest.main()
