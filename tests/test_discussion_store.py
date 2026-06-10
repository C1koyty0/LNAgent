"""discussion store 单元测试。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lnagent.memory.models import ChatMessage, DiscussionBrief
from lnagent.memory.store import JsonMemoryStore


class DiscussionStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = JsonMemoryStore(Path(self._tmp.name) / "demo")
        self.store.ensure_project_layout()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_ensure_project_layout_creates_discussion_root_only(self) -> None:
        discussion_root = self.store.project_dir / "discussion"
        self.assertTrue(discussion_root.is_dir())
        self.assertFalse((discussion_root / "scene_001").exists())

    def test_load_discussion_messages_returns_empty_when_missing(self) -> None:
        self.assertEqual(self.store.load_discussion_messages("scene_001"), [])

    def test_discussion_messages_round_trip(self) -> None:
        messages = [
            ChatMessage(role="user", content="先讨论一下这一场的节拍"),
            ChatMessage(role="assistant", content="可以先压住信息量，强调不安感。"),
        ]

        self.store.save_discussion_messages("scene_001", messages)
        loaded = self.store.load_discussion_messages("scene_001")

        self.assertEqual([m.to_dict() for m in loaded], [m.to_dict() for m in messages])

    def test_append_discussion_message_preserves_order(self) -> None:
        self.store.append_discussion_message(
            "scene_001", ChatMessage(role="user", content="第一条")
        )
        self.store.append_discussion_message(
            "scene_001", ChatMessage(role="assistant", content="第二条")
        )

        loaded = self.store.load_discussion_messages("scene_001")

        self.assertEqual([m.content for m in loaded], ["第一条", "第二条"])

    def test_load_discussion_brief_returns_empty_when_missing(self) -> None:
        brief = self.store.load_discussion_brief("scene_001")

        self.assertEqual(brief, DiscussionBrief.empty("scene_001"))

    def test_discussion_brief_round_trip(self) -> None:
        brief = DiscussionBrief(
            scene_id="scene_001",
            todo_items=["先写主角的不适应感"],
            constraints=["不要提前揭示徽章来源"],
            open_questions=["导师是否本场出场未定"],
            dirty=True,
            updated_at="2026-06-09T20:55:00+08:00",
        )

        self.store.save_discussion_brief("scene_001", brief)
        loaded = self.store.load_discussion_brief("scene_001")

        self.assertEqual(loaded, brief)

    def test_clear_discussion_messages_does_not_affect_brief(self) -> None:
        self.store.append_discussion_message(
            "scene_001", ChatMessage(role="user", content="保留 brief")
        )
        brief = DiscussionBrief(
            scene_id="scene_001",
            todo_items=["保留这个待写事项"],
            constraints=[],
            open_questions=[],
            dirty=False,
            updated_at="",
        )
        self.store.save_discussion_brief("scene_001", brief)

        self.store.clear_discussion_messages("scene_001")

        self.assertEqual(self.store.load_discussion_messages("scene_001"), [])
        self.assertEqual(self.store.load_discussion_brief("scene_001"), brief)

    def test_clear_discussion_brief_does_not_affect_messages(self) -> None:
        self.store.append_discussion_message(
            "scene_001", ChatMessage(role="user", content="保留 raw chat")
        )
        self.store.save_discussion_brief(
            "scene_001",
            DiscussionBrief(
                scene_id="scene_001",
                todo_items=["待写事项"],
                constraints=[],
                open_questions=[],
                dirty=True,
                updated_at="",
            ),
        )

        self.store.clear_discussion_brief("scene_001")

        loaded_messages = self.store.load_discussion_messages("scene_001")
        loaded_brief = self.store.load_discussion_brief("scene_001")

        self.assertEqual([m.content for m in loaded_messages], ["保留 raw chat"])
        self.assertEqual(loaded_brief, DiscussionBrief.empty("scene_001"))

    def test_clear_discussion_scene_clears_all_discussion_state(self) -> None:
        self.store.append_discussion_message(
            "scene_001", ChatMessage(role="user", content="临时讨论")
        )
        self.store.save_discussion_brief(
            "scene_001",
            DiscussionBrief(
                scene_id="scene_001",
                todo_items=["待写事项"],
                constraints=["限制项"],
                open_questions=["问题"],
                dirty=True,
                updated_at="",
            ),
        )

        self.store.clear_discussion_scene("scene_001")

        self.assertEqual(self.store.load_discussion_messages("scene_001"), [])
        self.assertEqual(
            self.store.load_discussion_brief("scene_001"),
            DiscussionBrief.empty("scene_001"),
        )


if __name__ == "__main__":
    unittest.main()
