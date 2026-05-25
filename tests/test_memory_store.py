"""记忆模块单元测试。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from lnagent.memory.models import ChatMessage, HotCanon, NovelMeta, SceneSession, WorldCanon
from lnagent.memory.prompt import PromptContextBuilder
from lnagent.memory.short_term import ShortTermBuffer
from lnagent.memory.store import JsonMemoryStore
from lnagent.session import NovelSession


class JsonMemoryStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = JsonMemoryStore(Path(self._tmp.name) / "demo")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_ensure_project_layout_creates_files(self) -> None:
        self.store.ensure_project_layout()
        self.assertTrue(self.store.project_dir.is_dir())
        self.assertTrue((self.store.project_dir / "meta.json").exists() is False)
        self.assertTrue((self.store.project_dir / "memory" / "canon.json").is_file())
        self.assertTrue((self.store.project_dir / "session.json").is_file())
        self.assertTrue(
            (self.store.project_dir / "manuscript" / "scene_001.md").is_file()
        )

    def test_meta_round_trip(self) -> None:
        meta = NovelMeta(
            title="测试书",
            world_rules=["魔法存在"],
            style="第三人称",
        )
        self.store.ensure_project_layout()
        self.store.save_meta(meta)
        loaded = self.store.load_meta()
        self.assertEqual(loaded.title, "测试书")
        self.assertEqual(loaded.world_rules, ["魔法存在"])
        self.assertEqual(loaded.style, "第三人称")

    def test_session_round_trip(self) -> None:
        session = SceneSession(
            scene_id="scene_001",
            messages=[
                ChatMessage(role="user", content="你好"),
                ChatMessage(role="assistant", content="你好，作者"),
            ],
            adopted_prose="开篇段落。",
        )
        self.store.ensure_project_layout()
        self.store.save_session(session)
        loaded = self.store.load_session()
        self.assertEqual(len(loaded.messages), 2)
        self.assertEqual(loaded.messages[0].content, "你好")
        self.assertEqual(loaded.adopted_prose, "开篇段落。")

    def test_load_canon_empty_when_missing(self) -> None:
        canon = self.store.load_canon()
        self.assertEqual(canon, HotCanon.empty())


class ShortTermBufferTest(unittest.TestCase):
    def test_append_and_to_session(self) -> None:
        buffer = ShortTermBuffer(scene_id="scene_001")
        buffer.append_user("方向：主角进酒馆")
        buffer.append_assistant("候选正文")
        buffer.set_candidate("候选正文")

        session = buffer.to_session()
        self.assertEqual(len(session.messages), 2)
        self.assertEqual(buffer.last_candidate, "候选正文")
        self.assertNotIn("last_candidate", session.to_dict())

    def test_from_session_clears_candidate(self) -> None:
        session = SceneSession(
            messages=[ChatMessage(role="user", content="a")],
            adopted_prose="已写内容",
        )
        buffer = ShortTermBuffer.from_session(session)
        self.assertIsNone(buffer.last_candidate)
        self.assertEqual(buffer.adopted_prose, "已写内容")

    def test_from_session_drops_trailing_assistant_candidate(self) -> None:
        session = SceneSession(
            messages=[
                ChatMessage(role="user", content="写开篇"),
                ChatMessage(role="assistant", content="未采纳候选"),
            ],
            adopted_prose="已写内容",
        )

        buffer = ShortTermBuffer.from_session(session, drop_pending_candidate=True)

        self.assertEqual(len(buffer.messages), 1)
        self.assertEqual(buffer.messages[0].role, "user")
        self.assertEqual(buffer.messages[0].content, "写开篇")
        self.assertEqual(buffer.adopted_prose, "已写内容")
        self.assertIsNone(buffer.last_candidate)

    def test_from_session_keeps_history_when_last_message_is_user(self) -> None:
        session = SceneSession(
            messages=[
                ChatMessage(role="user", content="写开篇"),
                ChatMessage(role="assistant", content="候选正文"),
                ChatMessage(role="user", content="换一种写法"),
            ],
        )

        buffer = ShortTermBuffer.from_session(session, drop_pending_candidate=True)

        self.assertEqual(len(buffer.messages), 3)
        self.assertEqual(buffer.messages[-1].role, "user")
        self.assertEqual(buffer.messages[-1].content, "换一种写法")


class PromptContextBuilderTest(unittest.TestCase):
    def test_build_includes_meta_history_and_user(self) -> None:
        meta = NovelMeta(
            title="异世界学院",
            world_rules=["禁止高阶魔法"],
            style="轻松",
        )
        buffer = ShortTermBuffer(
            scene_id="scene_001",
            messages=[
                ChatMessage(role="user", content="写开篇"),
                ChatMessage(role="assistant", content="从前有一座学院……"),
            ],
            adopted_prose="已采纳的首段。",
        )
        builder = PromptContextBuilder()
        messages = builder.build(
            meta=meta,
            canon=HotCanon.empty(),
            buffer=buffer,
            user_input="继续写",
        )

        self.assertEqual(len(messages), 4)
        system = messages[0]
        self.assertIsInstance(system, SystemMessage)
        assert isinstance(system.content, str)
        self.assertIn("异世界学院", system.content)
        self.assertIn("已采纳的首段", system.content)
        self.assertIsInstance(messages[-1], HumanMessage)
        self.assertEqual(messages[-1].content, "继续写")

    def test_build_includes_hot_canon(self) -> None:
        meta = NovelMeta(
            title="异世界学院",
            world_rules=["禁止高阶魔法"],
            style="轻松",
        )
        canon = HotCanon(
            characters=[
                {
                    "name": "莉亚",
                    "abilities": ["影步"],
                    "status": "左臂受伤",
                    "relationships": {"悠真": "同伴"},
                    "inventory": ["银钥匙"],
                    "location": "旧图书馆",
                }
            ],
            world=WorldCanon(rules=["暗属性魔法会侵蚀记忆"]),
            plot_threads=[{"id": "thread-1", "status": "open", "note": "钟楼封印"}],
        )
        buffer = ShortTermBuffer(scene_id="scene_001")
        builder = PromptContextBuilder()

        messages = builder.build(
            meta=meta,
            canon=canon,
            buffer=buffer,
            user_input="继续写",
        )

        system = messages[0]
        self.assertIsInstance(system, SystemMessage)
        assert isinstance(system.content, str)
        self.assertIn("Hot Canon", system.content)
        self.assertIn("莉亚", system.content)
        self.assertIn("影步", system.content)
        self.assertIn("暗属性魔法会侵蚀记忆", system.content)
        self.assertIn("钟楼封印", system.content)


class NovelSessionTest(unittest.TestCase):
    def test_send_loads_canon_for_prompt_builder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            meta = NovelMeta(title="异世界学院", world_rules=["禁止高阶魔法"], style="轻松")
            canon = HotCanon(
                characters=[{"name": "莉亚", "abilities": ["影步"]}],
                world=WorldCanon(rules=["暗属性魔法会侵蚀记忆"]),
            )
            store.save_canon(canon)
            prompt_builder = _CapturingPromptBuilder()
            session = NovelSession(
                store,
                _FakeModel(),
                meta,
                prompt_builder=prompt_builder,
            )

            reply = session.send("继续写")

            self.assertEqual(reply, "模型回复")
            self.assertEqual(prompt_builder.seen_canon, canon)


class _FakeModel:
    def invoke(self, messages: list[object]) -> object:
        return _FakeResponse(content="模型回复")


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _CapturingPromptBuilder:
    def __init__(self) -> None:
        self.seen_canon: HotCanon | None = None

    def build(
        self,
        *,
        meta: NovelMeta,
        canon: HotCanon,
        buffer: ShortTermBuffer,
        user_input: str,
    ) -> list[HumanMessage]:
        self.seen_canon = canon
        return [HumanMessage(content=user_input)]


if __name__ == "__main__":
    unittest.main()
