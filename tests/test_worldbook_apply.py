"""worldbook apply 单元测试。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lnagent.memory.models import (
    HotCanon,
    NovelMeta,
    ScopedWorldRules,
    WorldCanon,
    WorldbookScope,
    WorldbookStructured,
)
from lnagent.memory.prompt import PromptContextBuilder
from lnagent.memory.short_term import ShortTermBuffer
from lnagent.memory.store import JsonMemoryStore
from lnagent.memory.worldbook_apply import (
    WorldbookApplyError,
    apply_worldbook_to_meta,
)


class WorldbookApplyTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = JsonMemoryStore(Path(self._tmp.name) / "demo")
        self.store.ensure_project_layout()
        self.store.save_meta(
            NovelMeta(
                title="测试书",
                style="轻松",
                world=WorldCanon(
                    rules=["旧全局规则"],
                    scoped=[
                        ScopedWorldRules(
                            "faction",
                            "旧势力",
                            ["旧势力规则"],
                        )
                    ],
                ),
                pov="第一人称",
                tense="现在时",
                taboos=["不写血腥描写"],
                target_audience="轻小说读者",
                narrative_rules=["多用动作推进"],
                genre="校园奇幻",
                tone="温暖明快",
            )
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_apply_worldbook_to_meta_overwrites_world_and_preserves_narrative_fields(self) -> None:
        self.store.save_worldbook_structured(
            WorldbookStructured(
                overview="蒸汽与魔法并存的大陆。",
                global_rules=["跨境传送需要王室许可"],
                scopes=[
                    WorldbookScope(
                        scope_type="faction",
                        scope_id="洛兰王国",
                        summary="北境王权国家。",
                        rules=["贵族私军规模受限"],
                    ),
                    WorldbookScope(
                        scope_type="location",
                        scope_id="白塔学院",
                        summary="培养术士的学院。",
                        rules=["夜间禁止私入地下藏书库"],
                    ),
                ],
            )
        )

        updated_meta = apply_worldbook_to_meta(self.store)

        self.assertEqual(updated_meta.world.rules, ["跨境传送需要王室许可"])
        self.assertEqual(
            [(entry.scope_type, entry.scope_id, entry.rules) for entry in updated_meta.world.scoped],
            [
                ("faction", "洛兰王国", ["贵族私军规模受限"]),
                ("location", "白塔学院", ["夜间禁止私入地下藏书库"]),
            ],
        )
        self.assertEqual(updated_meta.style, "轻松")
        self.assertEqual(updated_meta.pov, "第一人称")
        self.assertEqual(updated_meta.tense, "现在时")
        self.assertEqual(updated_meta.taboos, ["不写血腥描写"])
        self.assertEqual(updated_meta.target_audience, "轻小说读者")
        self.assertEqual(updated_meta.narrative_rules, ["多用动作推进"])
        self.assertEqual(updated_meta.genre, "校园奇幻")
        self.assertEqual(updated_meta.tone, "温暖明快")

        reloaded_meta = self.store.load_meta()
        self.assertEqual(reloaded_meta.to_dict(), updated_meta.to_dict())

    def test_apply_worldbook_to_meta_raises_when_structured_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            empty_store = JsonMemoryStore(Path(tmp) / "demo")
            empty_store.ensure_project_layout()
            empty_store.save_meta(
                NovelMeta(title="测试书", style="轻松", world_rules=[])
            )

            with self.assertRaises(WorldbookApplyError):
                apply_worldbook_to_meta(empty_store)

    def test_apply_worldbook_to_meta_raises_when_structured_has_no_projectable_world_content(self) -> None:
        self.store.save_worldbook_structured(
            WorldbookStructured(
                overview="只有概览，没有可投影规则。",
                global_rules=[],
                scopes=[],
                open_questions=["世界树是否有意识？"],
            )
        )

        with self.assertRaises(WorldbookApplyError):
            apply_worldbook_to_meta(self.store)

    def test_apply_worldbook_to_meta_makes_prompt_builder_see_new_world(self) -> None:
        self.store.save_worldbook_structured(
            WorldbookStructured(
                global_rules=["月蚀期间禁止远程传送"],
                scopes=[
                    WorldbookScope(
                        scope_type="location",
                        scope_id="白塔学院",
                        summary="",
                        rules=["学院钟楼午夜后封闭"],
                    )
                ],
            )
        )

        updated_meta = apply_worldbook_to_meta(self.store)
        messages = PromptContextBuilder().build(
            meta=updated_meta,
            canon=HotCanon(
                characters=[{"name": "艾琳", "location": "白塔学院", "abilities": []}]
            ),
            buffer=ShortTermBuffer(scene_id="scene_001"),
            user_input="继续",
        )
        system = messages[0].content
        assert isinstance(system, str)

        self.assertIn("月蚀期间禁止远程传送", system)
        self.assertIn("学院钟楼午夜后封闭", system)


if __name__ == "__main__":
    unittest.main()
