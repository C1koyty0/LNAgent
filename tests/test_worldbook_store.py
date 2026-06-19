"""worldbook store 单元测试。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lnagent.memory.models import (
    WorldbookGlossaryEntry,
    WorldbookScope,
    WorldbookStructured,
)
from lnagent.memory.store import JsonMemoryStore


class WorldbookStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = JsonMemoryStore(Path(self._tmp.name) / "demo")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_load_worldbook_source_returns_empty_string_when_missing(self) -> None:
        self.assertEqual(self.store.load_worldbook_source(), "")

    def test_worldbook_source_round_trip(self) -> None:
        self.store.save_worldbook_source("# 设定文档\n\n- 王国使用银币。\n")

        self.assertEqual(
            self.store.load_worldbook_source(),
            "# 设定文档\n\n- 王国使用银币。\n",
        )

    def test_load_worldbook_structured_returns_empty_when_missing(self) -> None:
        self.assertEqual(
            self.store.load_worldbook_structured(),
            WorldbookStructured.empty(),
        )

    def test_worldbook_structured_round_trip(self) -> None:
        structured = WorldbookStructured(
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
                    rules=["夜间禁止私自进入地下藏书库"],
                ),
            ],
            glossary=[
                WorldbookGlossaryEntry(
                    term="圣纹",
                    definition="刻印在灵魂上的魔法回路。",
                )
            ],
            open_questions=["主角家族与王室的旧约是否仍然有效？"],
        )

        self.store.save_worldbook_structured(structured)

        self.assertEqual(self.store.load_worldbook_structured(), structured)

    def test_save_worldbook_source_creates_worldbook_directory_on_demand(self) -> None:
        self.store.save_worldbook_source("初版世界观")

        self.assertTrue((self.store.project_dir / "worldbook").is_dir())
        self.assertTrue((self.store.project_dir / "worldbook" / "source.md").is_file())

    def test_save_worldbook_structured_creates_worldbook_directory_on_demand(self) -> None:
        self.store.save_worldbook_structured(WorldbookStructured.empty())

        self.assertTrue((self.store.project_dir / "worldbook").is_dir())
        self.assertTrue(
            (self.store.project_dir / "worldbook" / "structured.json").is_file()
        )

    def test_clear_worldbook_structured_removes_existing_preview_file(self) -> None:
        self.store.save_worldbook_structured(
            WorldbookStructured(global_rules=["魔法需要月光引导"])
        )

        self.store.clear_worldbook_structured()

        self.assertFalse((self.store.project_dir / "worldbook" / "structured.json").exists())
        self.assertEqual(self.store.load_worldbook_structured(), WorldbookStructured.empty())


if __name__ == "__main__":
    unittest.main()
