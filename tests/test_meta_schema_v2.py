"""meta.json schema v2 单测。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from lnagent.memory.canon_context import resolve_active_scopes
from lnagent.memory.meta_display import format_meta_for_prompt
from lnagent.memory.meta_migrate import META_SCHEMA_VERSION, upgrade_meta_dict
from lnagent.memory.models import HotCanon, NovelMeta, ScopedWorldRules, WorldCanon
from lnagent.memory.prompt import PromptContextBuilder
from lnagent.memory.short_term import ShortTermBuffer
from lnagent.memory.store import JsonMemoryStore
from lnagent.project import load_meta_from_file


class MetaMigrateTest(unittest.TestCase):
    def test_upgrade_splits_faction_rules_from_world_rules(self) -> None:
        raw = {
            "title": "test",
            "style": "轻松",
            "world_rules": [
                "世界名称：艾尔维恩",
                "洛兰分封王国 - 地理位置：大陆中部",
                "梵洛斯中央帝国 - 地理位置：大陆东侧",
            ],
        }
        upgraded = upgrade_meta_dict(raw)
        self.assertEqual(upgraded["schema_version"], META_SCHEMA_VERSION)
        self.assertEqual(len(upgraded["world"]["rules"]), 1)
        self.assertEqual(len(upgraded["world"]["scoped"]), 2)
        scope_ids = {entry["scope_id"] for entry in upgraded["world"]["scoped"]}
        self.assertIn("洛兰分封王国", scope_ids)

    def test_from_dict_v1_meta(self) -> None:
        meta = NovelMeta.from_dict(
            {
                "title": "书",
                "style": "文风",
                "world_rules": ["通用规则", "圣光神国 - 政体：政教合一"],
            }
        )
        self.assertEqual(meta.schema_version, META_SCHEMA_VERSION)
        self.assertEqual(meta.world.rules, ["通用规则"])
        self.assertEqual(len(meta.world.scoped), 1)


class MetaPromptScopeTest(unittest.TestCase):
    def test_meta_prompt_filters_scoped_by_location(self) -> None:
        meta = NovelMeta(
            title="书",
            style="轻松",
            world=WorldCanon(
                rules=["通用"],
                scoped=[
                    ScopedWorldRules("faction", "洛兰分封王国", ["洛兰规则"]),
                    ScopedWorldRules("faction", "梵洛斯中央帝国", ["帝国规则"]),
                ],
            ),
        )
        canon = HotCanon(
            characters=[{"name": "主角", "location": "洛兰王都", "abilities": []}]
        )
        scopes = resolve_active_scopes(canon)
        text = format_meta_for_prompt(meta, active_scopes=scopes)
        self.assertIn("洛兰规则", text)
        self.assertNotIn("帝国规则", text)


class MetaStoreTest(unittest.TestCase):
    def test_save_meta_writes_schema_v2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "proj")
            store.ensure_project_layout()
            meta = NovelMeta(
                title="书",
                style="轻松",
                world=WorldCanon(
                    scoped=[ScopedWorldRules("faction", "洛兰", ["规则"])],
                ),
            )
            store.save_meta(meta)
            raw = json.loads((store.project_dir / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(raw["schema_version"], 2)
            self.assertIn("world", raw)
            self.assertNotIn("world_rules", raw)


class MetaLoadFileTest(unittest.TestCase):
    def test_load_v2_meta_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            meta_path = Path(tmp) / "meta.json"
            meta_path.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "title": "书",
                        "style": "轻松",
                        "world": {
                            "rules": ["通用"],
                            "scoped": [
                                {
                                    "scope_type": "faction",
                                    "scope_id": "洛兰",
                                    "rules": ["洛兰条目"],
                                }
                            ],
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            meta = load_meta_from_file(meta_path)
            self.assertEqual(meta.world.scoped[0].scope_id, "洛兰")


class MetaPromptBuilderTest(unittest.TestCase):
    def test_build_includes_scoped_meta_when_matched(self) -> None:
        builder = PromptContextBuilder()
        meta = NovelMeta(
            title="书",
            style="轻松",
            world=WorldCanon(
                rules=["通用"],
                scoped=[ScopedWorldRules("location", "洛兰", ["洛兰街景"])],
            ),
        )
        canon = HotCanon(
            characters=[{"name": "主角", "location": "洛兰", "abilities": []}]
        )
        messages = builder.build(
            meta=meta,
            canon=canon,
            buffer=ShortTermBuffer(scene_id="scene_001"),
            user_input="继续",
        )
        system = messages[0].content
        assert isinstance(system, str)
        self.assertIn("洛兰街景", system)


if __name__ == "__main__":
    unittest.main()
