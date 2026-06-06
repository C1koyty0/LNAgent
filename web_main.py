"""Web 启动入口。"""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from wsgiref.simple_server import make_server

from lnagent.app_service import AppService
from lnagent.config import Settings
from lnagent.web.app import StreamResponse, create_web_app


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
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
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
        start_response(status_line, headers)
        return [response.body]

    server = make_server(args.host, args.port, wsgi_app)
    print(f"LNAgent Web 已启动: http://{args.host}:{args.port}")
    server.serve_forever()


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
