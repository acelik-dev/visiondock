"""Offline tests of the real submission handler's dataset reference boundary."""
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Dict
import unittest
from unittest.mock import Mock

from fastapi import HTTPException
from pydantic import BaseModel
from starlette.requests import Request

from services.pipeline_env import merge_spec_pipeline_into_config
from services.project_access import require_project_access, session_user
from test_regression_training_target_authority import _load


CONFLICT = "Dataset reference does not match the project's current validated dataset. Refresh and retry."
MISSING = "Validated dataset reference is missing. Upload and validate the dataset again."
TASKS = ("classification", "multi_label", "regression", "object_localization", "object_detection")


class TrainingDatasetBindingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.store = Mock()
        self.service = Mock()
        self.service.submit_training_job.return_value = {"job_id": "offline-job"}
        self.ns = {
            "BaseModel": BaseModel, "Dict": Dict, "Any": Any,
            "HTTPException": HTTPException, "datetime": datetime,
            "os": SimpleNamespace(getenv=lambda key, default=None: default),
            "logger": Mock(), "_project_store": self.store,
            "session_user": session_user, "require_project_access": require_project_access,
            "merge_spec_pipeline_into_config": merge_spec_pipeline_into_config,
            "check_from_request": Mock(return_value={"balance": 100, "required": 1}),
            "ensure_user_row": Mock(return_value=SimpleNamespace(id=1)),
            "configured_vm_size": Mock(return_value="offline-vm"),
            "_use_mock": Mock(return_value=False),
            "_planned_job_id": Mock(return_value="offline-job"),
            "get_ml_service": Mock(return_value=self.service),
            "get_session_factory": Mock(return_value=Mock(return_value=Mock())),
            "record_usage_event": Mock(), "cost_for": Mock(return_value=1),
            "vm_hourly_usd": Mock(return_value=1),
            "start_submission": Mock(side_effect=lambda job_id, callback: callback()),
        }
        self.payload_type = _load("routers/training.py", "SubmitTrainingRequest", self.ns)
        _load("routers/training.py", "_resolve_dataset", self.ns)
        self.submit = _load("routers/training.py", "submit_training", self.ns, endpoint=True)

    async def _call(self, dataset, *, key="", url="", task="regression", owner="owner@test.local", config=None):
        self.store.get_meta.return_value = {"owner_email": owner, "dataset": dataset}
        self.store.load_spec.return_value = {
            "task_type": task, "target_name": "score", "target_unit": "points",
        }
        payload = self.payload_type(project_id="p", task_type=task,
                                    dataset_blob_key=key, dataset_url=url, config=config or {})
        request = Request({"type": "http", "session": {"user": "owner@test.local"}})
        return await self.submit(payload, request, Mock())

    def _dataset(self, key="validated/A"):
        return {"uploaded": True, "validated": True, "storage_key": key}

    async def _reject(self, dataset, status, detail, **kwargs):
        self.ns["start_submission"].reset_mock()
        self.ns["get_ml_service"].reset_mock()
        self.service.reset_mock()
        self.store.update_meta.reset_mock()
        with self.assertRaises(HTTPException) as caught:
            await self._call(dataset, **kwargs)
        self.assertEqual(caught.exception.status_code, status)
        self.assertEqual(caught.exception.detail, detail)
        self.ns["start_submission"].assert_not_called()
        self.ns["get_ml_service"].assert_not_called()
        self.service.submit_training_job.assert_not_called()
        self.store.update_meta.assert_not_called()

    async def _accept(self, dataset, expected, **kwargs):
        self.ns["start_submission"].reset_mock()
        self.service.reset_mock()
        result = await self._call(dataset, **kwargs)
        self.assertTrue(result["success"])
        self.ns["start_submission"].assert_called_once()
        self.service.submit_training_job.assert_called_once()
        args = self.service.submit_training_job.call_args.kwargs
        self.assertEqual(args["dataset_blob_key"], expected)
        return args

    async def test_conflicts_rejected_for_all_five_tasks(self):
        for task in TASKS:
            with self.subTest(task=task):
                await self._reject(self._dataset(), 409, CONFLICT, task=task,
                                   key="projects/another/datasets/B.zip")

    async def test_matching_and_omitted_keys_for_all_five_tasks(self):
        for task in TASKS:
            canonical = "validated/A/" if task in ("multi_label", "regression") else "validated/A.zip"
            for key in ("", canonical):
                with self.subTest(task=task, key=key):
                    await self._accept(self._dataset(canonical), canonical, key=key, task=task)

    async def test_detection_annotated_and_zip_conflicts(self):
        for task in ("object_detection", "object_localization"):
            for key in ("different/B.zip", "projects/other/datasets/annotated/B"):
                with self.subTest(task=task, key=key):
                    await self._reject(dict(self._dataset(), file_name="A.zip"),
                                       409, CONFLICT, key=key, task=task)

    async def test_unvalidated_gate_precedes_conflict(self):
        for key in ("validated/A", "different/B"):
            with self.subTest(key=key):
                await self._reject(dict(self._dataset(), validated=False), 400,
                                   "Dataset is not validated yet", key=key)

    async def test_missing_dataset_cannot_be_supplied_by_request(self):
        await self._reject({}, 400, "Upload training images before starting training", key="different/B")

    async def test_marketplace_matching_omitted_and_conflicting(self):
        canonical = "shared/marketplace/A"
        dataset = dict(self._dataset(canonical), source="marketplace", marketplace_item_id="catalog-A")
        for key in (canonical, ""):
            with self.subTest(key=key):
                await self._accept(dataset, canonical, key=key)
        await self._reject(dataset, 409, CONFLICT, key="some-other/B")

    async def test_request_url_is_not_used(self):
        for urls in ({}, {"url": "/api/projects/p/dataset/status"},
                     {"blob_url": "https://storage.test/A?sig=new", "url": "/status"}):
            with self.subTest(urls=urls):
                args = await self._accept(dict(self._dataset(), **urls), "validated/A",
                                          url="https://external.test/B?sig=old")
                self.assertEqual(args["dataset_url"], urls.get("blob_url") or urls.get("url") or "")

    async def test_ambiguous_metadata_fails_closed(self):
        for fields in ({}, {"file_name": "targets.csv"},
                       {"mode": "object_detection"},
                       {"source": "marketplace", "mode": "regression", "file_name": "targets.csv"},
                       {"marketplace_item_id": "A", "mode": "classification"}):
            with self.subTest(fields=fields):
                await self._reject({"uploaded": True, "validated": True, **fields},
                                   400, MISSING, key="request/cannot/supply/identity")

    async def test_supported_legacy_layouts(self):
        cases = [
            ({"file_name": "A.zip"}, "projects/p/datasets/raw/A.zip"),
            ({"mode": "classification", "file_name": "A.zip"}, "projects/p/datasets/raw/A.zip"),
            ({"mode": "classification"}, "projects/p/datasets/classification/"),
            ({"mode": "multi_label", "file_name": "labels.csv"}, "projects/p/datasets/multi_label/"),
            ({"mode": "regression", "file_name": "targets.csv"}, "projects/p/datasets/regression/"),
            ({"mode": "object_detection", "file_name": "A.zip"}, "projects/p/datasets/annotated/raw/A.zip"),
            ({"mode": "object_localization", "file_name": "A.zip"}, "projects/p/datasets/annotated/raw/A.zip"),
        ]
        for fields, canonical in cases:
            with self.subTest(fields=fields):
                dataset = {"uploaded": True, "validated": True, **fields}
                await self._accept(dataset, canonical)
                await self._accept(dataset, canonical, key=canonical)
                await self._reject(dataset, 409, CONFLICT, key="different/B")

    async def test_ownership_denial_precedes_resolution(self):
        await self._reject(self._dataset(), 404, "Project not found", owner="another@test.local")
        self.ns["check_from_request"].assert_not_called()
        self.store.load_spec.assert_not_called()

    async def test_fix5_target_semantics_preserved(self):
        args = await self._accept(self._dataset(), "validated/A", key="validated/A",
                                  config={"target_name": "value", "target_unit": "dollars"})
        self.assertEqual(args["config"]["target_name"], "score")
        self.assertEqual(args["config"]["target_unit"], "points")

    async def test_detection_does_not_reresolve_after_binding(self):
        # A changing metadata source must not trigger the old post-resolution
        # detection rewrite. Only ownership and resolution should read metadata.
        for task in ("object_detection", "object_localization"):
            with self.subTest(task=task):
                self.store.get_meta.reset_mock()
                meta = {"owner_email": "owner@test.local", "dataset":
                        dict(self._dataset("shared/A"), file_name="A.zip")}
                self.store.get_meta.side_effect = [meta, meta,
                    {"dataset": dict(self._dataset("different/B.zip"), file_name="B.zip")}]
                await self._accept(meta["dataset"], "shared/A", task=task)
                self.assertEqual(self.store.get_meta.call_count, 2)
                self.store.get_meta.side_effect = None


if __name__ == "__main__":
    unittest.main()
