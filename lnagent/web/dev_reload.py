"""开发态 Web 进程热重启（stdlib only）。"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

_RELOAD_CHILD_ENV = "LNAGENT_WEB_RELOAD_CHILD"
_WATCH_SUFFIXES = {".py", ".js", ".css"}
_REPO_ROOT = Path(__file__).resolve().parents[2]


def is_reload_child() -> bool:
    return os.environ.get(_RELOAD_CHILD_ENV) == "1"


def should_enable_reload(*, cli_reload: bool) -> bool:
    if is_reload_child():
        return False
    if cli_reload:
        return True
    return os.environ.get("LNAGENT_WEB_RELOAD", "").strip().lower() in {"1", "true", "yes"}


def _watch_snapshot() -> dict[str, float]:
    mtimes: dict[str, float] = {}
    candidates = [_REPO_ROOT / "web_main.py", _REPO_ROOT / "lnagent"]
    for candidate in candidates:
        if candidate.is_file():
            mtimes[str(candidate)] = candidate.stat().st_mtime
            continue
        if not candidate.is_dir():
            continue
        for path in candidate.rglob("*"):
            if not path.is_file() or path.suffix not in _WATCH_SUFFIXES:
                continue
            mtimes[str(path)] = path.stat().st_mtime
    return mtimes


def run_with_reload(argv: list[str]) -> None:
    env = os.environ.copy()
    env[_RELOAD_CHILD_ENV] = "1"
    command = [sys.executable, str(_REPO_ROOT / "web_main.py"), *argv]
    snapshot = _watch_snapshot()
    process = subprocess.Popen(command, env=env)
    print("LNAgent Web 开发模式：已启用文件变更自动重启（Ctrl+C 退出）")
    try:
        while True:
            return_code = process.poll()
            if return_code is not None:
                if return_code != 0:
                    raise SystemExit(return_code)
                snapshot = _watch_snapshot()
                process = subprocess.Popen(command, env=env)
                continue

            time.sleep(0.5)
            current = _watch_snapshot()
            if current == snapshot:
                continue

            print("检测到代码或静态资源变更，正在重启 Web 进程…")
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            snapshot = _watch_snapshot()
            process = subprocess.Popen(command, env=env)
    except KeyboardInterrupt:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
