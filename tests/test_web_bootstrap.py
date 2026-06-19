"""Web/API W0 阶段的共享初始化与项目索引测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import cast

from langchain_core.language_models import BaseChatModel

from lnagent.bootstrap import bootstrap_project_runtime
from lnagent.config import Settings
from lnagent.memory.models import NovelMeta, SceneSession, WorldCanon
from lnagent.memory.store import JsonMemoryStore
from lnagent.project_index import list_projects
from lnagent.session import NovelSession


class BootstrapRuntimeTest(unittest.TestCase):
    def test_bootstrap_project_runtime_builds_store_meta_model_and_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            projects_dir = root / "projects"
            meta_path = root / "meta.json"
            meta_path.write_text(
                json.dumps(
                    {
                        "title": "测试书",
                        "style": "轻小说",
                        "world_rules": ["魔法存在"],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            settings = Settings(
                api_key="test-key",
                model="fake-model",
                projects_dir=projects_dir,
            )
            fake_model = object()
            fake_session = object()
            seen: dict[str, object] = {}

            def fake_model_factory(passed_settings: Settings) -> object:
                seen["settings"] = passed_settings
                return fake_model

            def fake_session_factory(
                store: JsonMemoryStore,
                model: object,
                meta: NovelMeta,
            ) -> object:
                seen["store"] = store
                seen["model"] = model
                seen["meta"] = meta
                return fake_session

            runtime = bootstrap_project_runtime(
                "demo",
                meta_path=meta_path,
                settings=settings,
                model_factory=fake_model_factory,
                session_factory=fake_session_factory,
            )

            self.assertEqual(runtime.settings.project_id, "demo")
            self.assertEqual(runtime.settings.project_dir, projects_dir / "demo")
            self.assertEqual(runtime.store.project_dir, projects_dir / "demo")
            self.assertEqual(runtime.meta.title, "测试书")
            self.assertIs(runtime.model, fake_model)
            self.assertIs(runtime.session, fake_session)
            self.assertEqual(runtime.store.load_meta().title, "测试书")
            self.assertIs(seen["settings"], runtime.settings)
            self.assertIs(seen["store"], runtime.store)
            self.assertIs(seen["meta"], runtime.meta)
            self.assertIs(seen["model"], runtime.model)

    def test_bootstrap_project_runtime_accepts_meta_without_world_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            projects_dir = root / "projects"
            meta_path = root / "meta.json"
            meta_path.write_text(
                json.dumps(
                    {
                        "title": "极简项目",
                        "style": "轻小说",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            settings = Settings(
                api_key="test-key",
                model="fake-model",
                projects_dir=projects_dir,
            )
            fake_model = cast(BaseChatModel, object())
            fake_session = cast(NovelSession, object())

            def fake_model_factory(_settings: Settings) -> BaseChatModel:
                return fake_model

            def fake_session_factory(
                store: JsonMemoryStore,
                model: BaseChatModel,
                meta: NovelMeta,
            ) -> NovelSession:
                del store, model, meta
                return fake_session

            runtime = bootstrap_project_runtime(
                "minimal",
                meta_path=meta_path,
                settings=settings,
                model_factory=fake_model_factory,
                session_factory=fake_session_factory,
            )

            self.assertEqual(runtime.meta.title, "极简项目")
            self.assertEqual(runtime.meta.style, "轻小说")
            self.assertEqual(runtime.meta.world.rules, [])
            self.assertEqual(runtime.store.load_meta().world.rules, [])
            self.assertFalse((projects_dir / "minimal" / "worldbook" / "source.md").exists())


class ProjectIndexTest(unittest.TestCase):
    def test_list_projects_returns_sorted_valid_project_summaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            projects_dir = Path(tmp) / "projects"
            alpha = JsonMemoryStore(projects_dir / "alpha")
            alpha.ensure_project_layout()
            alpha.save_meta(NovelMeta(title="Alpha", world=WorldCanon(rules=["规则A"]), style="轻松"))

            beta = JsonMemoryStore(projects_dir / "beta")
            beta.ensure_project_layout()
            beta.save_meta(NovelMeta(title="Beta", world=WorldCanon(rules=["规则B"]), style="严肃"))
            beta.save_session(SceneSession(scene_id="scene_003"))

            summaries = list_projects(projects_dir)

            self.assertEqual([item.project_id for item in summaries], ["alpha", "beta"])
            self.assertEqual(summaries[0].title, "Alpha")
            self.assertEqual(summaries[0].style, "轻松")
            self.assertEqual(summaries[0].current_scene_id, "scene_001")
            self.assertEqual(summaries[1].current_scene_id, "scene_003")

    def test_list_projects_ignores_invalid_project_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            projects_dir = Path(tmp) / "projects"
            valid = JsonMemoryStore(projects_dir / "valid")
            valid.ensure_project_layout()
            valid.save_meta(NovelMeta(title="有效项目", world=WorldCanon(rules=["规则"]), style="轻松"))

            broken_dir = projects_dir / "broken"
            broken_dir.mkdir(parents=True)
            (broken_dir / "meta.json").write_text("{not json}", encoding="utf-8")

            empty_dir = projects_dir / "empty"
            empty_dir.mkdir(parents=True)

            summaries = list_projects(projects_dir)

            self.assertEqual([item.project_id for item in summaries], ["valid"])


if __name__ == "__main__":
    unittest.main()
