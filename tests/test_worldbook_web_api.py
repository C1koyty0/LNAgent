"""worldbook Web API 集成测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from lnagent.config import Settings
from lnagent.memory.models import HotCanon, NovelMeta
from lnagent.web.app import create_web_app
from tests.test_web_app import _ReplyModel, _build_service


class WorldbookWebApiTest(unittest.TestCase):
    def test_get_worldbook_returns_no_worldbook_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = _build_app(Path(tmp))
            client = app.test_client()

            response = client.get("/api/projects/demo/worldbook")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.get_json(),
                {
                    "source": "",
                    "structured": {
                        "schema_version": 1,
                        "overview": "",
                        "global_rules": [],
                        "scopes": [],
                        "glossary": [],
                        "open_questions": [],
                    },
                    "status": "no_worldbook",
                },
            )

    def test_save_source_then_get_worldbook_returns_source_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = _build_app(root)
            client = app.test_client()

            put_response = client.put(
                "/api/projects/demo/worldbook/source",
                json={"source": "# 世界观\n\n月神王国信奉银月。"},
            )
            self.assertEqual(put_response.status_code, 200)
            put_payload = put_response.get_json()
            self.assertEqual(put_payload["status"], "source_only")
            self.assertEqual(put_payload["source"], "# 世界观\n\n月神王国信奉银月。")

            stored_source = (root / "projects" / "demo" / "worldbook" / "source.md").read_text(
                encoding="utf-8"
            )
            self.assertEqual(stored_source, "# 世界观\n\n月神王国信奉银月。")

            get_response = client.get("/api/projects/demo/worldbook")
            self.assertEqual(get_response.status_code, 200)
            get_payload = get_response.get_json()
            self.assertEqual(get_payload["status"], "source_only")
            self.assertEqual(get_payload["source"], "# 世界观\n\n月神王国信奉银月。")
            self.assertEqual(get_payload["structured"]["global_rules"], [])

    def test_extract_worldbook_returns_preview_and_does_not_change_meta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = _ReplyModel(
                [
                    json.dumps(
                        {
                            "overview": "月神王国与白塔学院共存。",
                            "global_rules": ["魔法需要月光引导"],
                            "scopes": [
                                {
                                    "scope_type": "location",
                                    "scope_id": "白塔学院",
                                    "summary": "王国最高魔法学府",
                                    "rules": ["学院内禁止公开决斗"],
                                }
                            ],
                            "glossary": [{"term": "月纹", "definition": "施法印记"}],
                            "open_questions": ["谁掌握失落仪式"],
                        },
                        ensure_ascii=False,
                    )
                ]
            )
            app = _build_app(root, model_factory=lambda _project_id: model)
            client = app.test_client()

            client.put(
                "/api/projects/demo/worldbook/source",
                json={"source": "# 世界观\n\n王国依赖月光施法，白塔学院禁止公开决斗。"},
            )

            extract_response = client.post("/api/projects/demo/worldbook/extract")

            self.assertEqual(extract_response.status_code, 200)
            payload = extract_response.get_json()
            self.assertEqual(payload["status"], "preview_ready")
            self.assertEqual(payload["structured"]["global_rules"], ["魔法需要月光引导"])
            self.assertEqual(payload["structured"]["scopes"][0]["scope_id"], "白塔学院")

            stored_structured = json.loads(
                (root / "projects" / "demo" / "worldbook" / "structured.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(stored_structured["global_rules"], ["魔法需要月光引导"])

            meta_response = client.get("/api/projects/demo/meta")
            self.assertEqual(meta_response.status_code, 200)
            self.assertEqual(meta_response.get_json()["world"]["rules"], ["魔法存在"])

    def test_apply_worldbook_updates_meta_and_returns_applied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = _build_app(root)
            client = app.test_client()

            (root / "projects" / "demo" / "worldbook").mkdir(parents=True, exist_ok=True)
            (root / "projects" / "demo" / "worldbook" / "source.md").write_text(
                "# 世界观\n\n月神王国与白塔学院。",
                encoding="utf-8",
            )
            (root / "projects" / "demo" / "worldbook" / "structured.json").write_text(
                json.dumps(
                    {
                        "overview": "月神王国与白塔学院共存。",
                        "global_rules": ["魔法需要月光引导"],
                        "scopes": [
                            {
                                "scope_type": "location",
                                "scope_id": "白塔学院",
                                "summary": "王国最高魔法学府",
                                "rules": ["学院内禁止公开决斗"],
                            }
                        ],
                        "glossary": [],
                        "open_questions": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            apply_response = client.post("/api/projects/demo/worldbook/apply")

            self.assertEqual(apply_response.status_code, 200)
            payload = apply_response.get_json()
            self.assertEqual(payload["status"], "applied")
            self.assertEqual(payload["meta"]["world"]["rules"], ["魔法需要月光引导"])
            self.assertEqual(payload["meta"]["world"]["scoped"][0]["scope_id"], "白塔学院")

            meta_json = json.loads((root / "projects" / "demo" / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta_json["world"]["rules"], ["魔法需要月光引导"])

            get_response = client.get("/api/projects/demo/worldbook")
            self.assertEqual(get_response.status_code, 200)
            self.assertEqual(get_response.get_json()["status"], "applied")

    def test_extract_worldbook_rejects_empty_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = _build_app(Path(tmp))
            client = app.test_client()

            response = client.post("/api/projects/demo/worldbook/extract")

            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.get_json()["error"], "worldbook source 不能为空")

    def test_apply_worldbook_rejects_missing_structured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = _build_app(Path(tmp))
            client = app.test_client()

            response = client.post("/api/projects/demo/worldbook/apply")

            self.assertEqual(response.status_code, 400)
            self.assertIn("structured worldbook", response.get_json()["error"])


def _build_app(root: Path, *, model_factory=None):
    service = _build_service(root, model_factory=model_factory)
    return create_web_app(service)


if __name__ == "__main__":
    unittest.main()
