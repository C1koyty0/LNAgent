"""Web 启动入口。"""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from wsgiref.simple_server import make_server

from lnagent.app_service import AppService
from lnagent.config import Settings
from lnagent.web.app import StreamResponse, create_web_app
from lnagent.web.dev_reload import is_reload_child, run_with_reload, should_enable_reload


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LNAgent Web")
    parser.add_argument(
        "--host",
        default=os.environ.get("LNAGENT_WEB_HOST", "127.0.0.1"),
        help="Web server host (default: %(default)s)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("LNAGENT_WEB_PORT", "8000")),
        help="Web server port (default: %(default)s)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="开发模式：监听 lnagent/ 与静态资源变更并自动重启进程",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def _build_wsgi_app():
    settings = Settings.from_env()
    service = AppService(projects_dir=settings.projects_dir)
    app = create_web_app(service)

    def wsgi_app(environ, start_response):
        response = app.handle_wsgi(environ)
        status_line = f"{response.status_code} {_reason_phrase(response.status_code)}"
        if isinstance(response, StreamResponse):
            headers = [
                ("Content-Type", response.content_type),
                ("Cache-Control", "no-cache"),
                ("X-Accel-Buffering", "no"),
            ]
            start_response(status_line, headers)
            return response.iter_body()

        headers = [
            ("Content-Type", response.content_type),
            ("Content-Length", str(len(response.body))),
        ]
        for key, value in response.headers.items():
            headers.append((key, value))
        start_response(status_line, headers)
        return [response.body]

    return wsgi_app


def run_server(host: str, port: int) -> None:
    server = make_server(host, port, _build_wsgi_app())
    print(f"LNAgent Web 已启动: http://{host}:{port}")
    if not is_reload_child():
        print("提示：修改 JS/CSS 后刷新页面即可；也可使用 --reload 自动重启 Python 进程。")
    server.serve_forever()


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    child_argv = ["--host", args.host, "--port", str(args.port)]
    if should_enable_reload(cli_reload=args.reload):
        run_with_reload(child_argv)
        return
    run_server(args.host, args.port)


def _reason_phrase(status_code: int) -> str:
    return {
        200: "OK",
        201: "Created",
        400: "Bad Request",
        404: "Not Found",
        500: "Internal Server Error",
    }.get(status_code, "OK")


if __name__ == "__main__":
    main()
