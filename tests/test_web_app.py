"""Web 应用服务与 API 集成测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from lnagent.app_service import AppService
from lnagent.config import Settings
from lnagent.memory.cold_archive import ColdProposal
from lnagent.memory.models import HotCanon, NovelMeta
from lnagent.web.app import create_web_app


class WebAppIntegrationTest(unittest.TestCase):
    def test_send_then_adopt_commit_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = _build_app(Path(tmp), replies=["候选正文"], canon_name="莉亚")
            client = app.test_client()

            open_response = client.post("/api/projects/demo/open")
            self.assertEqual(open_response.status_code, 200)

            send_response = client.post(
                "/api/projects/demo/send",
                json={"text": "请续写第一段"},
            )
            self.assertEqual(send_response.status_code, 200)
            send_payload = send_response.get_json()
            self.assertEqual(send_payload["reply"], "候选正文")
            self.assertEqual(send_payload["last_candidate"], "候选正文")

            prepare_response = client.post(
                "/api/projects/demo/adopt/prepare",
                json={"text": "采纳后的正文"},
            )
            self.assertEqual(prepare_response.status_code, 200)
            prepare_payload = prepare_response.get_json()
            self.assertIn("莉亚", json.dumps(prepare_payload["canon_patch"], ensure_ascii=False))

            commit_response = client.post(
                "/api/projects/demo/adopt/commit",
                json={"text": "采纳后的正文", "accepted_canon": True},
            )
            self.assertEqual(commit_response.status_code, 200)
            commit_payload = commit_response.get_json()
            self.assertEqual(commit_payload["manuscript_text"], "采纳后的正文\n")
            self.assertIsNone(commit_payload["last_candidate"])

            state_response = client.get("/api/projects/demo/session")
            state_payload = state_response.get_json()
            self.assertEqual(state_payload["scene_id"], "scene_001")
            self.assertIsNone(state_payload["last_candidate"])
            self.assertEqual(len(state_payload["adopt_stack"]), 1)

    def test_list_projects_and_ignore_invalid_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = _build_app(root)
            client = app.test_client()

            broken = root / "projects" / "broken"
            broken.mkdir(parents=True)
            (broken / "meta.json").write_text("{bad json}", encoding="utf-8")

            response = client.get("/api/projects")
            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertEqual([item["project_id"] for item in payload["projects"]], ["demo"])

    def test_fix_prepare_and_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = _build_app(Path(tmp), fix_canon_name="修正设定")
            client = app.test_client()

            prepare_response = client.post(
                "/api/projects/demo/fix/prepare",
                json={"intent": "把角色名字改成修正设定"},
            )
            self.assertEqual(prepare_response.status_code, 200)
            prepare_payload = prepare_response.get_json()
            self.assertIn("修正设定", json.dumps(prepare_payload["canon_after"], ensure_ascii=False))

            commit_response = client.post(
                "/api/projects/demo/fix/commit",
                json={"intent": "把角色名字改成修正设定", "accepted_canon": True},
            )
            self.assertEqual(commit_response.status_code, 200)
            canon_response = client.get("/api/projects/demo/canon")
            canon_payload = canon_response.get_json()
            self.assertIn("修正设定", json.dumps(canon_payload, ensure_ascii=False))

    def test_scene_prepare_reconcile_and_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = _build_app(Path(tmp), replies=["候选正文"], canon_name="候选角色")
            client = app.test_client()

            client.post("/api/projects/demo/open")
            client.post("/api/projects/demo/send", json={"text": "继续写"})
            client.post(
                "/api/projects/demo/adopt/commit",
                json={"text": "第一场正文", "accepted_canon": False},
            )

            prepare_response = client.post("/api/projects/demo/scene/prepare")
            self.assertEqual(prepare_response.status_code, 200)
            prepare_payload = prepare_response.get_json()
            self.assertEqual(len(prepare_payload["reconcile_items"]), 1)
            self.assertEqual(prepare_payload["proposal"]["summary"], "本场景总结")

            reconcile_response = client.post(
                "/api/projects/demo/scene/reconcile",
                json={"stack_index": 0, "accepted_canon": True},
            )
            self.assertEqual(reconcile_response.status_code, 200)

            commit_response = client.post(
                "/api/projects/demo/scene/commit",
                json={"cold_accepted": True, "summary": "作者确认摘要"},
            )
            self.assertEqual(commit_response.status_code, 200)
            commit_payload = commit_response.get_json()
            self.assertEqual(commit_payload["new_scene_id"], "scene_002")

            synopsis_response = client.get("/api/projects/demo/synopsis")
            synopsis_payload = synopsis_response.get_json()
            self.assertEqual(synopsis_payload["global"], "全书梗概")
            self.assertEqual(synopsis_payload["scenes"][0]["summary"], "作者确认摘要")

    def test_home_page_and_project_page_render(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = _build_app(Path(tmp))
            client = app.test_client()

            home = client.get("/")
            self.assertEqual(home.status_code, 200)
            home_html = home.get_data(as_text=True)
            self.assertIn("LNAgent Web", home_html)
            self.assertIn("demo", home_html)
            self.assertIn("create-project-form", home_html)
            self.assertIn("/static/style.css", home_html)

            project_page = client.get("/projects/demo")
            self.assertEqual(project_page.status_code, 200)
            project_html = project_page.get_data(as_text=True)
            self.assertIn("项目：demo", project_html)
            self.assertIn("data-project-id='demo'", project_html)
            self.assertIn("data-action='send'", project_html)
            self.assertIn("/static/project.js", project_html)

    def test_static_assets_are_served(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = _build_app(Path(tmp))
            client = app.test_client()

            css = client.get("/static/style.css")
            self.assertEqual(css.status_code, 200)
            self.assertIn("text/css", css.content_type)
            self.assertIn(b"--bg", css.body)

            js = client.get("/static/project.js")
            self.assertEqual(js.status_code, 200)
            self.assertIn(b"refreshAll", js.body)

            missing = client.get("/static/not-found.js")
            self.assertEqual(missing.status_code, 404)

    def test_create_project_via_api(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = _build_app(Path(tmp), create_demo=False)
            client = app.test_client()

            response = client.post(
                "/api/projects",
                json={
                    "project_id": "new-book",
                    "meta": {
                        "title": "新书",
                        "style": "轻小说",
                        "world_rules": ["魔法存在"],
                    },
                },
            )
            self.assertEqual(response.status_code, 201)
            payload = response.get_json()
            self.assertEqual(payload["project_id"], "new-book")

            list_response = client.get("/api/projects")
            list_payload = list_response.get_json()
            self.assertEqual([item["project_id"] for item in list_payload["projects"]], ["new-book"])


class AppServiceTest(unittest.TestCase):
    def test_open_project_reuses_same_session_instance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = _build_service(Path(tmp))

            first = service.open_project("demo")
            second = service.open_project("demo")

            self.assertIs(first.session, second.session)

    def test_send_keeps_last_candidate_for_followup_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = _build_service(Path(tmp), replies=["候选正文"])

            send_payload = service.send_message("demo", "继续写")
            self.assertEqual(send_payload["last_candidate"], "候选正文")

            adopt_prepare = service.prepare_adopt("demo", None)
            self.assertEqual(adopt_prepare["text"], "候选正文")


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _ReplyModel:
    def __init__(self, replies: list[str] | None = None) -> None:
        self._replies = list(replies or ["模型回复"])
        self._index = 0

    def invoke(self, messages: list[object]) -> _FakeResponse:
        if self._index < len(self._replies):
            content = self._replies[self._index]
            self._index += 1
        else:
            content = self._replies[-1]
        return _FakeResponse(content)


class _StubCanonExtractor:
    def __init__(self, canon_name: str = "莉亚", fix_canon_name: str | None = None) -> None:
        self._canon_name = canon_name
        self._fix_canon_name = fix_canon_name or canon_name

    def extract_patch(self, adopted_text: str, canon: HotCanon) -> HotCanon:
        return HotCanon(characters=[{"name": self._canon_name}], world=canon.world)

    def extract_fix_patch(self, correction_intent: str, canon: HotCanon) -> HotCanon:
        return HotCanon(characters=[{"name": self._fix_canon_name}], world=canon.world)


class _StubColdExtractor:
    def propose(
        self,
        scene_id: str,
        adopted_text: str,
        *,
        meta: NovelMeta | None = None,
    ) -> ColdProposal:
        return ColdProposal(
            location="学院",
            time="夜晚",
            summary="本场景总结",
            key_points=["关键事件"],
        )

    def rollup_global(self, old_global: str, scene_entry: object) -> str:
        return "全书梗概"


def _build_app(
    root: Path,
    *,
    replies: list[str] | None = None,
    canon_name: str = "莉亚",
    fix_canon_name: str | None = None,
    create_demo: bool = True,
):
    service = _build_service(
        root,
        replies=replies,
        canon_name=canon_name,
        fix_canon_name=fix_canon_name,
        create_demo=create_demo,
    )
    return create_web_app(service)


def _build_service(
    root: Path,
    *,
    replies: list[str] | None = None,
    canon_name: str = "莉亚",
    fix_canon_name: str | None = None,
    create_demo: bool = True,
) -> AppService:
    projects_dir = root / "projects"
    service = AppService(
        projects_dir=projects_dir,
        settings_factory=lambda: Settings(api_key="test-key", model="fake-model", projects_dir=projects_dir),
        model_factory=lambda project_id: _ReplyModel(replies),
        canon_extractor_factory=lambda model: _StubCanonExtractor(canon_name, fix_canon_name),
        cold_extractor_factory=lambda model: _StubColdExtractor(),
    )
    if create_demo:
        service.create_project(
            "demo",
            {
                "title": "测试书",
                "style": "轻小说",
                "world_rules": ["魔法存在"],
            },
        )
    return service


if __name__ == "__main__":
    unittest.main()
