"""记忆模块单元测试。"""

from __future__ import annotations

import json
from unittest.mock import patch
import tempfile
import unittest
from datetime import date
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from main import parse_args as parse_main_args
from lnagent.cli.commands import CommandAction, parse_command
from lnagent.cli.config import ConfigCommandError, handle_config_args, run_config
from lnagent.cli.export import export_manuscript
from lnagent.memory.canon_extractor import is_empty_canon_patch, merge_hot_canon
from lnagent.memory.cold_archive import ColdArchiveExtractor, ColdProposal
from lnagent.memory.models import (
    AdoptRecord,
    ChatMessage,
    ColdSynopsis,
    ContextConfig,
    DiscussionBrief,
    HotCanon,
    NovelMeta,
    ProjectConfig,
    SceneSwitchConfig,
    SceneSession,
    SceneSynopsisEntry,
    WorldCanon,
    extract_tail,
    next_scene_id,
    previous_scene_id,
)
from lnagent.memory.prompt import PromptContextBuilder
from lnagent.memory.short_term import ShortTermBuffer, build_prose_from_records
from lnagent.memory.store import JsonMemoryStore
from lnagent.memory.discussion_brief import DiscussionBriefRefresher, DiscussionBriefRefreshError

from lnagent.memory.prompt import PromptContextBuilder
from lnagent.memory.scene_switch import SceneSwitchAdvisor
from lnagent.memory.short_term import ShortTermBuffer, build_prose_from_records
from lnagent.memory.store import JsonMemoryStore
from lnagent.project import collect_novel_meta, load_meta_from_file, open_or_create_project
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
        self.assertTrue((self.store.project_dir / "memory" / "synopsis.json").is_file())
        self.assertTrue((self.store.project_dir / "config.json").is_file())
        self.assertTrue((self.store.project_dir / "session.json").is_file())
        self.assertTrue((self.store.project_dir / "worldbook").is_dir())
        self.assertTrue(
            (self.store.project_dir / "manuscript" / "scene_001.md").is_file()
        )

    def test_meta_round_trip(self) -> None:
        meta = NovelMeta(
            title="测试书",
            world=WorldCanon(rules=["魔法存在"]),
            style="第三人称",
        )
        self.store.ensure_project_layout()
        self.store.save_meta(meta)
        loaded = self.store.load_meta()
        self.assertEqual(loaded.title, "测试书")
        self.assertEqual(loaded.world.rules, ["魔法存在"])
        self.assertEqual(loaded.style, "第三人称")

    def test_novel_meta_rejects_legacy_world_rules_constructor(self) -> None:
        with self.assertRaises(TypeError):
            NovelMeta(
                title="测试书",
                world_rules=["魔法存在"],
                style="第三人称",
            )

    def test_novel_meta_exposes_world_only_without_legacy_property(self) -> None:
        meta = NovelMeta(title="测试书", style="第三人称")

        with self.assertRaises(AttributeError):
            getattr(meta, "world_rules")

    def test_extended_meta_round_trip(self) -> None:
        meta = NovelMeta(
            title="测试书",
            world=WorldCanon(rules=["魔法存在"]),
            style="轻松",
            pov="第一人称",
            tense="现在时",
            taboos=["不写血腥描写"],
            target_audience="轻小说读者",
            narrative_rules=["多用动作推进"],
            genre="校园奇幻",
            tone="温暖明快",
        )
        self.store.ensure_project_layout()
        self.store.save_meta(meta)

        loaded = self.store.load_meta()

        self.assertEqual(loaded.pov, "第一人称")
        self.assertEqual(loaded.tense, "现在时")
        self.assertEqual(loaded.taboos, ["不写血腥描写"])
        self.assertEqual(loaded.target_audience, "轻小说读者")
        self.assertEqual(loaded.narrative_rules, ["多用动作推进"])
        self.assertEqual(loaded.genre, "校园奇幻")
        self.assertEqual(loaded.tone, "温暖明快")

    def test_old_meta_without_extended_fields_defaults_to_empty_values(self) -> None:
        meta = NovelMeta.from_dict(
            {
                "title": "旧书",
                "world_rules": ["旧规则"],
                "style": "轻松",
            }
        )

        self.assertEqual(meta.pov, "")
        self.assertEqual(meta.tense, "")
        self.assertEqual(meta.taboos, [])
        self.assertEqual(meta.target_audience, "")
        self.assertEqual(meta.narrative_rules, [])
        self.assertEqual(meta.genre, "")
        self.assertEqual(meta.tone, "")

    def test_config_round_trip(self) -> None:
        self.store.ensure_project_layout()
        config = ProjectConfig.default()
        config.context.char_budget = 500_000
        config.scene_switch.no_adopt_turns = 5

        self.store.save_config(config)
        loaded = self.store.load_config()

        self.assertEqual(loaded.context.char_budget, 500_000)
        self.assertEqual(loaded.scene_switch.no_adopt_turns, 5)

    def test_load_config_default_when_missing(self) -> None:
        config = self.store.load_config()

        self.assertEqual(config.context.char_budget, 300_000)
        self.assertEqual(config.context.messages_limit, 80_000)
        self.assertEqual(config.scene_switch.min_adopts, 2)
        self.assertEqual(config.scene_switch.no_adopt_turns, 3)

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

    def test_rewrite_scene_manuscript_overwrites_content(self) -> None:
        self.store.ensure_project_layout()
        self.store.append_scene_text("scene_001", "旧正文。")
        self.store.rewrite_scene_manuscript("scene_001", "新正文。\n")

        manuscript = self.store.project_dir / "manuscript" / "scene_001.md"
        self.assertEqual(manuscript.read_text(encoding="utf-8"), "新正文。\n")


class ProjectInitTest(unittest.TestCase):
    def test_load_meta_from_file_reads_extended_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            meta_path = Path(tmp) / "meta.json"
            meta_path.write_text(
                json.dumps(
                    {
                        "title": "测试书",
                        "style": "轻松",
                        "world_rules": ["魔法存在"],
                        "pov": "第一人称",
                        "taboos": ["不写血腥"],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            meta = load_meta_from_file(meta_path)

            self.assertEqual(meta.title, "测试书")
            self.assertEqual(meta.pov, "第一人称")
            self.assertEqual(meta.taboos, ["不写血腥"])

    def test_load_meta_from_file_requires_required_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            meta_path = Path(tmp) / "meta.json"
            meta_path.write_text(
                json.dumps({"title": "测试书", "style": "轻松"}, ensure_ascii=False),
                encoding="utf-8",
            )

            meta = load_meta_from_file(meta_path)

            self.assertEqual(meta.title, "测试书")
            self.assertEqual(meta.style, "轻松")
            self.assertEqual(meta.world.rules, [])

    def test_load_meta_from_file_allows_legacy_world_rules_without_prevalidation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            meta_path = Path(tmp) / "meta.json"
            meta_path.write_text(
                json.dumps(
                    {
                        "title": "测试书",
                        "style": "轻松",
                        "world_rules": ["魔法存在"],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            meta = load_meta_from_file(meta_path)

            self.assertEqual(meta.world.rules, ["魔法存在"])

    def test_load_meta_from_file_ignores_non_list_legacy_world_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            meta_path = Path(tmp) / "meta.json"
            meta_path.write_text(
                json.dumps(
                    {
                        "title": "测试书",
                        "style": "轻松",
                        "world_rules": "魔法存在",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            meta = load_meta_from_file(meta_path)

            self.assertEqual(meta.world.rules, [])

    def test_collect_novel_meta_skips_legacy_world_rules_prompt(self) -> None:
        with patch(
            "builtins.input",
            side_effect=["测试书", "轻松日常"],
        ):
            meta = collect_novel_meta()

        self.assertEqual(meta.title, "测试书")
        self.assertEqual(meta.style, "轻松日常")
        self.assertEqual(meta.world.rules, [])

    def test_open_or_create_project_uses_meta_file_for_new_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            meta_path = root / "meta.json"
            meta_path.write_text(
                json.dumps(
                    {
                        "title": "测试书",
                        "style": "轻松",
                        "world_rules": ["魔法存在"],
                        "genre": "校园奇幻",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            store = JsonMemoryStore(root / "project")

            meta = open_or_create_project(store, meta_path=meta_path)

            self.assertEqual(meta.title, "测试书")
            self.assertEqual(store.load_meta().genre, "校园奇幻")

    def test_open_or_create_project_rejects_meta_file_for_existing_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = JsonMemoryStore(root / "project")
            store.ensure_project_layout()
            store.save_meta(
                NovelMeta(title="旧书", world=WorldCanon(rules=["旧规则"]), style="轻松")
            )
            meta_path = root / "meta.json"
            meta_path.write_text(
                json.dumps(
                    {
                        "title": "新书",
                        "style": "严肃",
                        "world_rules": ["新规则"],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "不能覆盖已有项目"):
                open_or_create_project(store, meta_path=meta_path)

            self.assertEqual(store.load_meta().title, "旧书")


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

    def test_build_prose_from_records_joins_adopts(self) -> None:
        records = [
            AdoptRecord(
                text="第一段。",
                canon_before={},
                canon_patch={},
                accepted_canon=True,
            ),
            AdoptRecord(
                text="第二段。",
                canon_before={},
                canon_patch={},
                accepted_canon=True,
            ),
        ]

        prose = build_prose_from_records(records)

        self.assertEqual(prose, "第一段。\n\n第二段。\n")

    def test_pop_last_adopt_rebuilds_adopted_prose(self) -> None:
        buffer = ShortTermBuffer(scene_id="scene_001")
        for text in ("第一段。", "第二段。"):
            buffer.append_adopted_prose(text)
            buffer.record_adopt(
                AdoptRecord(
                    text=text,
                    canon_before={},
                    canon_patch={},
                    accepted_canon=True,
                )
            )

        popped = buffer.pop_last_adopt()

        self.assertEqual(popped.text, "第二段。")
        self.assertEqual(buffer.adopted_prose, "第一段。\n")
        self.assertEqual(len(buffer.adopt_stack), 1)

    def test_pop_last_adopt_empty_stack_raises(self) -> None:
        buffer = ShortTermBuffer(scene_id="scene_001")

        with self.assertRaisesRegex(ValueError, "没有可撤销的采纳"):
            buffer.pop_last_adopt()


class PromptContextBuilderTest(unittest.TestCase):
    def test_build_includes_meta_history_and_user(self) -> None:
        meta = NovelMeta(
            title="异世界学院",
            world=WorldCanon(rules=["禁止高阶魔法"]),
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
            world=WorldCanon(rules=["禁止高阶魔法"]),
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

    def test_build_new_scene_includes_global_prior_cold_and_tail(self) -> None:
        meta = NovelMeta(title="异世界学院", world=WorldCanon(), style="轻松")
        prior = SceneSynopsisEntry(
            id="scene_001",
            location="酒馆",
            time="雨夜",
            summary="主角抵达酒馆。",
            key_points=["遇见神秘人"],
        )
        builder = PromptContextBuilder()
        messages = builder.build(
            meta=meta,
            canon=HotCanon.empty(),
            buffer=ShortTermBuffer(scene_id="scene_002"),
            user_input="开场",
            global_summary="全书：主角寻找失落的记忆。",
            prior_scene_cold=prior,
            scene_tail="……他推开了门。",
        )

        system = messages[0]
        assert isinstance(system.content, str)
        self.assertIn("全书梗概", system.content)
        self.assertIn("主角寻找失落的记忆", system.content)
        self.assertIn("上一场景归档", system.content)
        self.assertIn("酒馆", system.content)
        self.assertIn("前文衔接", system.content)
        self.assertIn("他推开了门", system.content)
        self.assertNotIn("已采纳正文（当前场景）", system.content)

    def test_build_includes_discussion_writing_boundary_instruction(self) -> None:
        meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
        builder = PromptContextBuilder()

        messages = builder.build(
            meta=meta,
            canon=HotCanon.empty(),
            buffer=ShortTermBuffer(scene_id="scene_001"),
            user_input="讨论一下设定",
        )

        system = messages[0]
        assert isinstance(system.content, str)
        self.assertIn("只有作者通过 /a 采纳的文本才视为正式正文", system.content)
        self.assertIn("讨论区的结论是写作参考", system.content)

    def test_build_includes_non_empty_extended_meta_fields(self) -> None:
        meta = NovelMeta(
            title="书",
            world=WorldCanon(),
            style="轻松",
            pov="第一人称",
            tense="现在时",
            taboos=["不写血腥描写"],
            target_audience="轻小说读者",
            narrative_rules=["多用动作推进"],
            genre="校园奇幻",
            tone="温暖明快",
        )
        builder = PromptContextBuilder()

        messages = builder.build(
            meta=meta,
            canon=HotCanon.empty(),
            buffer=ShortTermBuffer(scene_id="scene_001"),
            user_input="继续",
        )

        system = messages[0]
        assert isinstance(system.content, str)
        self.assertIn("叙述人称：第一人称", system.content)
        self.assertIn("叙事时态：现在时", system.content)
        self.assertIn("禁忌内容", system.content)
        self.assertIn("不写血腥描写", system.content)
        self.assertIn("目标读者：轻小说读者", system.content)
        self.assertIn("叙事规则", system.content)
        self.assertIn("多用动作推进", system.content)
        self.assertIn("题材类型：校园奇幻", system.content)
        self.assertIn("整体语气：温暖明快", system.content)

    def test_build_skips_empty_extended_meta_fields(self) -> None:
        meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
        builder = PromptContextBuilder()

        messages = builder.build(
            meta=meta,
            canon=HotCanon.empty(),
            buffer=ShortTermBuffer(scene_id="scene_001"),
            user_input="继续",
        )

        system = messages[0]
        assert isinstance(system.content, str)
        self.assertNotIn("叙述人称：", system.content)
        self.assertNotIn("叙事时态：", system.content)
        self.assertNotIn("禁忌内容", system.content)
        self.assertNotIn("目标读者：", system.content)
        self.assertNotIn("叙事规则", system.content)
        self.assertNotIn("题材类型：", system.content)
        self.assertNotIn("整体语气：", system.content)

    def test_build_trims_oldest_messages_by_context_config(self) -> None:
        meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
        buffer = ShortTermBuffer(
            scene_id="scene_001",
            messages=[
                ChatMessage(role="user", content="很旧的提问"),
                ChatMessage(role="assistant", content="很旧的回答"),
                ChatMessage(role="user", content="近况"),
                ChatMessage(role="assistant", content="回应"),
            ],
        )
        builder = PromptContextBuilder()

        messages = builder.build(
            meta=meta,
            canon=HotCanon.empty(),
            buffer=buffer,
            user_input="继续",
            context_config=ContextConfig(messages_limit=4),
        )

        contents = [m.content for m in messages]
        self.assertNotIn("很旧的提问", contents)
        self.assertNotIn("很旧的回答", contents)
        self.assertIn("近况", contents)
        self.assertIn("回应", contents)
        self.assertGreater(builder.last_budget_report.clipped_chars["messages"], 0)

    def test_build_trims_adopted_prose_head_by_context_config(self) -> None:
        meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
        buffer = ShortTermBuffer(scene_id="scene_001", adopted_prose="abcdef")
        builder = PromptContextBuilder()

        messages = builder.build(
            meta=meta,
            canon=HotCanon.empty(),
            buffer=buffer,
            user_input="继续",
            context_config=ContextConfig(adopted_prose_limit=3),
        )

        system = messages[0]
        assert isinstance(system.content, str)
        self.assertIn("def", system.content)
        self.assertNotIn("abcdef", system.content)
        self.assertEqual(builder.last_budget_report.clipped_chars["adopted_prose"], 3)

    def test_build_applies_total_budget_after_block_limits(self) -> None:
        meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
        buffer = ShortTermBuffer(
            scene_id="scene_001",
            messages=[ChatMessage(role="user", content="旧" * 500)],
            adopted_prose="文" * 500,
        )
        builder = PromptContextBuilder()

        messages = builder.build(
            meta=meta,
            canon=HotCanon.empty(),
            buffer=buffer,
            user_input="继续",
            context_config=ContextConfig(
                char_budget=600,
                messages_limit=500,
                adopted_prose_limit=500,
            ),
        )

        total_chars = sum(len(str(message.content)) for message in messages)
        self.assertLessEqual(total_chars, 600)
        self.assertTrue(builder.last_budget_report.has_clipping)

    # ── D1: dual-track prompt builder ──

    def test_build_writing_injects_brief_block(self) -> None:
        meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
        brief = DiscussionBrief(
            scene_id="scene_001",
            todo_items=["先写主角的不适应感"],
            constraints=["不要提前揭示徽章来源"],
            open_questions=["导师是否本场出场未定"],
            dirty=True,
            updated_at="",
        )
        builder = PromptContextBuilder()

        messages = builder.build_writing(
            meta=meta,
            canon=HotCanon.empty(),
            buffer=ShortTermBuffer(scene_id="scene_001"),
            user_input="继续写",
            discussion_brief=brief,
        )

        system = messages[0]
        assert isinstance(system.content, str)
        self.assertIn("当前场景讨论结论", system.content)
        self.assertIn("先写主角的不适应感", system.content)
        self.assertIn("不要提前揭示徽章来源", system.content)
        self.assertIn("导师是否本场出场未定", system.content)

    def test_build_writing_no_empty_brief_block_when_none(self) -> None:
        meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
        builder = PromptContextBuilder()

        messages = builder.build_writing(
            meta=meta,
            canon=HotCanon.empty(),
            buffer=ShortTermBuffer(scene_id="scene_001"),
            user_input="继续写",
            discussion_brief=None,
        )

        system = messages[0]
        assert isinstance(system.content, str)
        self.assertNotIn("当前场景讨论结论", system.content)

    def test_build_discussion_uses_discussion_instructions(self) -> None:
        meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
        builder = PromptContextBuilder()

        messages = builder.build_discussion(
            meta=meta,
            canon=HotCanon.empty(),
            buffer=ShortTermBuffer(scene_id="scene_001"),
            user_input="讨论一下节拍",
        )

        system = messages[0]
        assert isinstance(system.content, str)
        self.assertNotIn(
            "区分“写作任务”和“讨论任务”", system.content,
        )

    def test_build_discussion_excludes_adopted_prose(self) -> None:
        meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
        buffer = ShortTermBuffer(
            scene_id="scene_001",
            adopted_prose="已采纳的正文。",
        )
        builder = PromptContextBuilder()

        messages = builder.build_discussion(
            meta=meta,
            canon=HotCanon.empty(),
            buffer=buffer,
            user_input="讨论一下节拍",
        )

        system = messages[0]
        assert isinstance(system.content, str)
        self.assertNotIn("已采纳正文（当前场景）", system.content)

    def test_build_discussion_includes_scene_tail(self) -> None:
        meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
        builder = PromptContextBuilder()

        messages = builder.build_discussion(
            meta=meta,
            canon=HotCanon.empty(),
            buffer=ShortTermBuffer(scene_id="scene_001"),
            user_input="讨论一下节拍",
            scene_tail="……他推开了门。",
        )

        system = messages[0]
        assert isinstance(system.content, str)
        self.assertIn("前文衔接", system.content)
        self.assertIn("他推开了门", system.content)

    def test_build_writing_preserves_block_order(self) -> None:
        meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
        brief = DiscussionBrief(
            scene_id="scene_001",
            todo_items=["待写事项"],
            constraints=["约束项"],
            open_questions=[],
        )
        builder = PromptContextBuilder()

        messages = builder.build_writing(
            meta=meta,
            canon=HotCanon.empty(),
            buffer=ShortTermBuffer(scene_id="scene_001", adopted_prose="正文。"),
            user_input="继续写",
            discussion_brief=brief,
        )

        system = messages[0]
        assert isinstance(system.content, str)
        brief_pos = system.content.index("当前场景讨论结论")
        prose_pos = system.content.index("已采纳正文（当前场景）")
        self.assertLess(brief_pos, prose_pos)

    def test_build_is_compat_alias_for_build_writing(self) -> None:
        meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
        brief = DiscussionBrief(
            scene_id="scene_001",
            todo_items=["待写事项"],
            constraints=["约束"],
            open_questions=[],
        )
        builder = PromptContextBuilder()

        compat_messages = builder.build(
            meta=meta,
            canon=HotCanon.empty(),
            buffer=ShortTermBuffer(scene_id="scene_001"),
            user_input="继续",
        )

        writing_messages = builder.build_writing(
            meta=meta,
            canon=HotCanon.empty(),
            buffer=ShortTermBuffer(scene_id="scene_001"),
            user_input="继续",
            discussion_brief=None,
        )

        self.assertEqual(
            [m.content for m in compat_messages],
            [m.content for m in writing_messages],
        )


class SceneSwitchAdvisorTest(unittest.TestCase):
    def test_suggests_when_min_adopts_reached(self) -> None:
        advisor = SceneSwitchAdvisor(SceneSwitchConfig(min_adopts=2, no_adopt_turns=3))

        suggestion = advisor.suggest(adopt_count=2, turns_since_last_adopt=0)

        self.assertTrue(suggestion.should_suggest)

    def test_suggests_when_no_adopt_turns_reached(self) -> None:
        advisor = SceneSwitchAdvisor(SceneSwitchConfig(min_adopts=2, no_adopt_turns=3))

        suggestion = advisor.suggest(adopt_count=0, turns_since_last_adopt=3)

        self.assertTrue(suggestion.should_suggest)

    def test_does_not_suggest_below_thresholds(self) -> None:
        advisor = SceneSwitchAdvisor(SceneSwitchConfig(min_adopts=2, no_adopt_turns=3))

        suggestion = advisor.suggest(adopt_count=1, turns_since_last_adopt=2)

        self.assertFalse(suggestion.should_suggest)


class SceneIdUtilTest(unittest.TestCase):
    def test_next_and_previous_scene_id(self) -> None:
        self.assertEqual(next_scene_id("scene_001"), "scene_002")
        self.assertEqual(previous_scene_id("scene_002"), "scene_001")
        self.assertIsNone(previous_scene_id("scene_001"))

    def test_extract_tail_limits_characters(self) -> None:
        text = "甲" * 600
        tail = extract_tail(text, limit=500)
        self.assertEqual(len(tail), 500)
        self.assertTrue(text.endswith(tail))


class SynopsisStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = JsonMemoryStore(Path(self._tmp.name) / "demo")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_synopsis_round_trip(self) -> None:
        self.store.ensure_project_layout()
        synopsis = ColdSynopsis(
            global_summary="全书梗概",
            scenes=[
                SceneSynopsisEntry(
                    id="scene_001",
                    location="酒馆",
                    time="雨夜",
                    summary="抵达酒馆。",
                    key_points=["伏笔A"],
                )
            ],
        )
        self.store.save_synopsis(synopsis)
        loaded = self.store.load_synopsis()
        self.assertEqual(loaded.global_summary, "全书梗概")
        self.assertEqual(loaded.scenes[0].location, "酒馆")

    def test_read_scene_tail_from_manuscript(self) -> None:
        self.store.ensure_project_layout()
        long_text = "段。" * 300
        self.store.append_scene_text("scene_001", long_text)
        tail = self.store.read_scene_tail("scene_001")
        self.assertEqual(len(tail), 500)


class ExportManuscriptTest(unittest.TestCase):
    def test_export_manuscript_writes_scenes_in_number_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            store.rewrite_scene_manuscript("scene_002", "第二场。")
            store.rewrite_scene_manuscript("scene_001", "第一场。")

            output = export_manuscript(store, today=date(2026, 5, 27))

            self.assertEqual(output, store.project_dir / "exports" / "2026-05-27.md")
            self.assertEqual(
                output.read_text(encoding="utf-8"),
                "## Scene 001\n\n第一场。\n\n## Scene 002\n\n第二场。\n",
            )

    def test_export_manuscript_skips_empty_scenes_and_uses_unique_default_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            store.rewrite_scene_manuscript("scene_001", "")
            store.rewrite_scene_manuscript("scene_002", "第二场。")
            exports_dir = store.project_dir / "exports"
            exports_dir.mkdir(parents=True)
            (exports_dir / "2026-05-27.md").write_text("旧导出", encoding="utf-8")

            output = export_manuscript(store, today=date(2026, 5, 27))

            self.assertEqual(output, exports_dir / "2026-05-27-2.md")
            self.assertEqual(
                output.read_text(encoding="utf-8"),
                "## Scene 002\n\n第二场。\n",
            )

    def test_export_manuscript_uses_explicit_project_relative_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            store.rewrite_scene_manuscript("scene_001", "第一场。")

            output = export_manuscript(store, output_path=Path("drafts/book.md"))

            self.assertEqual(output, store.project_dir / "drafts" / "book.md")
            self.assertEqual(
                output.read_text(encoding="utf-8"),
                "## Scene 001\n\n第一场。\n",
            )

    def test_export_manuscript_raises_when_all_scenes_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()

            with self.assertRaisesRegex(ValueError, "没有可导出的正文"):
                export_manuscript(store, today=date(2026, 5, 27))


class CountingMemoryStore(JsonMemoryStore):
    def __init__(self, project_dir: Path) -> None:
        super().__init__(project_dir)
        self.save_session_count = 0

    def save_session(self, session: SceneSession) -> None:
        self.save_session_count += 1
        super().save_session(session)


class SessionCheckpointPersistTest(unittest.TestCase):
    def test_send_does_not_persist_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = CountingMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
            session = NovelSession(store, _FakeModel(), meta)
            store.save_session_count = 0

            session.send("第一轮")
            session.send("第二轮")

            self.assertEqual(store.save_session_count, 0)

    def test_commit_adopt_persists_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = CountingMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
            session = NovelSession(
                store,
                _FakeModel(),
                meta,
                canon_extractor=_FakeCanonExtractor(HotCanon.empty()),
            )
            session.send("写开篇")
            session.commit_adopt(
                session.prepare_adopt("正文。"),
                accepted_canon=False,
            )

            self.assertGreaterEqual(store.save_session_count, 1)
            self.assertEqual(len(store.load_session().messages), 2)

    def test_session_save_after_send_persists_messages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
            session = NovelSession(store, _FakeModel(), meta)
            session.send("写开篇")

            session.save()

            reloaded = NovelSession(store, _FakeModel(), meta)
            self.assertEqual(len(reloaded.adopt_stack), 0)
            loaded = store.load_session()
            self.assertEqual(len(loaded.messages), 2)

    def test_send_without_checkpoint_leaves_disk_session_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
            session = NovelSession(store, _FakeModel(), meta)
            session.send("写开篇")

            reloaded = NovelSession(store, _FakeModel(), meta)
            loaded = store.load_session()

            self.assertEqual(loaded.messages, [])
            self.assertEqual(len(reloaded.adopt_stack), 0)


class ColdArchiveExtractorTest(unittest.TestCase):
    def test_propose_parses_json(self) -> None:
        payload = (
            '{"location":"钟楼","time":"午夜","summary":"封印动摇。",'
            '"key_points":["钟声"]}'
        )
        extractor = ColdArchiveExtractor(_JsonColdModel(propose_content=payload))
        proposal = extractor.propose("scene_001", "正文内容。")
        self.assertEqual(proposal.location, "钟楼")
        self.assertEqual(proposal.summary, "封印动摇。")

    def test_rollup_global_returns_text(self) -> None:
        extractor = ColdArchiveExtractor(_FixedResponseModel("更新后的全书梗概。"))
        entry = SceneSynopsisEntry(
            id="scene_001",
            location="钟楼",
            time="午夜",
            summary="封印动摇。",
        )
        result = extractor.rollup_global("旧梗概", entry)
        self.assertEqual(result, "更新后的全书梗概。")


class NovelSessionTest(unittest.TestCase):
    def test_session_loads_project_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            config = ProjectConfig.default()
            config.context.char_budget = 500_000
            store.save_config(config)
            meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")

            session = NovelSession(store, _FakeModel(), meta)

            self.assertEqual(session.config.context.char_budget, 500_000)

    def test_session_update_config_persists_immediately(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
            session = NovelSession(store, _FakeModel(), meta)
            config = ProjectConfig.default()
            config.scene_switch.min_adopts = 4

            session.update_config(config)

            self.assertEqual(session.config.scene_switch.min_adopts, 4)
            self.assertEqual(store.load_config().scene_switch.min_adopts, 4)

    def test_session_reset_config_persists_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
            session = NovelSession(store, _FakeModel(), meta)
            config = ProjectConfig.default()
            config.scene_switch.no_adopt_turns = 9
            session.update_config(config)

            session.reset_config()

            self.assertEqual(session.config.scene_switch.no_adopt_turns, 3)
            self.assertEqual(store.load_config().scene_switch.no_adopt_turns, 3)

    def test_send_loads_canon_for_prompt_builder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            meta = NovelMeta(
                title="异世界学院",
                world=WorldCanon(rules=["禁止高阶魔法"]),
                style="轻松",
            )
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
            self.assertIsNotNone(prompt_builder.seen_canon)
            seen = prompt_builder.seen_canon
            assert seen is not None
            self.assertEqual(seen.characters[0]["name"], "莉亚")
            self.assertEqual(seen.characters[0]["abilities"][0]["id"], "影步")

    def test_send_passes_project_context_config_to_prompt_builder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            config = ProjectConfig.default()
            config.context.char_budget = 500_000
            store.save_config(config)
            meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
            prompt_builder = _CapturingPromptBuilder()
            session = NovelSession(
                store,
                _FakeModel(),
                meta,
                prompt_builder=prompt_builder,
            )

            session.send("继续写")

            self.assertIsNotNone(prompt_builder.seen_context_config)
            self.assertEqual(prompt_builder.seen_context_config.char_budget, 500_000)

    def test_session_loads_scene_tail_with_configured_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            config = ProjectConfig.default()
            config.context.scene_tail_limit = 800
            store.save_config(config)
            store.rewrite_scene_manuscript("scene_001", "甲" * 1_000)
            store.save_session(SceneSession(scene_id="scene_002"))
            meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
            prompt_builder = _CapturingPromptBuilder()
            session = NovelSession(
                store,
                _FakeModel(),
                meta,
                prompt_builder=prompt_builder,
            )

            session.send("开场")

            self.assertEqual(len(prompt_builder.seen_scene_tail or ""), 800)

    def test_send_tracks_turns_since_last_adopt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
            session = NovelSession(
                store,
                _FakeModel(),
                meta,
                canon_extractor=_FakeCanonExtractor(HotCanon.empty()),
            )

            session.send("写开篇")
            session.send("再换一种")

            self.assertEqual(session.turns_since_last_adopt, 2)

            session.commit_adopt(
                session.prepare_adopt("正文。"),
                accepted_canon=False,
            )

            self.assertEqual(session.turns_since_last_adopt, 0)

    def test_send_is_compat_alias_for_writing_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
            prompt_builder = _CapturingPromptBuilder()
            session = NovelSession(
                store,
                _FixedResponseModel("写作回复"),
                meta,
                prompt_builder=prompt_builder,
            )

            reply = session.send("继续写")

            self.assertEqual(reply, "写作回复")
            self.assertIn("build_writing", prompt_builder.build_calls)
            self.assertEqual(session.last_candidate, "写作回复")

    def test_send_discussion_does_not_update_last_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
            session = NovelSession(
                store,
                _SequenceResponseModel(["写作回复", "讨论回复"]),
                meta,
            )
            session.send("写开篇")
            self.assertEqual(session.last_candidate, "写作回复")

            reply = session.send_discussion("讨论一下这段节拍")

            self.assertEqual(reply, "讨论回复")
            self.assertEqual(session.last_candidate, "写作回复")

    def test_send_discussion_does_not_increment_turns_since_last_adopt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
            session = NovelSession(
                store,
                _SequenceResponseModel(["写作回复", "讨论回复"]),
                meta,
            )
            session.send("写开篇")
            turns_before = session.turns_since_last_adopt

            session.send_discussion("讨论一下这段节拍")

            self.assertEqual(session.turns_since_last_adopt, turns_before)

    def test_send_discussion_persists_raw_messages_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
            session = NovelSession(store, _FixedResponseModel("讨论回复"), meta)

            session.send_discussion("讨论一下这段节拍")

            messages = store.load_discussion_messages("scene_001")
            self.assertEqual(len(messages), 2)
            self.assertEqual(messages[0].role, "user")
            self.assertEqual(messages[0].content, "讨论一下这段节拍")
            self.assertEqual(messages[1].role, "assistant")
            self.assertEqual(messages[1].content, "讨论回复")
            self.assertEqual(store.load_session().messages, [])

    def test_send_discussion_does_not_pollute_writing_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
            prompt_builder = _CapturingPromptBuilder()
            session = NovelSession(
                store,
                _FixedResponseModel("讨论回复"),
                meta,
                prompt_builder=prompt_builder,
            )

            session.send_discussion("讨论一下这段节拍")

            self.assertEqual(prompt_builder.seen_discussion_buffer_messages or [], [])
            self.assertEqual(store.load_session().messages, [])

    def test_stream_send_discussion_persists_raw_messages_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
            session = NovelSession(store, _StreamingModel(["讨论", "回复"]), meta)

            chunks = list(session.stream_send_discussion("讨论一下这段节拍"))

            self.assertEqual(chunks, ["讨论", "回复"])
            messages = store.load_discussion_messages("scene_001")
            self.assertEqual(messages[-1].content, "讨论回复")
            self.assertEqual(store.load_session().messages, [])

    def test_discussion_prompt_reads_discussion_raw_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            store.append_discussion_message(
                "scene_001",
                ChatMessage(role="user", content="先前讨论"),
            )
            store.save_session(
                SceneSession(
                    scene_id="scene_001",
                    messages=[ChatMessage(role="user", content="写作用历史")],
                )
            )
            meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
            prompt_builder = _CapturingPromptBuilder()
            session = NovelSession(
                store,
                _FixedResponseModel("讨论回复"),
                meta,
                prompt_builder=prompt_builder,
            )

            session.send_discussion("讨论一下这段节拍")

            seen = prompt_builder.seen_discussion_buffer_messages or []
            self.assertEqual(len(seen), 1)
            self.assertEqual(seen[0].content, "先前讨论")

    # ── D3: discussion dirty + auto-refresh bridge ──

    def test_send_discussion_marks_brief_dirty_and_refreshes_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
            session = NovelSession(
                store,
                _FixedResponseModel("讨论回复"),
                meta,
            )

            session.send_discussion("讨论一下这段节拍")

            brief = store.load_discussion_brief("scene_001")
            self.assertTrue(brief.dirty)
            self.assertTrue(brief.updated_at)

    def test_send_writing_refreshes_dirty_brief_before_building_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
            refresher = _FakeBriefRefresher()
            prompt_builder = _CapturingPromptBuilder()
            session = NovelSession(
                store,
                _SequenceResponseModel(["写作回复"]),
                meta,
                prompt_builder=prompt_builder,
                discussion_brief_refresher=refresher,
            )

            session.send_discussion("讨论")
            self.assertTrue(store.load_discussion_brief("scene_001").dirty)

            session.send_writing("继续写")

            self.assertEqual(refresher.refresh_calls, 1)
            self.assertTrue(prompt_builder.seen_discussion_brief is not None)
            self.assertFalse(
                prompt_builder.seen_discussion_brief.dirty  # type: ignore[union-attr]
            )

    def test_send_writing_uses_clean_brief_without_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
            refresher = _FakeBriefRefresher()
            prompt_builder = _CapturingPromptBuilder()
            session = NovelSession(
                store,
                _SequenceResponseModel(["写作回复"]),
                meta,
                prompt_builder=prompt_builder,
                discussion_brief_refresher=refresher,
            )

            clean_brief = DiscussionBrief(
                scene_id="scene_001",
                todo_items=["写开篇"],
                constraints=[],
                open_questions=[],
                dirty=False,
                updated_at="2026-01-01T00:00:00Z",
            )
            store.save_discussion_brief("scene_001", clean_brief)

            session.send_writing("继续写")

            self.assertEqual(refresher.refresh_calls, 0)

    def test_send_writing_falls_back_to_old_brief_when_refresh_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
            refresher = _FakeBriefRefresher(should_fail=True)
            prompt_builder = _CapturingPromptBuilder()
            session = NovelSession(
                store,
                _SequenceResponseModel(["写作回复"]),
                meta,
                prompt_builder=prompt_builder,
                discussion_brief_refresher=refresher,
            )

            old_brief = DiscussionBrief(
                scene_id="scene_001",
                todo_items=["旧待写事项"],
                constraints=["旧约束"],
                open_questions=[],
                dirty=False,
                updated_at="2026-01-01T00:00:00Z",
            )
            store.save_discussion_brief("scene_001", old_brief)

            session.send_discussion("讨论")

            reply = session.send_writing("继续写")

            self.assertEqual(reply, "写作回复")
            self.assertEqual(refresher.refresh_calls, 1)
            seen = prompt_builder.seen_discussion_brief
            self.assertIsNotNone(seen)
            self.assertEqual(seen.todo_items, ["旧待写事项"])  # type: ignore[union-attr]

    def test_send_writing_without_raw_discussion_skips_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
            refresher = _FakeBriefRefresher()
            session = NovelSession(
                store,
                _SequenceResponseModel(["写作回复"]),
                meta,
                discussion_brief_refresher=refresher,
            )

            session.send_writing("继续写")

            self.assertEqual(refresher.refresh_calls, 0)

    def test_stream_send_writing_also_refreshes_dirty_brief(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
            refresher = _FakeBriefRefresher()
            session = NovelSession(
                store,
                _StreamingModel(["写", "作", "回复"]),
                meta,
                discussion_brief_refresher=refresher,
            )

            session.send_discussion("讨论")

            chunks = list(session.stream_send_writing("继续写"))

            self.assertEqual("".join(chunks), "写作回复")
            self.assertEqual(refresher.refresh_calls, 1)

    def test_commit_adopt_accepts_canon_patch_and_clears_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            meta = NovelMeta(
                title="异世界学院",
                world=WorldCanon(rules=["禁止高阶魔法"]),
                style="轻松",
            )
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
            abilities = store.load_canon().characters[0]["abilities"]
            self.assertEqual(abilities[0]["id"], "影步")
            loaded = store.load_session()
            self.assertEqual(loaded.adopted_prose, "莉亚学会了影步。\n")
            self.assertEqual(len(loaded.adopt_stack), 1)
            self.assertTrue(loaded.adopt_stack[0].accepted_canon)
            self.assertEqual(store.load_discussion_messages("scene_001"), [])

    def test_commit_adopt_preserves_discussion_brief(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            meta = NovelMeta(
                title="异世界学院",
                world=WorldCanon(rules=["禁止高阶魔法"]),
                style="轻松",
            )
            session = NovelSession(
                store,
                _FakeModel(),
                meta,
                prompt_builder=_CapturingPromptBuilder(),
                canon_extractor=_FakeCanonExtractor(HotCanon.empty()),
            )
            session.send_discussion("讨论一下这段节拍")
            brief = DiscussionBrief(
                scene_id="scene_001",
                todo_items=["写开篇"],
                constraints=["不要引入新角色"],
                open_questions=[],
                dirty=False,
                updated_at="2026-06-10T00:00:00Z",
            )
            store.save_discussion_brief("scene_001", brief)
            session.send("写开篇")

            proposal = session.prepare_adopt("莉亚学会了影步。")
            session.commit_adopt(proposal, accepted_canon=True)

            self.assertEqual(store.load_discussion_messages("scene_001"), [])
            loaded_brief = store.load_discussion_brief("scene_001")
            self.assertEqual(loaded_brief.todo_items, ["写开篇"])
            self.assertEqual(loaded_brief.constraints, ["不要引入新角色"])

    def test_undo_does_not_restore_discussion_messages_after_adopt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            meta = NovelMeta(
                title="异世界学院",
                world=WorldCanon(rules=["禁止高阶魔法"]),
                style="轻松",
            )
            session = NovelSession(
                store,
                _FakeModel(),
                meta,
                prompt_builder=_CapturingPromptBuilder(),
                canon_extractor=_FakeCanonExtractor(HotCanon.empty()),
            )
            session.send_discussion("讨论一下这段节拍")
            session.send("写开篇")

            proposal = session.prepare_adopt("莉亚学会了影步。")
            session.commit_adopt(proposal, accepted_canon=True)
            session.undo_last_adopt()

            self.assertEqual(store.load_discussion_messages("scene_001"), [])

    def test_commit_adopt_rejects_canon_patch_but_keeps_manuscript(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            meta = NovelMeta(
                title="异世界学院",
                world=WorldCanon(rules=["禁止高阶魔法"]),
                style="轻松",
            )
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

    def test_apply_reconcile_accepts_canon(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
            patch = HotCanon(characters=[{"name": "莉亚", "abilities": ["影步"]}])
            session = NovelSession(
                store,
                _FakeModel(),
                meta,
                canon_extractor=_FakeCanonExtractor(patch),
            )
            session.commit_adopt(
                session.prepare_adopt("正文。"),
                accepted_canon=False,
            )
            items = session.pending_reconcile_items()
            self.assertEqual(len(items), 1)
            session.apply_reconcile(items[0], accepted_canon=True)
            self.assertEqual(
                store.load_canon().characters[0]["abilities"][0]["id"],
                "影步",
            )
            self.assertTrue(store.load_session().adopt_stack[0].accepted_canon)

    def test_finish_scene_switch_accept_writes_synopsis_and_advances_scene(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
            cold = _FakeColdExtractor(
                ColdProposal(
                    location="酒馆",
                    time="雨夜",
                    summary="提案摘要",
                    key_points=["要点"],
                ),
                rollup="新的全书梗概",
            )
            session = NovelSession(
                store,
                _FakeModel(),
                meta,
                canon_extractor=_FakeCanonExtractor(HotCanon.empty()),
                cold_extractor=cold,
            )
            session.commit_adopt(
                session.prepare_adopt("第一段。"),
                accepted_canon=True,
            )
            proposal = session.prepare_cold_proposal()
            new_id = session.finish_scene_switch(
                proposal,
                cold_accepted=True,
                summary="作者确认的摘要",
            )
            self.assertEqual(new_id, "scene_002")
            synopsis = store.load_synopsis()
            self.assertEqual(len(synopsis.scenes), 1)
            self.assertEqual(synopsis.scenes[0].summary, "作者确认的摘要")
            self.assertEqual(synopsis.scenes[0].location, "酒馆")
            self.assertEqual(synopsis.global_summary, "新的全书梗概")
            loaded = store.load_session()
            self.assertEqual(loaded.scene_id, "scene_002")
            self.assertEqual(loaded.adopted_prose, "")
            self.assertEqual(loaded.adopt_stack, [])

    def test_finish_scene_switch_reject_skips_synopsis_but_advances_scene(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
            session = NovelSession(
                store,
                _FakeModel(),
                meta,
                canon_extractor=_FakeCanonExtractor(HotCanon.empty()),
                cold_extractor=_FakeColdExtractor(
                    ColdProposal(
                        location="酒馆",
                        time="雨夜",
                        summary="提案",
                        key_points=[],
                    )
                ),
            )
            session.commit_adopt(
                session.prepare_adopt("第一段。"),
                accepted_canon=True,
            )
            proposal = session.prepare_cold_proposal()
            new_id = session.finish_scene_switch(
                proposal,
                cold_accepted=False,
                summary="",
            )
            self.assertEqual(new_id, "scene_002")
            self.assertEqual(store.load_synopsis().scenes, [])
            self.assertEqual(store.load_session().scene_id, "scene_002")

    def test_undo_single_adopt_rolls_back_prose_and_canon(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
            patch = HotCanon(characters=[{"name": "莉亚", "abilities": ["影步"]}])
            session = NovelSession(
                store,
                _FakeModel(),
                meta,
                canon_extractor=_FakeCanonExtractor(patch),
            )
            session.send("写开篇")
            proposal = session.prepare_adopt("莉亚学会了影步。")
            session.commit_adopt(proposal, accepted_canon=True)

            session.undo_last_adopt()

            self.assertEqual(store.load_canon(), HotCanon.empty())
            self.assertEqual(
                (store.project_dir / "manuscript" / "scene_001.md").read_text(
                    encoding="utf-8"
                ),
                "",
            )
            loaded = store.load_session()
            self.assertEqual(loaded.adopted_prose, "")
            self.assertEqual(loaded.adopt_stack, [])

    def test_undo_twice_removes_both_adopts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
            session = NovelSession(
                store,
                _FakeModel(),
                meta,
                canon_extractor=_FakeCanonExtractor(HotCanon.empty()),
            )
            session.commit_adopt(
                session.prepare_adopt("第一段。"),
                accepted_canon=False,
            )
            session.commit_adopt(
                session.prepare_adopt("第二段。"),
                accepted_canon=False,
            )

            session.undo_last_adopt()
            session.undo_last_adopt()

            self.assertEqual(
                (store.project_dir / "manuscript" / "scene_001.md").read_text(
                    encoding="utf-8"
                ),
                "",
            )
            self.assertEqual(store.load_session().adopt_stack, [])

    def test_undo_rejected_canon_adopt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
            patch = HotCanon(characters=[{"name": "莉亚", "abilities": ["影步"]}])
            session = NovelSession(
                store,
                _FakeModel(),
                meta,
                canon_extractor=_FakeCanonExtractor(patch),
            )
            session.commit_adopt(
                session.prepare_adopt("正文。"),
                accepted_canon=False,
            )

            session.undo_last_adopt()

            self.assertEqual(store.load_canon(), HotCanon.empty())
            self.assertEqual(
                (store.project_dir / "manuscript" / "scene_001.md").read_text(
                    encoding="utf-8"
                ),
                "",
            )

    def test_undo_empty_stack_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
            session = NovelSession(
                store,
                _FakeModel(),
                meta,
                canon_extractor=_FakeCanonExtractor(HotCanon.empty()),
            )

            with self.assertRaisesRegex(ValueError, "没有可撤销的采纳"):
                session.undo_last_adopt()

    def test_undo_does_not_touch_messages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
            session = NovelSession(
                store,
                _FakeModel(),
                meta,
                canon_extractor=_FakeCanonExtractor(HotCanon.empty()),
            )
            session.send("写开篇")
            session.commit_adopt(
                session.prepare_adopt("正文。"),
                accepted_canon=False,
            )
            message_count = len(store.load_session().messages)

            session.undo_last_adopt()

            self.assertEqual(len(store.load_session().messages), message_count)

    def test_prepare_fix_empty_patch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
            session = NovelSession(
                store,
                _FakeModel(),
                meta,
                canon_extractor=_FakeCanonExtractor(
                    HotCanon.empty(),
                    fix_patch=HotCanon.empty(),
                ),
            )

            proposal = session.prepare_fix("这只是一条说明。")

            self.assertTrue(is_empty_canon_patch(proposal.canon_patch))

    def test_commit_fix_updates_canon_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
            fix_patch = HotCanon(characters=[{"name": "莉亚", "abilities": []}])
            session = NovelSession(
                store,
                _FakeModel(),
                meta,
                canon_extractor=_FakeCanonExtractor(
                    HotCanon.empty(),
                    fix_patch=fix_patch,
                ),
            )
            session.commit_adopt(
                session.prepare_adopt("正文。"),
                accepted_canon=False,
            )
            manuscript_before = (
                store.project_dir / "manuscript" / "scene_001.md"
            ).read_text(encoding="utf-8")
            stack_before = len(store.load_session().adopt_stack)

            proposal = session.prepare_fix("主角并未获得暗属性能力。")
            session.commit_fix(proposal)

            self.assertEqual(store.load_canon().characters[0]["abilities"], [])
            self.assertEqual(
                (store.project_dir / "manuscript" / "scene_001.md").read_text(
                    encoding="utf-8"
                ),
                manuscript_before,
            )
            self.assertEqual(len(store.load_session().adopt_stack), stack_before)

    def test_prepare_fix_empty_intent_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "demo")
            store.ensure_project_layout()
            meta = NovelMeta(title="书", world=WorldCanon(), style="轻松")
            session = NovelSession(
                store,
                _FakeModel(),
                meta,
                canon_extractor=_FakeCanonExtractor(HotCanon.empty()),
            )

            with self.assertRaisesRegex(ValueError, "纠错意图不能为空"):
                session.prepare_fix("   ")


class HotCanonMergeTest(unittest.TestCase):
    def test_merge_updates_characters_and_deduplicates_arrays(self) -> None:
        base = HotCanon(
            characters=[
                {
                    "name": "莉亚",
                    "abilities": [
                        {
                            "id": "shadow_step",
                            "name": "影步",
                            "kind": "skill",
                            "level": 1,
                            "summary": "影步",
                            "introduced_in": "",
                            "constraints": [],
                        }
                    ],
                    "status": "疲惫",
                    "relationships": {"悠真": "同伴"},
                    "inventory": ["银钥匙"],
                    "location": "旧图书馆",
                }
            ],
            world=WorldCanon(rules=["暗属性魔法会侵蚀记忆"]),
            plot_threads=[
                {
                    "id": "seal",
                    "title": "封印",
                    "status": "open",
                    "introduced_in": "scene_001",
                    "advanced_in": [],
                    "closed_in": "",
                    "related_characters": [],
                    "priority": "main",
                    "note": "钟楼封印",
                }
            ],
        )
        patch = HotCanon(
            characters=[
                {
                    "name": "莉亚",
                    "abilities": [
                        {
                            "id": "shadow_step",
                            "name": "影步",
                            "kind": "skill",
                            "level": 1,
                            "summary": "影步",
                            "introduced_in": "",
                            "constraints": [],
                        },
                        {
                            "id": "blink",
                            "name": "瞬移",
                            "kind": "skill",
                            "level": 1,
                            "summary": "瞬移",
                            "introduced_in": "",
                            "constraints": [],
                        },
                    ],
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
        ability_ids = {item["id"] for item in character["abilities"]}
        self.assertEqual(ability_ids, {"shadow_step", "blink"})
        self.assertEqual(character["status"], "左臂受伤")
        self.assertEqual(character["relationships"], {"悠真": "同伴", "米娜": "老师"})
        self.assertEqual(character["inventory"], ["银钥匙", "黑羽"])
        self.assertEqual(character["location"], "钟楼")
        self.assertEqual(
            merged.world.rules,
            ["暗属性魔法会侵蚀记忆", "钟声会削弱封印"],
        )
        self.assertEqual(merged.plot_threads[0]["status"], "advanced")
        self.assertEqual(merged.plot_threads[0]["note"], "钟楼封印")


class CommandParserTest(unittest.TestCase):
    def test_parse_known_command_aliases(self) -> None:
        self.assertEqual(parse_command("/a").action, CommandAction.ADOPT)
        self.assertEqual(parse_command("/adopt").action, CommandAction.ADOPT)
        self.assertEqual(parse_command("/c").action, CommandAction.CANON)
        self.assertEqual(parse_command("/canon").action, CommandAction.CANON)
        self.assertEqual(
            parse_command("/canon migrate").action,
            CommandAction.CANON_MIGRATE,
        )
        self.assertEqual(
            parse_command("/c migrate").action,
            CommandAction.CANON_MIGRATE,
        )
        self.assertEqual(parse_command("/h").action, CommandAction.HELP)
        self.assertEqual(parse_command("/help").action, CommandAction.HELP)
        self.assertEqual(parse_command("/sc").action, CommandAction.SCENE)
        self.assertEqual(parse_command("/scene").action, CommandAction.SCENE)
        self.assertEqual(parse_command("/u").action, CommandAction.UNDO)
        self.assertEqual(parse_command("/undo").action, CommandAction.UNDO)
        self.assertEqual(parse_command("/f").action, CommandAction.FIX)
        self.assertEqual(parse_command("/fix").action, CommandAction.FIX)
        self.assertEqual(parse_command("/config").action, CommandAction.CONFIG)

    def test_parse_plain_text_as_message(self) -> None:
        parsed = parse_command("继续写主角进酒馆")

        self.assertEqual(parsed.action, CommandAction.MESSAGE)
        self.assertEqual(parsed.text, "继续写主角进酒馆")

    def test_parse_config_command_with_args(self) -> None:
        parsed = parse_command("/config set context.char_budget 500000")

        self.assertEqual(parsed.action, CommandAction.CONFIG)
        self.assertEqual(parsed.text, "set context.char_budget 500000")

    def test_parse_export_command_with_optional_path(self) -> None:
        self.assertEqual(parse_command("/export").action, CommandAction.EXPORT)
        parsed = parse_command("/export drafts/book.md")

        self.assertEqual(parsed.action, CommandAction.EXPORT)
        self.assertEqual(parsed.text, "drafts/book.md")

    def test_main_parse_args_accepts_meta_path(self) -> None:
        parsed = parse_main_args(["--project", "demo", "--meta", "meta.json"])

        self.assertEqual(parsed.project, "demo")
        self.assertEqual(parsed.meta, "meta.json")


class ConfigCommandTest(unittest.TestCase):
    def test_set_updates_integer_config_value(self) -> None:
        config = ProjectConfig.default()

        updated, message = handle_config_args(config, "set context.char_budget 500000")

        self.assertEqual(updated.context.char_budget, 500_000)
        self.assertIn("context.char_budget = 500000", message)

    def test_get_returns_single_config_value(self) -> None:
        config = ProjectConfig.default()

        updated, message = handle_config_args(config, "get scene_switch.no_adopt_turns")

        self.assertEqual(updated, config)
        self.assertEqual(message, "scene_switch.no_adopt_turns = 3")

    def test_reset_single_config_value(self) -> None:
        config = ProjectConfig.default()
        config.scene_switch.no_adopt_turns = 9

        updated, message = handle_config_args(config, "reset scene_switch.no_adopt_turns")

        self.assertEqual(updated.scene_switch.no_adopt_turns, 3)
        self.assertIn("scene_switch.no_adopt_turns = 3", message)

    def test_unknown_config_key_raises(self) -> None:
        with self.assertRaisesRegex(ConfigCommandError, "未知配置项"):
            handle_config_args(ProjectConfig.default(), "get context.missing")

    def test_invalid_config_value_raises(self) -> None:
        with self.assertRaisesRegex(ConfigCommandError, "必须是整数"):
            handle_config_args(ProjectConfig.default(), "set context.char_budget many")

    def test_run_config_persists_updated_session_config(self) -> None:
        session = _ConfigSession()

        message = run_config(session, "set context.char_budget 500000")

        self.assertIn("context.char_budget = 500000", message)
        self.assertEqual(session.config.context.char_budget, 500_000)
        self.assertTrue(session.updated)


class _FakeModel:
    def invoke(self, messages: list[object]) -> object:
        return _FakeResponse(content="模型回复")


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _ConfigSession:
    def __init__(self) -> None:
        self.config = ProjectConfig.default()
        self.updated = False

    def update_config(self, config: ProjectConfig) -> None:
        self.config = config
        self.updated = True


class _CapturingPromptBuilder:
    def __init__(self) -> None:
        self.seen_canon: HotCanon | None = None
        self.seen_context_config: ContextConfig | None = None
        self.seen_scene_tail: str | None = None
        self.seen_writing_buffer_messages: list[ChatMessage] | None = None
        self.seen_discussion_buffer_messages: list[ChatMessage] | None = None
        self.build_calls: list[str] = []
        self.seen_discussion_brief: DiscussionBrief | None = None

    def build(
        self,
        *,
        meta: NovelMeta,
        canon: HotCanon,
        buffer: ShortTermBuffer,
        user_input: str,
        **kwargs: object,
    ) -> list[HumanMessage]:
        self.build_calls.append("build")
        self.seen_canon = canon
        self.seen_writing_buffer_messages = list(buffer.messages)
        value = kwargs.get("context_config")
        self.seen_context_config = value if isinstance(value, ContextConfig) else None
        tail = kwargs.get("scene_tail")
        self.seen_scene_tail = tail if isinstance(tail, str) else None
        return [HumanMessage(content=user_input)]

    def build_writing(
        self,
        *,
        meta: NovelMeta,
        canon: HotCanon,
        buffer: ShortTermBuffer,
        user_input: str,
        **kwargs: object,
    ) -> list[HumanMessage]:
        self.build_calls.append("build_writing")
        self.seen_canon = canon
        self.seen_writing_buffer_messages = list(buffer.messages)
        brief = kwargs.get("discussion_brief")
        self.seen_discussion_brief = brief if isinstance(brief, DiscussionBrief) else None
        value = kwargs.get("context_config")
        self.seen_context_config = value if isinstance(value, ContextConfig) else None
        tail = kwargs.get("scene_tail")
        self.seen_scene_tail = tail if isinstance(tail, str) else None
        return [HumanMessage(content=user_input)]

    def build_discussion(
        self,
        *,
        meta: NovelMeta,
        canon: HotCanon,
        buffer: ShortTermBuffer,
        user_input: str,
        **kwargs: object,
    ) -> list[HumanMessage]:
        self.build_calls.append("build_discussion")
        self.seen_canon = canon
        self.seen_discussion_buffer_messages = list(buffer.messages)
        value = kwargs.get("context_config")
        self.seen_context_config = value if isinstance(value, ContextConfig) else None
        tail = kwargs.get("scene_tail")
        self.seen_scene_tail = tail if isinstance(tail, str) else None
        return [HumanMessage(content=user_input)]


class _FixedResponseModel:
    def __init__(self, content: str) -> None:
        self._content = content

    def invoke(self, messages: list[object]) -> object:
        return _FakeResponse(content=self._content)


class _StreamingModel:
    def __init__(self, chunks: list[str]) -> None:
        self._chunks = chunks

    def invoke(self, messages: list[object]) -> object:
        return _FakeResponse(content="".join(self._chunks))

    def stream(self, messages: list[object]):
        for chunk in self._chunks:
            yield _FakeResponse(content=chunk)


class _SequenceResponseModel:
    def __init__(self, contents: list[str]) -> None:
        self._contents = contents
        self._index = 0

    def invoke(self, messages: list[object]) -> object:
        if self._index >= len(self._contents):
            content = self._contents[-1]
        else:
            content = self._contents[self._index]
        self._index += 1
        return _FakeResponse(content=content)


class _FakeBriefRefresher(DiscussionBriefRefresher):
    def __init__(self, *, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.refresh_calls: int = 0

    def refresh(
        self,
        scene_id: str,
        messages: list[ChatMessage],
        meta: NovelMeta | None = None,
        canon: HotCanon | None = None,
        global_summary: str = "",
        prior_scene_cold: object = None,
        scene_tail: str | None = None,
    ) -> DiscussionBrief:
        self.refresh_calls += 1
        if self.should_fail:
            raise DiscussionBriefRefreshError("simulated refresh failure")
        return DiscussionBrief(
            scene_id=scene_id,
            todo_items=["刷新后的待写事项"],
            constraints=["刷新后的约束"],
            open_questions=[],
            dirty=False,
            updated_at="2026-06-10T00:00:00Z",
        )


class _JsonColdModel:
    def __init__(
        self,
        *,
        propose_content: str = "{}",
        rollup_content: str = "梗概",
    ) -> None:
        self._propose_content = propose_content
        self._rollup_content = rollup_content
        self._call = 0

    def invoke(self, messages: list[object]) -> object:
        self._call += 1
        if self._call == 1:
            return _FakeResponse(content=self._propose_content)
        return _FakeResponse(content=self._rollup_content)


class _FakeColdExtractor:
    def __init__(
        self,
        proposal: ColdProposal,
        *,
        rollup: str = "全书梗概",
    ) -> None:
        self._proposal = proposal
        self._rollup = rollup

    def propose(
        self,
        scene_id: str,
        adopted_text: str,
        *,
        meta: NovelMeta | None = None,
    ) -> ColdProposal:
        return self._proposal

    def rollup_global(
        self,
        old_global: str,
        scene_entry: SceneSynopsisEntry,
    ) -> str:
        return self._rollup


class _FakeCanonExtractor:
    def __init__(self, patch: HotCanon, *, fix_patch: HotCanon | None = None) -> None:
        self.patch = patch
        self.fix_patch = patch if fix_patch is None else fix_patch

    def extract_patch(self, adopted_text: str, canon: HotCanon) -> HotCanon:
        return self.patch

    def extract_fix_patch(self, correction_intent: str, canon: HotCanon) -> HotCanon:
        return self.fix_patch


if __name__ == "__main__":
    unittest.main()
