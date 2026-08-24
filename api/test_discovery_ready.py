"""Discovery readiness: every semantic call comes from the model, not from keywords."""

from __future__ import annotations

import unittest

from discovery import (
    assess_discovery_with_llm,
    empty_discovery,
    normalize_discovery,
    resolve_task_type_with_llm,
    slots_support_ready,
    visible_user_turns,
)


def _full_slots(**overrides: bool) -> dict[str, bool]:
    slots = {
        "use_case": True,
        "task_type": True,
        "objects_or_defects": True,
        "environment": True,
        "throughput": True,
    }
    slots.update(overrides)
    return slots


class TranscriptShapeTests(unittest.TestCase):
    def test_internal_prompt_is_not_a_user_turn(self) -> None:
        transcript = [
            {"role": "user", "content": "UI analysis prompt", "internal": True},
            {"role": "assistant", "content": "What should we detect?"},
        ]
        self.assertEqual(visible_user_turns(transcript), 0)

    def test_real_user_turns_are_counted(self) -> None:
        transcript = [
            {"role": "user", "content": "UI analysis prompt", "internal": True},
            {"role": "user", "content": "hello"},
            {"role": "user", "content": "classify metal parts as ok or defective"},
        ]
        self.assertEqual(visible_user_turns(transcript), 2)


class NormalizeReadinessTests(unittest.TestCase):
    def test_model_says_no_substance_keeps_locked(self) -> None:
        raw = {
            "ready_for_config": True,
            "detected_task": "classification",
            "slots": _full_slots(),
            "classes": ["ok", "defect"],
            "progress_percent": 100,
            "user_answered_substantively": False,
            "user_confirmed_summary": False,
        }
        d = normalize_discovery(raw, user_turn_count=4)
        self.assertFalse(d["ready_for_config"])
        self.assertEqual(d["suggested_action"], "continue_chat")

    def test_model_ready_with_substance_unlocks(self) -> None:
        raw = {
            "ready_for_config": True,
            "detected_task": "classification",
            "slots": _full_slots(throughput=False),
            "classes": ["ok", "defect"],
            "progress_percent": 80,
            "user_answered_substantively": True,
        }
        d = normalize_discovery(raw, user_turn_count=3)
        self.assertTrue(d["ready_for_config"])
        self.assertGreaterEqual(d["progress_percent"], 90)
        self.assertTrue(slots_support_ready(d["slots"], task=d["detected_task"]))

    def test_confirmed_summary_counts_as_substance(self) -> None:
        raw = {
            "ready_for_config": True,
            "detected_task": "classification",
            "slots": _full_slots(),
            "classes": ["kingfisher", "carp"],
            "user_answered_substantively": False,
            "user_confirmed_summary": True,
        }
        d = normalize_discovery(raw, user_turn_count=2)
        self.assertTrue(d["ready_for_config"])

    def test_ready_without_slots_is_rejected(self) -> None:
        raw = {
            "ready_for_config": True,
            "detected_task": "classification",
            "slots": _full_slots(environment=False, throughput=False),
            "classes": ["ok", "defect"],
            "user_answered_substantively": True,
        }
        d = normalize_discovery(raw, user_turn_count=2)
        self.assertFalse(d["ready_for_config"])
        self.assertIn("environment", d["missing_slots"])
        self.assertIn("throughput", d["missing_slots"])

    def test_zero_user_turns_never_ready(self) -> None:
        raw = {
            "ready_for_config": True,
            "detected_task": "classification",
            "slots": _full_slots(),
            "classes": ["ok", "defect"],
            "user_answered_substantively": True,
        }
        self.assertFalse(normalize_discovery(raw, user_turn_count=0)["ready_for_config"])

    def test_classes_are_kept_verbatim(self) -> None:
        raw = {
            "ready_for_config": False,
            "detected_task": "classification",
            "slots": _full_slots(),
            "classes": ["drone", "camera drone", "These are photos of birds"],
            "user_answered_substantively": True,
        }
        d = normalize_discovery(raw, user_turn_count=2)
        self.assertEqual(
            d["extracted_labels"],
            ["drone", "camera drone", "These are photos of birds"],
        )


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)


class _FakeCompletions:
    def __init__(self, content: str) -> None:
        self.content = content
        self.last_messages = None
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        self.last_messages = kwargs.get("messages")
        return type("R", (), {"choices": [_FakeChoice(self.content)]})()


class _FakeClient:
    def __init__(self, content: str) -> None:
        self.chat = type("C", (), {"completions": _FakeCompletions(content)})()


class AssessTests(unittest.TestCase):
    def test_no_user_turns_skips_the_model(self) -> None:
        client = _FakeClient("{}")
        d = assess_discovery_with_llm(
            client,
            model="test-model",
            transcript=[{"role": "user", "content": "prompt", "internal": True}],
            assistant_reply="Tell me about your project.",
            token_kwargs={},
        )
        self.assertEqual(d, empty_discovery(0))
        self.assertEqual(client.chat.completions.calls, 0)

    def test_wrap_up_phrase_alone_does_not_unlock(self) -> None:
        client = _FakeClient(
            '{"ready_for_config": false, "detected_task": null, '
            '"slots": {}, "user_answered_substantively": false}'
        )
        d = assess_discovery_with_llm(
            client,
            model="test-model",
            transcript=[{"role": "user", "content": "hello"}],
            assistant_reply="Here's what I suggest: classification. Use Generate Config.",
            token_kwargs={},
        )
        self.assertFalse(d["ready_for_config"])
        self.assertEqual(d["suggested_action"], "continue_chat")

    def test_internal_prompt_is_not_sent_to_the_model(self) -> None:
        client = _FakeClient('{"ready_for_config": false, "slots": {}}')
        assess_discovery_with_llm(
            client,
            model="test-model",
            transcript=[
                {"role": "user", "content": "SECRET UI PROMPT", "internal": True},
                {"role": "user", "content": "classify birds"},
            ],
            assistant_reply="Which species?",
            token_kwargs={},
        )
        sent = client.chat.completions.last_messages[1]["content"]
        self.assertNotIn("SECRET UI PROMPT", sent)
        self.assertIn("classify birds", sent)


class ResolveTaskTypeTests(unittest.TestCase):
    def test_pond_wildlife_correction_uses_vlm_json(self) -> None:
        transcript = [
            {
                "role": "assistant",
                "content": "I suggest multi-label classification for kingfisher and/or carp.",
            },
            {
                "role": "user",
                "content": "I dont want multi-label classification, I want single-label classification",
            },
            {
                "role": "assistant",
                "content": "Here's what I suggest: image classification with kingfisher and carp.",
            },
        ]
        client = _FakeClient('{"task_type": "classification"}')
        task = resolve_task_type_with_llm(
            client,
            model="test-model",
            transcript=transcript,
            token_kwargs={},
        )
        self.assertEqual(task, "classification")
        sent = client.chat.completions.last_messages[1]["content"]
        self.assertIn("I dont want multi-label classification", sent)
        self.assertIn("single-label classification", sent)

    def test_invalid_vlm_task_is_ignored(self) -> None:
        client = _FakeClient('{"task_type": "captioning"}')
        task = resolve_task_type_with_llm(
            client,
            model="test-model",
            transcript=[{"role": "user", "content": "classify birds"}],
            token_kwargs={},
        )
        self.assertIsNone(task)


if __name__ == "__main__":
    unittest.main()
