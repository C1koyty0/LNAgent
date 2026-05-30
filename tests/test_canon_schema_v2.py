"""Hot Canon schema v2 单测。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from lnagent.memory.canon_context import resolve_active_scopes
from lnagent.memory.canon_display import format_canon_summary, format_hot_canon_for_prompt
from lnagent.memory.canon_extractor import (
    is_empty_canon_patch,
    merge_hot_canon,
)
from lnagent.memory.canon_migrate import (
    CANON_SCHEMA_VERSION,
    parse_legacy_ability_string,
    slugify,
    upgrade_canon_dict,
)
from lnagent.memory.models import HotCanon, ScopedWorldRules, WorldCanon
from lnagent.memory.prompt import PromptContextBuilder
from lnagent.memory.models import NovelMeta
from lnagent.memory.short_term import ShortTermBuffer
from lnagent.memory.store import JsonMemoryStore


class CanonMigrateTest(unittest.TestCase):
    def test_upgrade_v1_adds_schema_version_and_scoped(self) -> None:
        raw = {
            "characters": [],
            "world": {"rules": ["通用规则"]},
            "plot_threads": [],
        }
        upgraded = upgrade_canon_dict(raw)
        self.assertEqual(upgraded["schema_version"], CANON_SCHEMA_VERSION)
        self.assertEqual(upgraded["world"]["scoped"], [])

    def test_parse_legacy_ability_dedupes_by_slug(self) -> None:
        first = parse_legacy_ability_string("能量感知 lv1：感知半径10m")
        second = parse_legacy_ability_string("能量感知 lv1：精度提升")
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(slugify("能量感知"), first["id"])

    def test_v1_string_abilities_migrate_on_from_dict(self) -> None:
        canon = HotCanon.from_dict(
            {
                "characters": [
                    {
                        "name": "伽紫",
                        "abilities": [
                            "能量感知 lv1：A",
                            "能量感知 lv1：B",
                        ],
                    }
                ],
                "world": {"rules": []},
                "plot_threads": [],
            }
        )
        abilities = canon.characters[0]["abilities"]
        self.assertEqual(len(abilities), 1)
        self.assertEqual(abilities[0]["id"], slugify("能量感知"))


class ScopedMergeTest(unittest.TestCase):
    def test_merge_scoped_rules_by_scope_key(self) -> None:
        base = HotCanon(
            world=WorldCanon(
                rules=["通用"],
                scoped=[
                    ScopedWorldRules(
                        scope_type="faction",
                        scope_id="洛兰分封王国",
                        rules=["骑士合击"],
                    )
                ],
            )
        )
        patch = HotCanon.from_dict(
            {
                "world": {
                    "scoped": [
                        {
                            "scope_type": "faction",
                            "scope_id": "洛兰分封王国",
                            "rules": ["领地士气"],
                        }
                    ]
                }
            }
        )
        merged = merge_hot_canon(base, patch)
        scoped = merged.world.scoped
        self.assertEqual(len(scoped), 1)
        self.assertEqual(
            set(scoped[0].rules),
            {"骑士合击", "领地士气"},
        )

    def test_empty_patch_with_scoped_only(self) -> None:
        patch = HotCanon.from_dict(
            {
                "world": {
                    "scoped": [
                        {
                            "scope_type": "location",
                            "scope_id": "白色空间",
                            "rules": ["转生准备"],
                        }
                    ]
                }
            }
        )
        self.assertFalse(is_empty_canon_patch(patch))


class AbilityMergeTest(unittest.TestCase):
    def test_merge_abilities_by_id_updates_level(self) -> None:
        base = HotCanon(
            characters=[
                {
                    "name": "莉亚",
                    "abilities": [
                        {
                            "id": "energy_sense",
                            "name": "能量感知",
                            "kind": "skill",
                            "level": 1,
                            "summary": "旧",
                            "introduced_in": "",
                            "constraints": [],
                        }
                    ],
                }
            ]
        )
        patch = HotCanon(
            characters=[
                {
                    "name": "莉亚",
                    "abilities": [
                        {
                            "id": "energy_sense",
                            "name": "能量感知",
                            "kind": "skill",
                            "level": 2,
                            "summary": "新",
                            "introduced_in": "scene_002",
                            "constraints": ["叠加"],
                        }
                    ],
                }
            ]
        )
        merged = merge_hot_canon(base, patch)
        ability = merged.characters[0]["abilities"][0]
        self.assertEqual(ability["level"], 2)
        self.assertEqual(ability["summary"], "新")
        self.assertIn("叠加", ability["constraints"])


class PlotThreadMergeTest(unittest.TestCase):
    def test_merge_advanced_in_and_closed_in(self) -> None:
        base = HotCanon(
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
                    "note": "钟楼",
                }
            ]
        )
        patch = HotCanon(
            plot_threads=[
                {
                    "id": "seal",
                    "status": "closed",
                    "advanced_in": ["scene_002"],
                    "closed_in": "scene_002",
                }
            ]
        )
        merged = merge_hot_canon(base, patch)
        thread = merged.plot_threads[0]
        self.assertEqual(thread["status"], "closed")
        self.assertEqual(thread["closed_in"], "scene_002")
        self.assertEqual(thread["advanced_in"], ["scene_002"])


class CanonPromptScopeTest(unittest.TestCase):
    def test_prompt_includes_matching_scoped_only(self) -> None:
        canon = HotCanon(
            characters=[
                {"name": "主角", "location": "洛兰王都", "abilities": []},
            ],
            world=WorldCanon(
                rules=["通用"],
                scoped=[
                    ScopedWorldRules("faction", "洛兰分封王国", ["洛兰规则"]),
                    ScopedWorldRules("faction", "梵洛斯中央帝国", ["帝国规则"]),
                ],
            ),
        )
        text = format_hot_canon_for_prompt(
            canon,
            active_scopes={("location", "洛兰王都")},
        )
        self.assertIsNotNone(text)
        assert text is not None
        self.assertIn("洛兰规则", text)
        self.assertNotIn("帝国规则", text)

    def test_resolve_active_scopes_from_character_location(self) -> None:
        canon = HotCanon(
            characters=[{"name": "A", "location": "白色空间", "abilities": []}]
        )
        scopes = resolve_active_scopes(canon)
        self.assertIn(("location", "白色空间"), scopes)


class CanonStoreSchemaTest(unittest.TestCase):
    def test_save_canon_writes_schema_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonMemoryStore(Path(tmp) / "proj")
            store.ensure_project_layout()
            store.save_meta(
                NovelMeta(title="t", world_rules=[], style="s")
            )
            store.save_canon(
                HotCanon(
                    world=WorldCanon(
                        scoped=[
                            ScopedWorldRules("faction", "洛兰", ["r1"]),
                        ]
                    )
                )
            )
            raw = json.loads((store.project_dir / "memory" / "canon.json").read_text())
            self.assertEqual(raw["schema_version"], 2)
            self.assertEqual(len(raw["world"]["scoped"]), 1)


class CanonDisplayTest(unittest.TestCase):
    def test_format_canon_summary_lists_open_threads(self) -> None:
        canon = HotCanon(
            plot_threads=[
                {
                    "id": "a",
                    "title": "主线",
                    "status": "open",
                    "introduced_in": "scene_001",
                    "advanced_in": [],
                    "closed_in": "",
                    "related_characters": [],
                    "priority": "main",
                    "note": "未完",
                },
                {
                    "id": "b",
                    "title": "已收束",
                    "status": "closed",
                    "introduced_in": "scene_001",
                    "advanced_in": [],
                    "closed_in": "scene_001",
                    "related_characters": [],
                    "priority": "",
                    "note": "",
                },
            ]
        )
        text = format_canon_summary(canon)
        self.assertIn("主线", text)
        self.assertIn("[open]", text)
        self.assertIn("[closed]", text)


class PromptBuilderSchemaTest(unittest.TestCase):
    def test_build_uses_compact_hot_canon(self) -> None:
        builder = PromptContextBuilder()
        canon = HotCanon(
            world=WorldCanon(
                rules=["通用"],
                scoped=[ScopedWorldRules("location", "洛兰", ["洛兰街景"])],
            ),
            characters=[
                {
                    "name": "主角",
                    "location": "洛兰",
                    "abilities": [
                        {
                            "id": "sense",
                            "name": "感知",
                            "kind": "skill",
                            "level": 1,
                            "summary": "短说明",
                            "introduced_in": "",
                            "constraints": [],
                        }
                    ],
                }
            ],
        )
        messages = builder.build(
            meta=NovelMeta(title="t", world_rules=[], style="s"),
            canon=canon,
            buffer=ShortTermBuffer(scene_id="scene_001"),
            user_input="继续",
        )
        system = messages[0].content
        assert isinstance(system, str)
        self.assertIn("洛兰街景", system)
        self.assertNotIn('"schema_version"', system)


if __name__ == "__main__":
    unittest.main()
