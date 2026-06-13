#!/usr/bin/env bash
#
# 一步启动 LNAgent Web（最小前端页面 + 后端 API）
#
# 用法:
#   bash scripts/start-web.sh
#   bash scripts/start-web.sh --host 0.0.0.0 --port 9000
#   API_KEY=xxx bash scripts/start-web.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

HOST="${LNAGENT_WEB_HOST:-127.0.0.1}"
PORT="${LNAGENT_WEB_PORT:-8000}"
PROJECTS_DIR="${LNAGENT_PROJECTS_DIR:-$PROJECT_ROOT/projects}"
MODEL_NAME="${MODEL:-gpt-4o-mini}"
PYTHON_BIN="${PYTHON_BIN:-python}"
RELOAD=0

print_help() {
    cat <<EOF
LNAgent Web 一键启动脚本（Bash）

用法:
  bash scripts/start-web.sh [--host HOST] [--port PORT] [--projects-dir PATH]

参数:
  --host HOST           监听地址，默认读取 LNAGENT_WEB_HOST 或 127.0.0.1
  --port PORT           监听端口，默认读取 LNAGENT_WEB_PORT 或 8000
  --projects-dir PATH   项目目录，默认读取 LNAGENT_PROJECTS_DIR 或 <repo>/projects
  --reload              开发模式：文件变更时自动重启 Web 进程
  --help                显示帮助

环境变量:
  API_KEY               必填，大模型 API Key
  MODEL                 可选，默认 gpt-4o-mini
  API_BASE_URL          可选，OpenAI 兼容接口基址
  LNAGENT_WEB_HOST      可选，Web host 默认值
  LNAGENT_WEB_PORT      可选，Web port 默认值
  LNAGENT_PROJECTS_DIR  可选，项目目录默认值
  PYTHON_BIN            可选，Python 可执行文件，默认 python

说明:
  当前 LNAgent Web 为单进程启动：同一个 Python 进程同时提供前端页面和后端 API。
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --host)
            HOST="$2"
            shift 2
            ;;
        --port)
            PORT="$2"
            shift 2
            ;;
        --projects-dir)
            PROJECTS_DIR="$2"
            shift 2
            ;;
        --reload)
            RELOAD=1
            shift
            ;;
        --help|-h)
            print_help
            exit 0
            ;;
        *)
            echo "未知参数: $1" >&2
            echo "使用 --help 查看帮助。" >&2
            exit 1
            ;;
    esac
done

if [[ -z "${API_KEY:-}" ]]; then
    cat >&2 <<EOF
错误: 未设置 API_KEY。
请先导出环境变量，例如：
  export API_KEY="your-api-key"
EOF
    exit 1
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "错误: 未找到 Python 可执行文件: $PYTHON_BIN" >&2
    exit 1
fi

mkdir -p "$PROJECTS_DIR"

export MODEL="$MODEL_NAME"
export LNAGENT_PROJECTS_DIR="$PROJECTS_DIR"
export LNAGENT_WEB_HOST="$HOST"
export LNAGENT_WEB_PORT="$PORT"

cd "$PROJECT_ROOT"

echo "==> 启动 LNAgent Web"
echo "项目目录: $PROJECT_ROOT"
echo "Python: $($PYTHON_BIN --version 2>&1)"
echo "监听地址: http://$HOST:$PORT"
echo "小说项目目录: $PROJECTS_DIR"
echo "前端页面: http://$HOST:$PORT/"
echo "后端 API: http://$HOST:$PORT/api/projects"
if [[ "$RELOAD" == "1" ]]; then
    echo "开发模式: 已启用 --reload（文件变更自动重启）"
fi
echo ""

WEB_ARGS=(--host "$HOST" --port "$PORT")
if [[ "$RELOAD" == "1" ]]; then
    WEB_ARGS+=(--reload)
fi

exec "$PYTHON_BIN" web_main.py "${WEB_ARGS[@]}"
