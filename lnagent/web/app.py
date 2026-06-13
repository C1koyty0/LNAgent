"""Minimal Web app for LNAgent first milestone."""

from __future__ import annotations

import json
import mimetypes
from html import escape
from io import BytesIO
from pathlib import Path
from typing import Any

from lnagent.app_service import AppService

STATIC_DIR = Path(__file__).resolve().parent / "static"


class SimpleResponse:
    def __init__(
        self,
        body: bytes,
        *,
        status: int = 200,
        content_type: str = "text/html; charset=utf-8",
    ) -> None:
        self.status_code = status
        self.body = body
        self.content_type = content_type

    def get_data(self, as_text: bool = False) -> str | bytes:
        if as_text:
            return self.body.decode("utf-8")
        return self.body

    def get_json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))


class StreamResponse:
    def __init__(
        self,
        chunks: Any,
        *,
        status: int = 200,
        content_type: str = "text/event-stream; charset=utf-8",
    ) -> None:
        self.status_code = status
        self.content_type = content_type
        self._chunks = chunks

    def iter_body(self):
        yield from self._chunks


class SimpleTestClient:
    def __init__(self, app: "SimpleWebApp") -> None:
        self._app = app

    def get(self, path: str) -> SimpleResponse:
        return self._request("GET", path, None)

    def post(self, path: str, json: dict | None = None) -> SimpleResponse:
        return self._request("POST", path, json)

    def _request(self, method: str, path: str, payload: dict | None) -> SimpleResponse:
        body = b""
        content_length = "0"
        content_type = ""
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            content_length = str(len(body))
            content_type = "application/json"

        environ = {
            "REQUEST_METHOD": method,
            "PATH_INFO": path,
            "QUERY_STRING": "",
            "wsgi.input": BytesIO(body),
            "CONTENT_LENGTH": content_length,
            "CONTENT_TYPE": content_type,
        }
        return _materialize_response(self._app.handle_wsgi(environ))


def _materialize_response(response: SimpleResponse | StreamResponse) -> SimpleResponse:
    if isinstance(response, StreamResponse):
        body = b"".join(response.iter_body())
        return SimpleResponse(body, status=response.status_code, content_type=response.content_type)
    return response


class SimpleWebApp:
    def __init__(self, service: AppService) -> None:
        self._service = service

    def test_client(self) -> SimpleTestClient:
        return SimpleTestClient(self)

    def handle_wsgi(self, environ: dict[str, Any]) -> SimpleResponse | StreamResponse:
        method = environ.get("REQUEST_METHOD", "GET")
        path = environ.get("PATH_INFO", "/")
        try:
            if method == "GET" and path == "/":
                return self._html_response(_render_home(self._service.list_projects()))
            if method == "GET" and path.startswith("/projects/"):
                project_id = path.split("/", 2)[2]
                return self._html_response(_render_project(project_id))
            if method == "GET" and path.startswith("/static/"):
                return self._serve_static(path[len("/static/") :])
            if path.startswith("/api/"):
                return self._handle_api(method, path, environ)
            return self._json_response({"error": "not found"}, status=404)
        except ValueError as exc:
            return self._json_response({"error": str(exc)}, status=400)

    def _handle_api(self, method: str, path: str, environ: dict[str, Any]) -> SimpleResponse | StreamResponse:
        payload = _read_json_body(environ)
        if method == "GET" and path == "/api/projects":
            return self._json_response(
                {"projects": [item.__dict__ for item in self._service.list_projects()]}
            )
        if method == "POST" and path == "/api/projects":
            result = self._service.create_project(payload.get("project_id", ""), payload.get("meta", {}))
            return self._json_response(result, status=201)

        project_id, suffix = _match_project_api(path)
        if project_id is None:
            return self._json_response({"error": "not found"}, status=404)

        if method == "GET" and suffix == "":
            return self._json_response(self._service.get_project_overview(project_id))
        if method == "POST" and suffix == "/open":
            handle = self._service.open_project(project_id)
            return self._json_response(
                {
                    "project_id": handle.project_id,
                    "scene_id": handle.session.scene_id,
                    "title": handle.meta.title,
                }
            )
        if method == "GET" and suffix == "/meta":
            return self._json_response(self._service.get_meta(project_id))
        if method == "GET" and suffix == "/canon":
            return self._json_response(self._service.get_canon(project_id))
        if method == "GET" and suffix == "/synopsis":
            return self._json_response(self._service.get_synopsis(project_id))
        if method == "GET" and suffix == "/config":
            return self._json_response(self._service.get_config(project_id))
        if method == "POST" and suffix == "/config":
            raw_value = payload.get("value")
            parsed_value = None if raw_value is None else int(raw_value)
            return self._json_response(
                self._service.update_config(
                    project_id,
                    action=str(payload.get("action", "")),
                    key=str(payload.get("key", "")),
                    value=parsed_value,
                )
            )
        if method == "GET" and suffix == "/manuscripts":
            return self._json_response(self._service.list_manuscripts(project_id))
        if method == "GET" and suffix == "/session":
            return self._json_response(self._service.get_session_state(project_id))
        if method == "GET" and suffix == "/manuscript":
            return self._json_response(self._service.get_manuscript(project_id))
        if method == "POST" and suffix == "/undo":
            return self._json_response(self._service.undo_last_adopt(project_id))
        if method == "POST" and suffix == "/export":
            output_path = payload.get("output_path")
            return self._json_response(
                self._service.export_manuscript(
                    project_id,
                    str(output_path) if output_path else None,
                )
            )
        if method == "POST" and suffix == "/send/stream":
            return self._sse_response(
                self._service.stream_message(project_id, str(payload.get("text", "")))
            )
        if method == "POST" and suffix == "/writing/send/stream":
            return self._sse_response(
                self._service.stream_writing_message(project_id, str(payload.get("text", "")))
            )
        if method == "POST" and suffix == "/send":
            return self._json_response(self._service.send_message(project_id, payload.get("text", "")))
        if method == "POST" and suffix == "/writing/send":
            return self._json_response(
                self._service.send_writing_message(project_id, payload.get("text", ""))
            )
        if method == "GET" and suffix == "/discussion/get":
            return self._json_response(self._service.get_discussion_state(project_id))
        if method == "POST" and suffix == "/discussion/send":
            return self._json_response(
                self._service.send_discussion_message(project_id, payload.get("text", ""))
            )
        if method == "POST" and suffix == "/discussion/refresh":
            return self._json_response(self._service.refresh_discussion_brief(project_id))
        if method == "POST" and suffix == "/discussion/clear":
            return self._json_response(self._service.clear_discussion_messages(project_id))
        if method == "POST" and suffix == "/adopt/prepare":
            return self._json_response(self._service.prepare_adopt(project_id, payload.get("text")))
        if method == "POST" and suffix == "/adopt/commit":
            return self._json_response(
                self._service.commit_adopt(
                    project_id,
                    payload.get("text"),
                    accepted_canon=bool(payload.get("accepted_canon", False)),
                )
            )
        if method == "POST" and suffix == "/fix/prepare":
            return self._json_response(self._service.prepare_fix(project_id, payload.get("intent", "")))
        if method == "POST" and suffix == "/fix/commit":
            return self._json_response(
                self._service.commit_fix(
                    project_id,
                    payload.get("intent", ""),
                    accepted_canon=bool(payload.get("accepted_canon", False)),
                )
            )
        if method == "POST" and suffix == "/scene/prepare":
            return self._json_response(self._service.prepare_scene_switch(project_id))
        if method == "POST" and suffix == "/scene/reconcile":
            return self._json_response(
                self._service.apply_scene_reconcile(
                    project_id,
                    int(payload.get("stack_index", -1)),
                    accepted_canon=bool(payload.get("accepted_canon", False)),
                )
            )
        if method == "POST" and suffix == "/scene/commit":
            return self._json_response(
                self._service.commit_scene_switch(
                    project_id,
                    cold_accepted=bool(payload.get("cold_accepted", False)),
                    summary=str(payload.get("summary", "")),
                )
            )
        return self._json_response({"error": "not found"}, status=404)

    def _serve_static(self, relative_path: str) -> SimpleResponse:
        normalized = Path(relative_path)
        if normalized.is_absolute() or ".." in normalized.parts:
            return self._json_response({"error": "not found"}, status=404)
        target = (STATIC_DIR / normalized).resolve()
        if not str(target).startswith(str(STATIC_DIR.resolve())):
            return self._json_response({"error": "not found"}, status=404)
        if not target.is_file():
            return self._json_response({"error": "not found"}, status=404)
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        return SimpleResponse(target.read_bytes(), content_type=content_type)

    @staticmethod
    def _json_response(payload: Any, *, status: int = 200) -> SimpleResponse:
        return SimpleResponse(
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            status=status,
            content_type="application/json; charset=utf-8",
        )

    @staticmethod
    def _html_response(html: str, *, status: int = 200) -> SimpleResponse:
        return SimpleResponse(html.encode("utf-8"), status=status)

    def _sse_response(self, events: Any) -> StreamResponse:
        def chunks():
            for event in events:
                name = str(event.get("event", "message"))
                payload = json.dumps(event.get("data", {}), ensure_ascii=False)
                yield _format_sse(name, payload)

        return StreamResponse(chunks())


def create_web_app(service: AppService) -> SimpleWebApp:
    return SimpleWebApp(service)


def _match_project_api(path: str) -> tuple[str | None, str]:
    prefix = "/api/projects/"
    if not path.startswith(prefix):
        return None, ""
    tail = path[len(prefix) :]
    if "/" in tail:
        project_id, suffix = tail.split("/", 1)
        return project_id, "/" + suffix
    return tail, ""


def _format_sse(event: str, data: str) -> bytes:
    return f"event: {event}\ndata: {data}\n\n".encode("utf-8")


def _read_json_body(environ: dict[str, Any]) -> dict:
    length_text = environ.get("CONTENT_LENGTH", "0") or "0"
    try:
        length = int(length_text)
    except ValueError:
        length = 0
    if length <= 0:
        return {}
    raw = environ["wsgi.input"].read(length)
    if not raw:
        return {}
    data = json.loads(raw.decode("utf-8"))
    return data if isinstance(data, dict) else {}


def _page_shell(*, title: str, body: str, scripts: list[str], body_attrs: str = "") -> str:
    script_tags = "".join(f'<script src="{escape(path)}" defer></script>' for path in scripts)
    return (
        "<!DOCTYPE html>"
        "<html lang='zh-CN'>"
        "<head>"
        "<meta charset='utf-8'>"
        f"<title>{escape(title)}</title>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<link rel='stylesheet' href='/static/style.css'>"
        "</head>"
        f"<body{body_attrs}>{body}{script_tags}</body>"
        "</html>"
    )


def _render_home(projects: list[Any]) -> str:
    items = "".join(
        (
            f"<li>"
            f"<a href='/projects/{escape(item.project_id)}'>{escape(item.project_id)}</a>"
            f"<div class='project-meta'>{escape(item.title)} · {escape(item.style)} · "
            f"{escape(item.current_scene_id)}</div>"
            f"</li>"
        )
        for item in projects
    )
    if not items:
        items = "<li class='hint'>暂无项目，可在下方创建。</li>"

    body = (
        "<div class='page'>"
        "<header class='page-header'>"
        "<div><h1>LNAgent Web</h1><p class='subtitle'>选择项目开始写作，或创建新项目。</p></div>"
        "</header>"
        "<div id='status-message' class='status'></div>"
        "<div class='layout'>"
        "<section class='panel'>"
        "<h2>项目列表</h2>"
        f"<ul class='project-list'>{items}</ul>"
        "</section>"
        "<section class='panel'>"
        "<h2>创建项目</h2>"
        "<form id='create-project-form' class='form-grid'>"
        "<label>project_id<input id='project-id' type='text' required placeholder='例如 my-novel'></label>"
        "<label>书名<input id='project-title' type='text' required placeholder='例如 魔法学院物语'></label>"
        "<label>文风<input id='project-style' type='text' required placeholder='例如 轻小说'></label>"
        "<label>世界规则（每行一条）<textarea id='project-world-rules' placeholder='魔法存在&#10;主角是普通学生'></textarea></label>"
        "<div class='button-row'>"
        "<button id='create-project-button' type='submit' class='primary'>创建并进入</button>"
        "</div>"
        "</form>"
        "</section>"
        "</div>"
        "</div>"
    )
    return _page_shell(title="LNAgent Web", body=body, scripts=["/static/common.js", "/static/home.js"])


def _render_project(project_id: str) -> str:
    safe_id = escape(project_id)
    body = (
        f"<div class='page' data-project-id='{safe_id}'>"
        "<header class='page-header'>"
        f"<div><h1>项目：{safe_id}</h1>"
        "<p class='subtitle'>"
        f"<span id='meta-title'></span> · <span id='meta-style'></span> · "
        "场景 <span id='scene-id'></span>"
        "</p></div>"
        "<a href='/'>返回首页</a>"
        "</header>"
        "<div id='status-message' class='status'></div>"
        "<div id='page-loading' class='page-loading hidden' aria-live='polite'>"
        "<span class='spinner'></span><span id='page-loading-text'>处理中…</span>"
        "</div>"
        "<section id='scene-suggestion' class='panel callout hidden'>"
        "<p id='scene-suggestion-text'></p>"
        "<div class='button-row'>"
        "<button type='button' class='primary' data-action='scene-prepare'>准备切换场景</button>"
        "</div>"
        "</section>"
        "<div class='layout'>"
        "<main>"
        "<section class='panel progress-panel'>"
        "<h2>写作进度</h2>"
        "<div id='writing-progress' class='summary-block'><p class='hint'>加载中…</p></div>"
        "</section>"
        "<section class='panel'>"
        "<div class='panel-header'>"
        "<h2>对话</h2>"
        "<div id='mode-toggle' class='mode-toggle' role='tablist' aria-label='交互模式'>"
        "<button type='button' class='mode-button is-active' data-mode='writing' aria-pressed='true'>写作</button>"
        "<button type='button' class='mode-button' data-mode='discussion' aria-pressed='false'>讨论</button>"
        "</div>"
        "</div>"
        "<p id='mode-description' class='hint'>当前为写作模式：会生成候选正文，并保持 SSE 流式体验。</p>"
        "<div id='discussion-messages' class='messages hidden'><p class='hint'>加载中…</p></div>"
        "<div id='messages' class='messages'><p class='hint'>加载中…</p></div>"
        "<label for='send-input'>发送消息（Ctrl+Enter 发送）</label>"
        "<textarea id='send-input' placeholder='继续写、讨论设定或提出修改…'></textarea>"
        "<div class='button-row'>"
        "<button id='send-button' type='button' class='primary' data-action='send'>发送</button>"
        "</div>"
        "</section>"
        "<section class='panel' id='adopt-panel'>"
        "<h2>候选与采纳</h2>"
        "<p id='discussion-weak-hint' class='hint hidden'>当前为讨论模式：这里保留写作候选与采纳操作，但讨论回复不会覆盖候选正文。</p>"
        "<label for='adopt-text'>采纳正文（可编辑）</label>"
        "<textarea id='adopt-text'></textarea>"
        "<div class='button-row'>"
        "<button type='button' data-action='adopt-prepare'>预览 Canon 变更</button>"
        "<button type='button' class='primary' data-action='adopt-commit-yes'>采纳并接受设定</button>"
        "<button type='button' data-action='adopt-commit-no'>采纳但拒绝设定</button>"
        "<button type='button' class='danger' data-action='undo'>撤销上次采纳</button>"
        "</div>"
        "<pre id='adopt-preview' class='pre-block hidden'></pre>"
        "</section>"
        "<section class='panel' id='fix-panel'>"
        "<h2>设定修正</h2>"
        "<label for='fix-intent'>修正意图</label>"
        "<textarea id='fix-intent' placeholder='例如：把角色名字改成…'></textarea>"
        "<div class='button-row'>"
        "<button type='button' data-action='fix-prepare'>预览修正</button>"
        "<button type='button' class='primary' data-action='fix-commit-yes'>确认修正并接受设定</button>"
        "<button type='button' data-action='fix-commit-no'>确认修正但拒绝设定</button>"
        "</div>"
        "<pre id='fix-preview' class='pre-block hidden'></pre>"
        "</section>"
        "<section id='scene-panel' class='panel hidden scene-panel'>"
        "<h2>场景切换</h2>"
        "<div id='scene-reconcile'></div>"
        "<div id='scene-cold' class='hidden'></div>"
        "<label for='scene-summary'>场景摘要（可编辑）</label>"
        "<textarea id='scene-summary'></textarea>"
        "<div class='button-row'>"
        "<button type='button' data-action='scene-reconcile-yes'>接受 Hot Canon</button>"
        "<button type='button' data-action='scene-reconcile-no'>拒绝 Hot Canon</button>"
        "<button type='button' class='primary' data-action='scene-commit-yes'>接受 Cold 并切换</button>"
        "<button type='button' data-action='scene-commit-no'>拒绝 Cold 并切换</button>"
        "</div>"
        "</section>"
        "<section class='panel'>"
        "<h2>工具</h2>"
        "<div class='button-row'>"
        "<button type='button' data-action='export'>导出全书 Markdown</button>"
        "</div>"
        "<p id='export-result' class='hint'></p>"
        "</section>"
        "<section class='panel'>"
        "<h2>场景切换入口</h2>"
        "<p class='hint'>完成至少一次采纳后，可准备切换到下一场景。</p>"
        "<div class='button-row'>"
        "<button type='button' data-action='scene-prepare'>准备切换场景</button>"
        "</div>"
        "</section>"
        "</main>"
        "<aside>"
        "<section class='panel'>"
        "<h2>会话状态</h2>"
        "<p>距上次采纳轮数：<span id='turns-since-adopt'>0</span></p>"
        "<p id='budget-notice' class='hint'></p>"
        "</section>"
        "<section class='panel brief-panel'>"
        "<h2>Discussion Brief</h2>"
        "<p class='hint brief-panel-desc'>当前场景讨论结论的结构化摘要；写作模式会自动读取，不直接引用原始讨论。</p>"
        "<div class='button-row brief-actions'>"
        "<button type='button' data-action='discussion-refresh'>刷新讨论摘要</button>"
        "<button type='button' data-action='discussion-clear'>清空原始消息</button>"
        "</div>"
        "<div id='discussion-brief' class='summary-block'><p class='hint'>加载中…</p></div>"
        "</section>"
        "<section class='panel'>"
        "<h2>项目配置</h2>"
        "<div id='config-summary'></div>"
        "<form id='config-form' class='form-grid'>"
        "<label>配置项<select id='config-key'></select></label>"
        "<label>值<input id='config-value' type='number' min='0' required></label>"
        "<div class='button-row'>"
        "<button type='submit' class='primary'>更新配置</button>"
        "<button type='button' data-action='config-reset'>重置选中项</button>"
        "<button type='button' data-action='config-reset-all'>重置全部</button>"
        "</div>"
        "</form>"
        "</section>"
        "<section class='panel'>"
        "<h2>Meta</h2>"
        "<div id='meta-summary' class='summary-block'></div>"
        "<details><summary>原始 JSON</summary>"
        "<pre id='meta-json' class='pre-block json-block'></pre></details>"
        "</section>"
        "<section class='panel'>"
        "<h2>Hot Canon</h2>"
        "<div id='canon-summary' class='summary-block'></div>"
        "<details><summary>原始 JSON</summary>"
        "<pre id='canon-json' class='pre-block json-block'></pre></details>"
        "</section>"
        "<section class='panel'>"
        "<h2>Synopsis</h2>"
        "<div id='synopsis-summary' class='summary-block'></div>"
        "<details><summary>原始 JSON</summary>"
        "<pre id='synopsis-json' class='pre-block json-block'></pre></details>"
        "</section>"
        "<section class='panel'>"
        "<h2>Manuscript 索引</h2>"
        "<p class='hint'>完整正文见上方「写作进度」。</p>"
        "<div id='manuscript-list' class='summary-block'></div>"
        "</aside>"
        "</div>"
        "</div>"
    )
    return _page_shell(
        title=f"LNAgent · {project_id}",
        body=body,
        body_attrs=f" data-project-id='{safe_id}'",
        scripts=["/static/common.js", "/static/render.js", "/static/project.js"],
    )
