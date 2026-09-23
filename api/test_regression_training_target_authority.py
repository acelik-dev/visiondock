"""Offline submission and AML-boundary tests for regression target authority."""
from __future__ import annotations

import ast
import csv
import io
import math
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict
import unittest
from unittest.mock import Mock

from fastapi import HTTPException
from pydantic import BaseModel
from starlette.requests import Request

from services.pipeline_env import merge_spec_pipeline_into_config, pipeline_env_from_spec
from services.project_access import require_project_access, session_user


API = Path(__file__).parent


def _load(filename, name, namespace, *, endpoint=False):
    # Like test_vlm_project_access: execute the complete actual function without
    # importing module startup or constructing storage/Azure clients.
    tree = ast.parse((API / filename).read_text())
    node = next(n for n in ast.walk(tree) if isinstance(
        n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    ) and n.name == name)
    if endpoint:
        node.decorator_list = []
        node.args.defaults = []
        for arg in node.args.args:
            arg.annotation = None
        node.returns = None
    exec(compile(ast.Module(body=[node], type_ignores=[]), filename, "exec", dont_inherit=True), namespace)
    return namespace[name]


class RegressionTrainingTargetAuthorityTests(unittest.IsolatedAsyncioTestCase):
    async def _submit(self, spec, config, task="regression"):
        store = Mock()
        store.load_spec.return_value = spec
        store.get_meta.return_value = {
            "owner_email": "owner@example.test",
            "dataset": {"uploaded": True, "validated": True,
                        "storage_key": "projects/p/datasets/data.zip"},
        }
        service = Mock()
        service.submit_training_job.return_value = {"job_id": "offline-job"}
        namespace = {
            "BaseModel": BaseModel, "Dict": Dict, "Any": Any,
            "HTTPException": HTTPException, "datetime": datetime,
            "os": SimpleNamespace(getenv=lambda key, default=None: default),
            "logger": Mock(), "_project_store": store,
            "session_user": session_user, "require_project_access": require_project_access,
            "merge_spec_pipeline_into_config": merge_spec_pipeline_into_config,
            "check_from_request": Mock(return_value={"balance": 100, "required": 1}),
            "ensure_user_row": Mock(return_value=SimpleNamespace(id=1)),
            "configured_vm_size": Mock(return_value="offline-vm"),
            "_use_mock": Mock(return_value=False),
            "_planned_job_id": Mock(return_value="offline-job"),
            "get_ml_service": Mock(return_value=service),
            "get_session_factory": Mock(return_value=Mock(return_value=Mock())),
            "record_usage_event": Mock(), "cost_for": Mock(return_value=1),
            "vm_hourly_usd": Mock(return_value=1),
            # Run the real queued callback synchronously against mocks only.
            "start_submission": Mock(side_effect=lambda job_id, callback: callback()),
        }
        payload_type = _load("routers/training.py", "SubmitTrainingRequest", namespace)
        _load("routers/training.py", "_resolve_dataset", namespace)
        submit = _load("routers/training.py", "submit_training", namespace, endpoint=True)
        payload = payload_type(project_id="p", task_type=task, config=config)
        request = Request({"type": "http", "session": {"user": "owner@example.test"}})
        result = await submit(payload, request, Mock())
        self.assertTrue(result["success"])
        self.assertEqual(result["mode"], "azure")
        namespace["start_submission"].assert_called_once()
        service.submit_training_job.assert_called_once()
        return service.submit_training_job.call_args.kwargs

    async def test_conflicting_target_name(self):
        result = await self._submit({"task_type": "regression", "target_name": "score"},
                                    {"target_name": "value"})
        self.assertEqual(result["config"]["target_name"], "score")

    async def test_omitted_and_falsey_request_name(self):
        for config in ({}, {"target_name": ""}, {"target_name": None}):
            with self.subTest(config=config):
                result = await self._submit({"task_type": "regression", "target_name": "score"}, config)
                self.assertEqual(result["config"]["target_name"], "score")

    async def test_missing_and_empty_persisted_name(self):
        for fields in ({}, {"target_name": ""}):
            with self.subTest(fields=fields):
                result = await self._submit({"task_type": "regression", **fields}, {"target_name": "value"})
                self.assertEqual(result["config"]["target_name"], "target")

    async def test_conflicting_unit_and_name(self):
        result = await self._submit(
            {"task_type": "regression", "target_name": "temperature", "target_unit": "Celsius"},
            {"target_name": "value", "target_unit": "dollars"},
        )
        self.assertEqual(result["config"], {"target_name": "temperature", "target_unit": "Celsius"})

    async def test_empty_or_missing_persisted_unit(self):
        for fields in ({}, {"target_unit": ""}):
            with self.subTest(fields=fields):
                result = await self._submit({"task_type": "regression", **fields}, {"target_unit": "dollars"})
                self.assertEqual(result["config"]["target_unit"], "")

    async def test_no_spec_preserves_request(self):
        for config in ({}, {"target_name": "target"}, {"target_name": "value", "target_unit": "points"}):
            with self.subTest(config=config):
                result = await self._submit(None, config)
                self.assertEqual(result["config"], config)
                self.assertEqual(result["task_type"], "regression")

    async def test_legacy_spec_without_task_uses_existing_branch(self):
        result = await self._submit({"target_name": "score"}, {"target_name": "value"})
        self.assertEqual(result["config"]["target_name"], "score")

    async def test_non_regression_precedence_unchanged(self):
        for task in ("classification", "multi_label", "object_localization", "object_detection"):
            with self.subTest(task=task):
                config = {"target_name": "value", "target_unit": "dollars", "epochs": 2}
                result = await self._submit(
                    {"task_type": task, "target_name": "score", "target_unit": "points"}, config,
                )
                self.assertEqual(result["task_type"], task)
                self.assertEqual(result["config"], config)

    async def test_aml_environment_and_fix4_parser(self):
        resolved = await self._submit(
            {"task_type": "regression", "target_name": "score", "target_unit": "points"},
            {"target_name": "value", "target_unit": "dollars"},
        )
        command = Mock()
        env = {"AZURE_STORAGE_CONNECTION_STRING": "offline-placeholder"}
        namespace = {
            "Any": Any, "Dict": Dict, "Path": Path, "datetime": datetime,
            "__file__": str(API / "services/azure_ml_service.py"),
            "os": SimpleNamespace(getenv=env.get), "logger": Mock(),
            "pipeline_env_from_spec": pipeline_env_from_spec,
            "command": command, "JobResourceConfiguration": Mock(),
        }
        build_job = _load("services/azure_ml_service.py", "submit_training_job", namespace)
        service = Mock(compute_name="offline-compute")
        service.ml_client.jobs.create_or_update.return_value = SimpleNamespace(
            name="offline-job", display_name="offline", status="Queued", experiment_name="offline",
        )
        build_job(service, **resolved)
        service.ml_client.jobs.create_or_update.assert_called_once_with(command.return_value)
        job_env = command.call_args.kwargs["environment_variables"]
        self.assertEqual(job_env["TARGET_NAME"], "score")
        self.assertEqual(job_env["TARGET_UNIT"], "points")
        self.assertIn("python aml_train_regression.py", command.call_args.kwargs["command"])
        parser = _load("training_scripts/aml_train_regression.py", "_parse_targets_csv",
                       {"csv": csv, "io": io, "math": math})
        self.assertEqual(parser(b"image,target,score\na.jpg,1,9\nb.jpg,2,9\n", job_env["TARGET_NAME"]),
                         {"a.jpg": 9.0, "b.jpg": 9.0})


if __name__ == "__main__":
    unittest.main()
