"""AML job timing extraction — training credits are billed from this duration."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from services.azure_ml_service import _extract_job_times


class ExtractJobTimesTests(unittest.TestCase):
    def test_dict_properties_from_real_aml_job(self) -> None:
        """Real AML jobs expose timings as a dict with PascalCase UTC strings."""
        job = SimpleNamespace(
            properties={
                "StartTimeUtc": "2026-08-13 08:59:35",
                "EndTimeUtc": "2026-08-13 09:09:30",
            },
            creation_context=SimpleNamespace(created_at="2026-08-13T08:56:32.151405+00:00"),
        )
        times = _extract_job_times(job)
        self.assertEqual(times["duration_seconds"], 595.0)

    def test_mixed_naive_and_aware_timestamps(self) -> None:
        job = SimpleNamespace(
            properties={"EndTimeUtc": "2026-08-13 09:09:30"},
            creation_context=SimpleNamespace(created_at="2026-08-13T08:56:32+00:00"),
        )
        times = _extract_job_times(job)
        self.assertAlmostEqual(times["duration_seconds"], 778.0, places=0)

    def test_iso_duration_property_wins(self) -> None:
        job = SimpleNamespace(
            properties={"duration": "PT16M59.42S"},
            creation_context=SimpleNamespace(created_at=None),
        )
        self.assertAlmostEqual(_extract_job_times(job)["duration_seconds"], 1019.42, places=2)

    def test_running_job_has_no_duration(self) -> None:
        job = SimpleNamespace(
            properties={"StartTimeUtc": "2026-08-13 08:59:35"},
            creation_context=SimpleNamespace(created_at=None),
        )
        self.assertIsNone(_extract_job_times(job)["duration_seconds"])


if __name__ == "__main__":
    unittest.main()
