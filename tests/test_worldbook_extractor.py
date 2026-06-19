"""WorldbookExtractor 单元测试。"""

from __future__ import annotations

import unittest
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from lnagent.memory.models import (
    WorldbookGlossaryEntry,
    WorldbookScope,
    WorldbookStructured,
)
from lnagent.memory.worldbook_extractor import (
    WorldbookExtractParseError,
    WorldbookExtractor,
)


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeWorldbookModel:
    def __init__(self, content: str) -> None:
        self._content = content
        self.invoke_calls = 0
        self.last_messages: list[Any] = []

    def invoke(self, messages: list[Any]) -> Any:
        self.invoke_calls += 1
        self.last_messages = list(messages)
        return _FakeResponse(self._content)


class WorldbookExtractorTest(unittest.TestCase):
    def test_extract_parses_valid_json_to_structured(self) -> None:
        model = _FakeWorldbookModel(
            """
            {
              "schema_version": 1,
              "overview": "蒸汽与魔法并存的大陆。",
              "global_rules": ["跨境传送需要王室许可"],
              "scopes": [
                {
                  "scope_type": "faction",
                  "scope_id": "洛兰王国",
                  "summary": "北境王权国家。",
                  "rules": ["贵族私军规模受限"]
                }
              ],
              "glossary": [
                {
                  "term": "圣纹",
                  "definition": "刻印在灵魂上的魔法回路。"
                }
              ],
              "open_questions": ["主角家族与王室旧约是否仍然有效？"]
            }
            """
        )
        extractor = WorldbookExtractor(model)

        structured = extractor.extract("# 世界观\n\n这里是原始设定文档。")

        self.assertEqual(
            structured,
            WorldbookStructured(
                schema_version=1,
                overview="蒸汽与魔法并存的大陆。",
                global_rules=["跨境传送需要王室许可"],
                scopes=[
                    WorldbookScope(
                        scope_type="faction",
                        scope_id="洛兰王国",
                        summary="北境王权国家。",
                        rules=["贵族私军规模受限"],
                    )
                ],
                glossary=[
                    WorldbookGlossaryEntry(
                        term="圣纹",
                        definition="刻印在灵魂上的魔法回路。",
                    )
                ],
                open_questions=["主角家族与王室旧约是否仍然有效？"],
            ),
        )

    def test_extract_returns_empty_structured_for_empty_source(self) -> None:
        model = _FakeWorldbookModel("should not be used")
        extractor = WorldbookExtractor(model)

        structured = extractor.extract("  \n\n ")

        self.assertEqual(structured, WorldbookStructured.empty())
        self.assertEqual(model.invoke_calls, 0)

    def test_extract_raises_on_invalid_json(self) -> None:
        model = _FakeWorldbookModel("not valid json")
        extractor = WorldbookExtractor(model)

        with self.assertRaises(WorldbookExtractParseError):
            extractor.extract("# 世界观\n\n原始设定")

    def test_extract_calls_model_with_worldbook_prompt_and_source(self) -> None:
        model = _FakeWorldbookModel(
            '{"overview":"","global_rules":[],"scopes":[],"glossary":[],"open_questions":[]}'
        )
        extractor = WorldbookExtractor(model)

        extractor.extract("# 世界观\n\n- 王国信仰月神")

        self.assertEqual(model.invoke_calls, 1)
        self.assertEqual(len(model.last_messages), 2)
        self.assertIsInstance(model.last_messages[0], SystemMessage)
        self.assertIsInstance(model.last_messages[1], HumanMessage)
        system_content = model.last_messages[0].content
        human_content = model.last_messages[1].content
        self.assertIn("不要编造", system_content)
        self.assertIn("global_rules", system_content)
        self.assertIn("# 世界观", human_content)
        self.assertIn("王国信仰月神", human_content)


if __name__ == "__main__":
    unittest.main()
