"""记忆模块单元测试。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from lnagent.memory.models import ChatMessage, HotCanon, NovelMeta, SceneSession
from lnagent.memory.prompt import PromptContextBuilder
from lnagent.memory.short_term import ShortTermBuffer
from lnagent.memory.store import JsonMemoryStore


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
        messages = builder.build(meta=meta, buffer=buffer, user_input="继续写")

        self.assertEqual(len(messages), 4)
        system = messages[0]
        self.assertIsInstance(system, SystemMessage)
        assert isinstance(system.content, str)
        self.assertIn("异世界学院", system.content)
        self.assertIn("已采纳的首段", system.content)
        self.assertIsInstance(messages[-1], HumanMessage)
        self.assertEqual(messages[-1].content, "继续写")


if __name__ == "__main__":
    unittest.main()
