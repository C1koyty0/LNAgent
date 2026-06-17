"""模板存储层测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from lnagent.template_store import JsonTemplateStore


class TemplateStoreTest(unittest.TestCase):
    def test_save_list_load_and_overwrite_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonTemplateStore(Path(tmp) / "projects")

            saved = store.save_template(
                "学院模板",
                {
                    "title": "测试书",
                    "style": "轻小说",
                    "pov": "第一人称",
                    "tense": "过去式",
                    "genre": "学院奇幻",
                    "tone": "明快",
                    "target_audience": "青年读者",
                    "taboos": ["  避免说教  ", "", "避免跳脱"],
                    "narrative_rules": ["聚焦主角感知", "  "],
                    "world_rules": ["应被忽略的旧字段"],
                },
            )
            self.assertEqual(saved["name"], "学院模板")
            self.assertEqual(saved["style"], "轻小说")
            self.assertEqual(saved["taboos"], ["避免说教", "避免跳脱"])
            self.assertEqual(saved["narrative_rules"], ["聚焦主角感知"])

            template_path = Path(tmp) / "projects" / "_templates" / "学院模板.json"
            self.assertTrue(template_path.is_file())
            raw = json.loads(template_path.read_text(encoding="utf-8"))
            self.assertEqual(raw["title"], "测试书")
            self.assertEqual(raw["style"], "轻小说")
            self.assertNotIn("world", raw)
            self.assertNotIn("world_rules", raw)

            self.assertEqual(store.load_template("学院模板"), saved)
            self.assertEqual(store.list_templates(), [saved])

            overwritten = store.save_template(
                "学院模板",
                {
                    "title": "新书名",
                    "style": "严肃奇幻",
                    "taboos": ["避免说教"],
                },
            )
            self.assertEqual(overwritten["title"], "新书名")
            self.assertEqual(overwritten["style"], "严肃奇幻")
            self.assertEqual(store.load_template("学院模板")["style"], "严肃奇幻")

    def test_list_templates_skips_invalid_files_and_tolerates_legacy_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = JsonTemplateStore(Path(tmp) / "projects")
            template_dir = Path(tmp) / "projects" / "_templates"
            template_dir.mkdir(parents=True, exist_ok=True)
            (template_dir / "broken.json").write_text("{bad json}", encoding="utf-8")
            (template_dir / "legacy.json").write_text(
                json.dumps(
                    {
                        "style": "轻小说",
                        "taboos": ["  避免说教  ", "  "],
                        "world_rules": ["旧字段应被忽略"],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            templates = store.list_templates()
            self.assertEqual(len(templates), 1)
            self.assertEqual(templates[0]["name"], "legacy")
            self.assertEqual(templates[0]["title"], "")
            self.assertEqual(templates[0]["style"], "轻小说")
            self.assertEqual(templates[0]["taboos"], ["避免说教"])
            self.assertNotIn("world_rules", templates[0])

            store.delete_template("legacy")
            self.assertEqual(store.list_templates(), [])


if __name__ == "__main__":
    unittest.main()
