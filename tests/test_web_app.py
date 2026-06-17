"""Web 应用服务与 API 集成测试。"""

from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path

from lnagent.app_service import AppService
from lnagent.config import Settings
from lnagent.memory.cold_archive import ColdProposal
from lnagent.memory.models import HotCanon, NovelMeta
from lnagent.llm import extract_stream_chunk_content
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
            self.assertIn("/static/style.css?v=", home_html)

            project_page = client.get("/projects/demo")
            self.assertEqual(project_page.status_code, 200)
            project_html = project_page.get_data(as_text=True)
            self.assertIn("项目：demo", project_html)
            self.assertIn("data-project-id='demo'", project_html)
            self.assertIn("<body data-project-id='demo'", project_html)
            self.assertIn("data-action='send'", project_html)
            self.assertIn("/static/project.js?v=", project_html)
            self.assertIn("data-action='undo'", project_html)
            self.assertIn("config-form", project_html)
            self.assertIn("writing-progress", project_html)
            self.assertIn("mode-toggle", project_html)
            self.assertIn("data-mode='writing'", project_html)
            self.assertIn("data-mode='discussion'", project_html)
            self.assertIn("discussion-brief", project_html)
            self.assertIn("discussion-messages", project_html)
            self.assertIn("discussion-weak-hint", project_html)
            self.assertIn("brief-panel", project_html)
            self.assertIn("brief-actions", project_html)
            self.assertIn("brief-panel-desc", project_html)
            self.assertIn("brief-edit-form", project_html)
            self.assertIn("data-action='discussion-brief-save'", project_html)
            self.assertIn("data-action='discussion-edit-toggle'", project_html)
            self.assertIn("meta-form", project_html)
            self.assertIn("meta-style-input", project_html)
            self.assertIn("meta-pov-input", project_html)
            self.assertIn("meta-tense-input", project_html)
            self.assertIn("meta-genre-input", project_html)
            self.assertIn("meta-tone-input", project_html)
            self.assertIn("meta-target-audience-input", project_html)
            self.assertIn("meta-taboos-input", project_html)
            self.assertIn("meta-narrative-rules-input", project_html)
            self.assertIn("data-action='meta-save'", project_html)
            self.assertIn("meta-form-note", project_html)
            brief_panel_start = project_html.index("brief-panel")
            refresh_in_panel = project_html.index("data-action='discussion-refresh'", brief_panel_start)
            clear_in_panel = project_html.index("data-action='discussion-clear'", brief_panel_start)
            self.assertLess(refresh_in_panel, project_html.index("</aside>"))
            self.assertLess(clear_in_panel, project_html.index("</aside>"))
            self.assertNotIn("id='config-summary' class='kv-list'", project_html)

    def test_static_assets_are_served(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = _build_app(Path(tmp))
            client = app.test_client()

            css = client.get("/static/style.css")
            self.assertEqual(css.status_code, 200)
            self.assertIn("text/css", css.content_type)
            self.assertEqual(css.headers.get("Cache-Control"), "no-cache, must-revalidate")
            self.assertIn(b"--bg", css.body)
            self.assertIn(b"brief-panel", css.body)
            self.assertIn(b"brief-status-note", css.body)
            self.assertIn(b"brief-edit-form", css.body)
            self.assertIn(b"meta-form", css.body)
            self.assertIn(b"meta-form-note", css.body)
            self.assertIn(b"meta-readonly-box", css.body)

            js = client.get("/static/project.js")
            self.assertEqual(js.status_code, 200)
            self.assertIn(b"refreshAll", js.body)
            self.assertIn(b"/discussion/send", js.body)
            self.assertIn(b"/discussion/get", js.body)
            self.assertIn(b"/discussion/refresh", js.body)
            self.assertIn(b"/discussion/brief/save", js.body)
            self.assertIn(b"saveDiscussionBrief", js.body)
            self.assertIn(b"messageCount", js.body)
            self.assertIn(b"/writing/send/stream", js.body)
            self.assertIn(b"mode-toggle", js.body)
            self.assertIn(b"setMode(", js.body)
            self.assertIn(b"saveMeta", js.body)
            self.assertIn(b"/meta", js.body)
            self.assertIn(b"meta-style-input", js.body)
            self.assertIn(b"meta-form", js.body)

            render_js = client.get("/static/render.js")
            self.assertEqual(render_js.status_code, 200)
            self.assertIn(b"renderMetaSummary", render_js.body)
            self.assertIn(b"renderMetaEditForm", render_js.body)
            self.assertIn(b"meta-form-note", render_js.body)
            self.assertIn(b"textToMetaList", render_js.body)
            self.assertIn(b"metaListToText", render_js.body)
            self.assertIn(b"renderDiscussionBrief", render_js.body)
            self.assertIn(b"deriveDiscussionBriefStatus", render_js.body)
            self.assertIn(b"formatBriefTimestamp", render_js.body)
            self.assertIn(b"brief-status-note", render_js.body)
            self.assertIn("原始讨论已清空".encode("utf-8"), render_js.body)
            self.assertIn(b"briefItemsToText", render_js.body)
            self.assertIn(b"textToBriefItems", render_js.body)
            self.assertIn(b"renderDiscussionMessages", render_js.body)

            missing = client.get("/static/not-found.js")
            self.assertEqual(missing.status_code, 404)

    def test_undo_export_and_config_apis(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = _build_app(Path(tmp), replies=["候选正文"], canon_name="莉亚")
            client = app.test_client()

            client.post("/api/projects/demo/open")
            client.post("/api/projects/demo/send", json={"text": "继续写"})
            client.post(
                "/api/projects/demo/adopt/commit",
                json={"text": "第一场正文", "accepted_canon": True},
            )

            undo_response = client.post("/api/projects/demo/undo")
            self.assertEqual(undo_response.status_code, 200)
            undo_payload = undo_response.get_json()
            self.assertEqual(undo_payload["undone_text"], "第一场正文")
            self.assertEqual(undo_payload["session"]["adopted_prose"], "")

            client.post(
                "/api/projects/demo/adopt/commit",
                json={"text": "恢复后的正文", "accepted_canon": False},
            )

            export_response = client.post("/api/projects/demo/export")
            self.assertEqual(export_response.status_code, 200)
            export_payload = export_response.get_json()
            self.assertIn("恢复后的正文", export_payload["content"])
            self.assertTrue(export_payload["filename"].endswith(".md"))

            config_response = client.get("/api/projects/demo/config")
            self.assertEqual(config_response.status_code, 200)
            config_payload = config_response.get_json()
            self.assertIn("context.char_budget", config_payload["available_keys"])
            self.assertIn("context.char_budget", config_payload["flat"])

            update_response = client.post(
                "/api/projects/demo/config",
                json={
                    "action": "set",
                    "key": "context.char_budget",
                    "value": 500000,
                },
            )
            self.assertEqual(update_response.status_code, 200)
            update_payload = update_response.get_json()
            self.assertEqual(update_payload["config"]["flat"]["context.char_budget"], 500000)

            manuscripts_response = client.get("/api/projects/demo/manuscripts")
            self.assertEqual(manuscripts_response.status_code, 200)
            manuscripts_payload = manuscripts_response.get_json()
            self.assertEqual(manuscripts_payload["current_scene_id"], "scene_001")
            self.assertEqual(len(manuscripts_payload["scenes"]), 1)

    def test_send_stream_sse_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = _build_app(Path(tmp), replies=["流式正文"])
            client = app.test_client()

            client.post("/api/projects/demo/open")
            response = client.post(
                "/api/projects/demo/send/stream",
                json={"text": "请续写"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn("text/event-stream", response.content_type)
            body = response.get_data(as_text=True)
            self.assertIn("event: token", body)
            self.assertIn("event: done", body)
            self.assertIn("流式正文", body)

            state_response = client.get("/api/projects/demo/session")
            state_payload = state_response.get_json()
            self.assertEqual(state_payload["last_candidate"], "流式正文")
            self.assertEqual(len(state_payload["messages"]), 2)

    def test_send_stream_handles_cumulative_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = _build_app(
                Path(tmp),
                replies=["累积流式正文"],
                model_factory=lambda _project_id: _CumulativeReplyModel(["累积流式正文"]),
            )
            client = app.test_client()

            client.post("/api/projects/demo/open")
            response = client.post(
                "/api/projects/demo/send/stream",
                json={"text": "请续写"},
            )
            self.assertEqual(response.status_code, 200)
            body = response.get_data(as_text=True)
            self.assertNotIn("累累积", body)

            state_response = client.get("/api/projects/demo/session")
            state_payload = state_response.get_json()
            self.assertEqual(state_payload["last_candidate"], "累积流式正文")
            self.assertEqual(
                state_payload["messages"][-1]["content"],
                "累积流式正文",
            )

    def test_send_stream_continues_after_consumer_stops_reading(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = _build_app(
                Path(tmp),
                replies=["完整流式正文"],
                model_factory=lambda _project_id: _InterruptibleReplyModel(["完整流式正文"]),
            )
            client = app.test_client()

            client.post("/api/projects/demo/open")
            payload = json.dumps({"text": "请续写"}, ensure_ascii=False).encode("utf-8")
            response = app.handle_wsgi(
                {
                    "REQUEST_METHOD": "POST",
                    "PATH_INFO": "/api/projects/demo/send/stream",
                    "QUERY_STRING": "",
                    "wsgi.input": __import__("io").BytesIO(payload),
                    "CONTENT_LENGTH": str(len(payload)),
                    "CONTENT_TYPE": "application/json",
                }
            )

            iterator = response.iter_body()
            next(iterator)
            iterator.close()
            time.sleep(0.05)

            state_response = client.get("/api/projects/demo/session")
            state_payload = state_response.get_json()
            self.assertEqual(state_payload["last_candidate"], "完整流式正文")
            self.assertEqual(state_payload["messages"][-1]["content"], "完整流式正文")

    def test_discussion_routes_round_trip_refresh_and_clear(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = _build_app(
                Path(tmp),
                replies=[
                    "先把学院纪律讨论清楚。",
                    json.dumps(
                        {
                            "todo_items": ["确定学院纪律"],
                            "constraints": ["禁止公开私斗"],
                            "open_questions": ["谁来执行纪律"],
                        },
                        ensure_ascii=False,
                    ),
                ],
            )
            client = app.test_client()

            client.post("/api/projects/demo/open")
            send_response = client.post(
                "/api/projects/demo/discussion/send",
                json={"text": "先讨论学院纪律"},
            )
            self.assertEqual(send_response.status_code, 200)
            send_payload = send_response.get_json()
            self.assertEqual(send_payload["reply"], "先把学院纪律讨论清楚。")
            self.assertEqual(send_payload["scene_id"], "scene_001")
            self.assertEqual(
                [item["content"] for item in send_payload["messages"]],
                ["先讨论学院纪律", "先把学院纪律讨论清楚。"],
            )
            self.assertTrue(send_payload["brief"]["dirty"])

            session_response = client.get("/api/projects/demo/session")
            session_payload = session_response.get_json()
            self.assertIsNone(session_payload["last_candidate"])
            self.assertEqual(session_payload["messages"], [])

            get_response = client.get("/api/projects/demo/discussion/get")
            self.assertEqual(get_response.status_code, 200)
            get_payload = get_response.get_json()
            self.assertEqual(get_payload["scene_id"], "scene_001")
            self.assertEqual(len(get_payload["messages"]), 2)
            self.assertTrue(get_payload["brief"]["dirty"])

            refresh_response = client.post("/api/projects/demo/discussion/refresh")
            self.assertEqual(refresh_response.status_code, 200)
            refresh_payload = refresh_response.get_json()
            self.assertEqual(refresh_payload["brief"]["todo_items"], ["确定学院纪律"])
            self.assertEqual(refresh_payload["brief"]["constraints"], ["禁止公开私斗"])
            self.assertEqual(refresh_payload["brief"]["open_questions"], ["谁来执行纪律"])
            self.assertFalse(refresh_payload["brief"]["dirty"])

            clear_response = client.post("/api/projects/demo/discussion/clear")
            self.assertEqual(clear_response.status_code, 200)
            clear_payload = clear_response.get_json()
            self.assertEqual(clear_payload["messages"], [])
            self.assertEqual(clear_payload["brief"]["todo_items"], ["确定学院纪律"])
            self.assertFalse(clear_payload["brief"]["dirty"])
            self.assertIn("updated_at", clear_payload["brief"])
            self.assertEqual(clear_payload["brief"]["constraints"], ["禁止公开私斗"])
            self.assertEqual(clear_payload["brief"]["open_questions"], ["谁来执行纪律"])

    def test_discussion_brief_save_via_api(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = _build_app(Path(tmp))
            client = app.test_client()

            client.post("/api/projects/demo/open")
            save_response = client.post(
                "/api/projects/demo/discussion/brief/save",
                json={
                    "todo_items": ["  写交付场景  ", ""],
                    "constraints": ["保持轻松基调", "  "],
                    "open_questions": "莫丽恩是否点破",
                },
            )
            self.assertEqual(save_response.status_code, 200)
            save_payload = save_response.get_json()
            self.assertEqual(save_payload["scene_id"], "scene_001")
            self.assertEqual(save_payload["brief"]["todo_items"], ["写交付场景"])
            self.assertEqual(save_payload["brief"]["constraints"], ["保持轻松基调"])
            self.assertEqual(save_payload["brief"]["open_questions"], ["莫丽恩是否点破"])
            self.assertFalse(save_payload["brief"]["dirty"])
            self.assertTrue(save_payload["brief"]["updated_at"])

            get_payload = client.get("/api/projects/demo/discussion/get").get_json()
            self.assertEqual(get_payload["brief"]["todo_items"], ["写交付场景"])
            self.assertFalse(get_payload["brief"]["dirty"])

            writing_response = client.post(
                "/api/projects/demo/writing/send",
                json={"text": "按 brief 写一段"},
            )
            self.assertEqual(writing_response.status_code, 200)

    def test_update_meta_via_api_persists_refreshes_cache_and_affects_next_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            model = _RecordingReplyModel(["按新设定生成的正文"])
            app = _build_app(
                Path(tmp),
                model_factory=lambda _project_id: model,
            )
            client = app.test_client()

            client.post("/api/projects/demo/open")
            update_response = client._request(
                "PUT",
                "/api/projects/demo/meta",
                {
                    "title": "不应被修改的标题",
                    "style": "严肃奇幻",
                    "pov": "第一人称",
                    "tense": "过去式",
                    "genre": "学院奇幻",
                    "tone": "克制",
                    "target_audience": "青年读者",
                    "taboos": ["避免说教", "  ", "避免跳脱"],
                    "narrative_rules": ["聚焦主角感知", "单场景内避免大段回忆"],
                    "world": {"rules": ["不应被修改的世界规则"]},
                },
            )
            self.assertEqual(update_response.status_code, 200)
            update_payload = update_response.get_json()
            self.assertEqual(update_payload["style"], "严肃奇幻")
            self.assertEqual(update_payload["pov"], "第一人称")
            self.assertEqual(update_payload["tense"], "过去式")
            self.assertEqual(update_payload["genre"], "学院奇幻")
            self.assertEqual(update_payload["tone"], "克制")
            self.assertEqual(update_payload["target_audience"], "青年读者")
            self.assertEqual(update_payload["taboos"], ["避免说教", "避免跳脱"])
            self.assertEqual(
                update_payload["narrative_rules"],
                ["聚焦主角感知", "单场景内避免大段回忆"],
            )
            self.assertEqual(update_payload["title"], "测试书")
            self.assertEqual(update_payload["world"]["rules"], ["魔法存在"])

            overview_response = client.get("/api/projects/demo")
            self.assertEqual(overview_response.status_code, 200)
            overview_payload = overview_response.get_json()
            self.assertEqual(overview_payload["style"], "严肃奇幻")

            stored_meta = json.loads(
                (Path(tmp) / "projects" / "demo" / "meta.json").read_text(encoding="utf-8")
            )
            self.assertEqual(stored_meta["style"], "严肃奇幻")
            self.assertEqual(stored_meta["pov"], "第一人称")
            self.assertEqual(stored_meta["tense"], "过去式")
            self.assertEqual(stored_meta["target_audience"], "青年读者")
            self.assertEqual(stored_meta["title"], "测试书")
            self.assertEqual(stored_meta["world"]["rules"], ["魔法存在"])

            writing_response = client.post(
                "/api/projects/demo/writing/send",
                json={"text": "按新的叙事配置写一段"},
            )
            self.assertEqual(writing_response.status_code, 200)
            self.assertEqual(writing_response.get_json()["reply"], "按新设定生成的正文")

            system_prompt = model.last_messages[0].content
            assert isinstance(system_prompt, str)
            self.assertIn("文风：严肃奇幻", system_prompt)
            self.assertIn("叙述人称：第一人称", system_prompt)
            self.assertIn("叙事时态：过去式", system_prompt)
            self.assertIn("目标读者：青年读者", system_prompt)
            self.assertIn("叙事规则：", system_prompt)

    def test_update_meta_rejects_empty_style(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = _build_app(Path(tmp))
            client = app.test_client()

            client.post("/api/projects/demo/open")
            update_response = client._request(
                "PUT",
                "/api/projects/demo/meta",
                {"style": "   "},
            )
            self.assertEqual(update_response.status_code, 400)
            self.assertEqual(update_response.get_json()["error"], "style 不能为空")

            meta_response = client.get("/api/projects/demo/meta")
            self.assertEqual(meta_response.status_code, 200)
            self.assertEqual(meta_response.get_json()["style"], "轻小说")

    def test_writing_route_and_legacy_send_alias_share_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = _build_app(
                Path(tmp),
                replies=[
                    "先讨论人物关系。",
                    json.dumps({"todo_items": ["先定人物关系"]}, ensure_ascii=False),
                    "第一版候选正文",
                    "第二版候选正文",
                ],
            )
            client = app.test_client()

            client.post("/api/projects/demo/open")
            client.post(
                "/api/projects/demo/discussion/send",
                json={"text": "先讨论人物关系"},
            )

            writing_response = client.post(
                "/api/projects/demo/writing/send",
                json={"text": "请写第一段"},
            )
            self.assertEqual(writing_response.status_code, 200)
            writing_payload = writing_response.get_json()
            self.assertEqual(writing_payload["reply"], "第一版候选正文")
            self.assertEqual(writing_payload["last_candidate"], "第一版候选正文")

            discussion_state = client.get("/api/projects/demo/discussion/get").get_json()
            self.assertEqual(len(discussion_state["messages"]), 2)
            self.assertEqual(discussion_state["brief"]["todo_items"], ["先定人物关系"])
            self.assertFalse(discussion_state["brief"]["dirty"])

            legacy_response = client.post(
                "/api/projects/demo/send",
                json={"text": "继续写第二段"},
            )
            self.assertEqual(legacy_response.status_code, 200)
            legacy_payload = legacy_response.get_json()
            self.assertEqual(legacy_payload["reply"], "第二版候选正文")
            self.assertEqual(legacy_payload["last_candidate"], "第二版候选正文")

    def test_writing_stream_route_and_legacy_alias_keep_sse_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = _build_app(Path(tmp), replies=["流式正文", "兼容流式正文"])
            client = app.test_client()

            client.post("/api/projects/demo/open")
            writing_stream = client.post(
                "/api/projects/demo/writing/send/stream",
                json={"text": "请续写"},
            )
            self.assertEqual(writing_stream.status_code, 200)
            self.assertIn("text/event-stream", writing_stream.content_type)
            writing_body = writing_stream.get_data(as_text=True)
            self.assertIn("event: token", writing_body)
            self.assertIn("event: done", writing_body)
            self.assertIn("流式正文", writing_body)

            legacy_stream = client.post(
                "/api/projects/demo/send/stream",
                json={"text": "再续写一段"},
            )
            self.assertEqual(legacy_stream.status_code, 200)
            self.assertIn("text/event-stream", legacy_stream.content_type)
            legacy_body = legacy_stream.get_data(as_text=True)
            self.assertIn("event: token", legacy_body)
            self.assertIn("event: done", legacy_body)
            self.assertIn("兼容流式正文", legacy_body)

            state_response = client.get("/api/projects/demo/session")
            state_payload = state_response.get_json()
            self.assertEqual(state_payload["last_candidate"], "兼容流式正文")

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
    def test_extract_stream_chunk_content_reads_string_and_chunk(self) -> None:
        self.assertEqual(extract_stream_chunk_content(_FakeChunk("片段")), "片段")
        self.assertEqual(extract_stream_chunk_content("直接文本"), "直接文本")
        self.assertEqual(
            extract_stream_chunk_content(
                _FakeChunk([{"type": "output_text", "text": "输出"}])
            ),
            "输出",
        )
        self.assertEqual(
            extract_stream_chunk_content(_FakeChunk([{"text": "裸字段"}])),
            "裸字段",
        )
        self.assertEqual(
            extract_stream_chunk_content(
                _FakeChunk(
                    [
                        {"type": "text", "text": "甲"},
                        {"type": "text", "text": "乙"},
                    ]
                )
            ),
            "甲乙",
        )

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


class _FakeChunk:
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

    def stream(self, messages: list[object]):
        reply = self.invoke(messages).content
        for char in reply:
            yield _FakeChunk(char)


class _CumulativeReplyModel(_ReplyModel):
    def stream(self, messages: list[object]):
        reply = self.invoke(messages).content
        cumulative = ""
        for char in reply:
            cumulative += char
            yield _FakeChunk(cumulative)


class _InterruptibleReplyModel(_ReplyModel):
    def stream(self, messages: list[object]):
        reply = self.invoke(messages).content
        for char in reply:
            yield _FakeChunk(char)


class _RecordingReplyModel(_ReplyModel):
    def __init__(self, replies: list[str] | None = None) -> None:
        super().__init__(replies)
        self.last_messages: list[object] = []

    def invoke(self, messages: list[object]) -> _FakeResponse:
        self.last_messages = list(messages)
        return super().invoke(messages)


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
    model_factory=None,
):
    service = _build_service(
        root,
        replies=replies,
        canon_name=canon_name,
        fix_canon_name=fix_canon_name,
        create_demo=create_demo,
        model_factory=model_factory,
    )
    return create_web_app(service)


def _build_service(
    root: Path,
    *,
    replies: list[str] | None = None,
    canon_name: str = "莉亚",
    fix_canon_name: str | None = None,
    create_demo: bool = True,
    model_factory=None,
) -> AppService:
    projects_dir = root / "projects"
    factory = model_factory or (lambda _project_id: _ReplyModel(replies))
    service = AppService(
        projects_dir=projects_dir,
        settings_factory=lambda: Settings(api_key="test-key", model="fake-model", projects_dir=projects_dir),
        model_factory=factory,
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
