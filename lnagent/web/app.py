"""Minimal Web app for LNAgent first milestone."""

from __future__ import annotations

import json
from html import escape
from io import BytesIO
from typing import Any
from urllib.parse import parse_qs

from lnagent.app_service import AppService


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
        return self._app.handle_wsgi(environ)


class SimpleWebApp:
    def __init__(self, service: AppService) -> None:
        self._service = service

    def test_client(self) -> SimpleTestClient:
        return SimpleTestClient(self)

    def handle_wsgi(self, environ: dict[str, Any]) -> SimpleResponse:
        method = environ.get("REQUEST_METHOD", "GET")
        path = environ.get("PATH_INFO", "/")
        try:
            if method == "GET" and path == "/":
                return self._html_response(_render_home(self._service.list_projects()))
            if method == "GET" and path.startswith("/projects/"):
                project_id = path.split("/", 2)[2]
                overview = self._service.get_project_overview(project_id)
                session = self._service.get_session_state(project_id)
                return self._html_response(_render_project(project_id, overview, session))
            if path.startswith("/api/"):
                return self._handle_api(method, path, environ)
            return self._json_response({"error": "not found"}, status=404)
        except ValueError as exc:
            return self._json_response({"error": str(exc)}, status=400)

    def _handle_api(self, method: str, path: str, environ: dict[str, Any]) -> SimpleResponse:
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
        if method == "GET" and suffix == "/session":
            return self._json_response(self._service.get_session_state(project_id))
        if method == "GET" and suffix == "/manuscript":
            return self._json_response(self._service.get_manuscript(project_id))
        if method == "POST" and suffix == "/send":
            return self._json_response(self._service.send_message(project_id, payload.get("text", "")))
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


def _render_home(projects: list[Any]) -> str:
    items = "".join(
        f'<li><a href="/projects/{escape(item.project_id)}">{escape(item.project_id)}</a> — {escape(item.title)}</li>'
        for item in projects
    )
    if not items:
        items = "<li>暂无项目</li>"
    return (
        "<html><head><meta charset='utf-8'><title>LNAgent Web</title></head><body>"
        "<h1>LNAgent Web</h1>"
        "<h2>项目列表</h2>"
        f"<ul>{items}</ul>"
        "</body></html>"
    )


def _render_project(project_id: str, overview: dict, session: dict) -> str:
    adopted = escape(str(session.get("adopted_prose", "")))
    candidate = escape(str(session.get("last_candidate") or ""))
    return (
        "<html><head><meta charset='utf-8'><title>LNAgent Project</title></head><body>"
        f"<h1>项目：{escape(project_id)}</h1>"
        f"<p>书名：{escape(str(overview.get('title', '')))}</p>"
        f"<p>当前场景：{escape(str(session.get('scene_id', '')))}</p>"
        f"<h2>当前候选</h2><pre>{candidate}</pre>"
        f"<h2>已采纳正文</h2><pre>{adopted}</pre>"
        "</body></html>"
    )
