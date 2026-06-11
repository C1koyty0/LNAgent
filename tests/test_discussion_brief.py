"""DiscussionBriefRefresher 单元测试。"""

from __future__ import annotations

import unittest
from typing import Any

from lnagent.memory.models import ChatMessage, DiscussionBrief, HotCanon, NovelMeta
from lnagent.memory.discussion_brief import (
    DiscussionBriefRefreshError,
    DiscussionBriefRefresher,
)


class _FakeBriefModel:
    def __init__(self, json_text: str) -> None:
        self._json_text = json_text
        self.invoke_calls: int = 0
        self.last_messages: list[Any] = []

    def invoke(self, messages: list[Any]) -> Any:
        self.invoke_calls += 1
        self.last_messages = messages
        return _FakeResponse(content=self._json_text)


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class DiscussionBriefRefresherTest(unittest.TestCase):
    def test_refresh_parses_valid_json_to_brief(self) -> None:
        model = _FakeBriefModel(
            '{"todo_items":["写开篇"],"constraints":["不要引入新角色"],"open_questions":["导师何时出场"]}'
        )
        refresher = DiscussionBriefRefresher(model)
        meta = NovelMeta(title="书", world_rules=[], style="轻松")

        brief = refresher.refresh(
            scene_id="scene_001",
            messages=[ChatMessage(role="user", content="讨论")],
            meta=meta,
            canon=HotCanon.empty(),
        )

        self.assertEqual(brief.scene_id, "scene_001")
        self.assertEqual(brief.todo_items, ["写开篇"])
        self.assertEqual(brief.constraints, ["不要引入新角色"])
        self.assertEqual(brief.open_questions, ["导师何时出场"])
        self.assertFalse(brief.dirty)
        self.assertTrue(brief.updated_at)

    def test_refresh_defaults_missing_lists_to_empty(self) -> None:
        model = _FakeBriefModel("{}")
        refresher = DiscussionBriefRefresher(model)

        brief = refresher.refresh(
            scene_id="scene_002",
            messages=[ChatMessage(role="user", content="讨论")],
            meta=NovelMeta(title="书", world_rules=[], style="轻松"),
            canon=HotCanon.empty(),
        )

        self.assertEqual(brief.scene_id, "scene_002")
        self.assertEqual(brief.todo_items, [])
        self.assertEqual(brief.constraints, [])
        self.assertEqual(brief.open_questions, [])
        self.assertFalse(brief.dirty)
        self.assertTrue(brief.updated_at)

    def test_refresh_rejects_non_object_root(self) -> None:
        model = _FakeBriefModel('["array", "not", "object"]')
        refresher = DiscussionBriefRefresher(model)

        with self.assertRaises(DiscussionBriefRefreshError):
            refresher.refresh(
                scene_id="scene_003",
                messages=[ChatMessage(role="user", content="讨论")],
                meta=NovelMeta(title="书", world_rules=[], style="轻松"),
                canon=HotCanon.empty(),
            )

    def test_refresh_raises_on_invalid_json(self) -> None:
        model = _FakeBriefModel("not valid json")
        refresher = DiscussionBriefRefresher(model)

        with self.assertRaises(DiscussionBriefRefreshError):
            refresher.refresh(
                scene_id="scene_004",
                messages=[ChatMessage(role="user", content="讨论")],
                meta=NovelMeta(title="书", world_rules=[], style="轻松"),
                canon=HotCanon.empty(),
            )

    def test_refresh_filters_empty_strings_and_non_list_defaults(self) -> None:
        data = (
            '{"todo_items":["写开篇",""],'
            '"constraints":["","不要引入新角色",null,"  "],'
            '"open_questions":"not a list"}'
        )
        model = _FakeBriefModel(data)
        refresher = DiscussionBriefRefresher(model)

        brief = refresher.refresh(
            scene_id="scene_005",
            messages=[ChatMessage(role="user", content="讨论")],
            meta=NovelMeta(title="书", world_rules=[], style="轻松"),
            canon=HotCanon.empty(),
        )

        self.assertEqual(brief.todo_items, ["写开篇"])
        self.assertEqual(brief.constraints, ["不要引入新角色"])
        self.assertEqual(brief.open_questions, [])

    def test_refresh_calls_model_with_prompt(self) -> None:
        model = _FakeBriefModel('{"todo_items":[],"constraints":[],"open_questions":[]}')
        refresher = DiscussionBriefRefresher(model)

        refresher.refresh(
            scene_id="scene_006",
            messages=[ChatMessage(role="user", content="讨论")],
            meta=NovelMeta(title="书", world_rules=[], style="轻松"),
            canon=HotCanon.empty(),
        )

        self.assertEqual(model.invoke_calls, 1)

    def test_refresh_includes_context_in_prompt(self) -> None:
        model = _FakeBriefModel('{"todo_items":[],"constraints":[],"open_questions":[]}')
        refresher = DiscussionBriefRefresher(model)

        meta = NovelMeta(title="测试书", world_rules=["规则"], style="轻松")
        canon = HotCanon.empty()
        canon.characters.append({"name": "主角"})  # type: ignore[arg-type]

        refresher.refresh(
            scene_id="scene_007",
            messages=[
                ChatMessage(role="user", content="讨论一下这段节拍"),
                ChatMessage(role="assistant", content="可以"),
            ],
            meta=meta,
            canon=canon,
            global_summary="全书梗概",
            scene_tail="前文尾巴",
        )

        self.assertEqual(model.invoke_calls, 1)
        messages = model.last_messages
        self.assertEqual(len(messages), 2)
        human_content = messages[1].content

        self.assertIn("测试书", human_content)
        self.assertIn("规则", human_content)
        self.assertIn("主角", human_content)
        self.assertIn("全书梗概", human_content)
        self.assertIn("前文尾巴", human_content)
        self.assertIn("讨论一下这段节拍", human_content)
        self.assertIn("可以", human_content)


if __name__ == "__main__":
    unittest.main()
