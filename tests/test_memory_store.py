"""记忆模块单元测试。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from lnagent.cli.commands import CommandAction, parse_command
from lnagent.memory.canon_extractor import merge_hot_canon
from lnagent.memory.models import (
    AdoptRecord,
    ChatMessage,
    HotCanon,
    NovelMeta,
    SceneSession,
    WorldCanon,
)
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
        record = AdoptRecord(
            text="开篇段落。",
            canon_before=HotCanon.empty().to_dict(),
            canon_patch=HotCanon(
                characters=[{"name": "莉亚", "abilities": ["影步"]}]
            ).to_dict(),
            accepted_canon=True,
        )
        session = SceneSession(
            scene_id="scene_001",
            messages=[
                ChatMessage(role="user", content="你好"),
                ChatMessage(role="assistant", content="你好，作者"),
            ],
            adopted_prose="开篇段落。",
            adopt_stack=[record],
        )
        self.store.ensure_project_layout()
        self.store.save_session(session)
        loaded = self.store.load_session()
        self.assertEqual(len(loaded.messages), 2)
        self.assertEqual(loaded.messages[0].content, "你好")
        self.assertEqual(loaded.adopted_prose, "开篇段落。")
        self.assertEqual(len(loaded.adopt_stack), 1)
        self.assertEqual(loaded.adopt_stack[0].text, "开篇段落。")
        self.assertTrue(loaded.adopt_stack[0].accepted_canon)

    def test_load_canon_empty_when_missing(self) -> None:
        canon = self.store.load_canon()
        self.assertEqual(canon, HotCanon.empty())

    def test_append_scene_text_preserves_previous_content(self) -> None:
        self.store.ensure_project_layout()

        self.store.append_scene_text("scene_001", "第一段。")
        self.store.append_scene_text("scene_001", "第二段。")

        manuscript = self.store.project_dir / "manuscript" / "scene_001.md"
        self.assertEqual(manuscript.read_text(encoding="utf-8"), "第一段。\n\n第二段。\n")


class ShortTermBufferTest(unittest.TestCase):
    def test_append_and_to_session(self) -> None:
        buffer = ShortTermBuffer(scene_id="scene_001")
        buffer.append_user("方向：主角进酒馆")
        buffer.append_assistant("候选正文")
        buffer.set_candidate("候选正文")
        record = AdoptRecord(
            text="候选正文",
            canon_before=HotCanon.empty().to_dict(),
            canon_patch=HotCanon.empty().to_dict(),
            accepted_canon=False,
        )
        buffer.append_adopted_prose("候选正文")
        buffer.record_adopt(record)
        buffer.clear_candidate()

        session = buffer.to_session()
        self.assertEqual(len(session.messages), 2)
        self.assertIsNone(buffer.last_candidate)
        self.assertEqual(session.adopted_prose, "候选正文\n")
        self.assertEqual(len(session.adopt_stack), 1)
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

    def test_from_session_restores_adopt_stack(self) -> None:
        record = AdoptRecord(
            text="已采纳正文",
            canon_before=HotCanon.empty().to_dict(),
            canon_patch=HotCanon.empty().to_dict(),
            accepted_canon=True,
        )
        session = SceneSession(messages=[], adopted_prose="已采纳正文\n", adopt_stack=[record])

        buffer = ShortTermBuffer.from_session(session)

        self.assertEqual(len(buffer.adopt_stack), 1)
        self.assertEqual(buffer.adopt_stack[0].text, "已采纳正文")

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

    def test_commit_adopt_accepts_canon_patch_and_clears_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            meta = NovelMeta(title="异世界学院", world_rules=["禁止高阶魔法"], style="轻松")
            session = NovelSession(
                store,
                _FakeModel(),
                meta,
                prompt_builder=_CapturingPromptBuilder(),
                canon_extractor=_FakeCanonExtractor(
                    HotCanon(characters=[{"name": "莉亚", "abilities": ["影步"]}])
                ),
            )
            session.send("写开篇")

            proposal = session.prepare_adopt("莉亚学会了影步。")
            session.commit_adopt(proposal, accepted_canon=True)

            self.assertIsNone(session.last_candidate)
            self.assertEqual(
                (store.project_dir / "manuscript" / "scene_001.md").read_text(
                    encoding="utf-8"
                ),
                "莉亚学会了影步。\n",
            )
            self.assertEqual(store.load_canon().characters[0]["abilities"], ["影步"])
            loaded = store.load_session()
            self.assertEqual(loaded.adopted_prose, "莉亚学会了影步。\n")
            self.assertEqual(len(loaded.adopt_stack), 1)
            self.assertTrue(loaded.adopt_stack[0].accepted_canon)

    def test_commit_adopt_rejects_canon_patch_but_keeps_manuscript(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            meta = NovelMeta(title="异世界学院", world_rules=["禁止高阶魔法"], style="轻松")
            session = NovelSession(
                store,
                _FakeModel(),
                meta,
                prompt_builder=_CapturingPromptBuilder(),
                canon_extractor=_FakeCanonExtractor(
                    HotCanon(world=WorldCanon(rules=["影步会消耗体力"]))
                ),
            )
            session.send("写开篇")

            proposal = session.prepare_adopt("莉亚学会了影步。")
            session.commit_adopt(proposal, accepted_canon=False)

            self.assertEqual(store.load_canon(), HotCanon.empty())
            self.assertEqual(
                (store.project_dir / "manuscript" / "scene_001.md").read_text(
                    encoding="utf-8"
                ),
                "莉亚学会了影步。\n",
            )
            self.assertFalse(store.load_session().adopt_stack[0].accepted_canon)


class HotCanonMergeTest(unittest.TestCase):
    def test_merge_updates_characters_and_deduplicates_arrays(self) -> None:
        base = HotCanon(
            characters=[
                {
                    "name": "莉亚",
                    "abilities": ["影步"],
                    "status": "疲惫",
                    "relationships": {"悠真": "同伴"},
                    "inventory": ["银钥匙"],
                    "location": "旧图书馆",
                }
            ],
            world=WorldCanon(rules=["暗属性魔法会侵蚀记忆"]),
            plot_threads=[{"id": "seal", "status": "open", "note": "钟楼封印"}],
        )
        patch = HotCanon(
            characters=[
                {
                    "name": "莉亚",
                    "abilities": ["影步", "瞬移"],
                    "status": "左臂受伤",
                    "relationships": {"米娜": "老师"},
                    "inventory": ["银钥匙", "黑羽"],
                    "location": "钟楼",
                }
            ],
            world=WorldCanon(rules=["暗属性魔法会侵蚀记忆", "钟声会削弱封印"]),
            plot_threads=[{"id": "seal", "status": "advanced"}],
        )

        merged = merge_hot_canon(base, patch)

        character = merged.characters[0]
        self.assertEqual(character["abilities"], ["影步", "瞬移"])
        self.assertEqual(character["status"], "左臂受伤")
        self.assertEqual(character["relationships"], {"悠真": "同伴", "米娜": "老师"})
        self.assertEqual(character["inventory"], ["银钥匙", "黑羽"])
        self.assertEqual(character["location"], "钟楼")
        self.assertEqual(
            merged.world.rules,
            ["暗属性魔法会侵蚀记忆", "钟声会削弱封印"],
        )
        self.assertEqual(
            merged.plot_threads[0],
            {"id": "seal", "status": "advanced", "note": "钟楼封印"},
        )


class CommandParserTest(unittest.TestCase):
    def test_parse_known_command_aliases(self) -> None:
        self.assertEqual(parse_command("/a").action, CommandAction.ADOPT)
        self.assertEqual(parse_command("/adopt").action, CommandAction.ADOPT)
        self.assertEqual(parse_command("/c").action, CommandAction.CANON)
        self.assertEqual(parse_command("/canon").action, CommandAction.CANON)
        self.assertEqual(parse_command("/h").action, CommandAction.HELP)
        self.assertEqual(parse_command("/help").action, CommandAction.HELP)

    def test_parse_plain_text_as_message(self) -> None:
        parsed = parse_command("继续写主角进酒馆")

        self.assertEqual(parsed.action, CommandAction.MESSAGE)
        self.assertEqual(parsed.text, "继续写主角进酒馆")


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


class _FakeCanonExtractor:
    def __init__(self, patch: HotCanon) -> None:
        self.patch = patch

    def extract_patch(self, adopted_text: str, canon: HotCanon) -> HotCanon:
        return self.patch


if __name__ == "__main__":
    unittest.main()
