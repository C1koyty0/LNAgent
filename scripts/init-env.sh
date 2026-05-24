#!/usr/bin/env bash
#
# 初始化 LNAgent 项目的 mamba 虚拟环境并安装依赖（Linux / macOS）
#
# 用法:
#   bash scripts/init-env.sh
#   ./scripts/init-env.sh        # 需先 chmod +x scripts/init-env.sh
#
# 环境变量:
#   LNAGENT_ENV_PREFIX  覆盖虚拟环境路径；设为空字符串则使用 mamba 默认 envs 目录

set -euo pipefail

ENV_NAME="LNAgent"
PYTHON_VERSION="3.12.13"

if [[ -v LNAGENT_ENV_PREFIX ]]; then
    ENV_PREFIX="$LNAGENT_ENV_PREFIX"
else
    ENV_PREFIX="${HOME}/Projects/Python/env/LNAgent"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REQUIREMENTS_FILE="$PROJECT_ROOT/requirements.txt"

find_mamba() {
    if command -v mamba >/dev/null 2>&1; then
        command -v mamba
        return 0
    fi

    local candidates=(
        "${HOME}/.local/share/mamba/condabin/mamba"
        "${HOME}/miniforge3/condabin/mamba"
        "${HOME}/mambaforge/condabin/mamba"
        "${HOME}/miniconda3/condabin/mamba"
        "/opt/homebrew/Caskroom/miniforge/base/condabin/mamba"
        "/usr/local/Caskroom/miniforge/base/condabin/mamba"
        "/opt/homebrew/bin/mamba"
        "/usr/local/bin/mamba"
    )

    for path in "${candidates[@]}"; do
        if [[ -x "$path" ]]; then
            echo "$path"
            return 0
        fi
    done

    return 1
}

env_exists() {
    local mamba_exe="$1"
    local output
    output="$("$mamba_exe" env list 2>&1)"

    while IFS= read -r line; do
        if [[ "$line" =~ ^[[:space:]]*${ENV_NAME}[[:space:]] ]] || [[ "$line" =~ [[:space:]]${ENV_NAME}[[:space:]] ]]; then
            return 0
        fi
        if [[ -n "$ENV_PREFIX" && "$line" == *"$ENV_PREFIX"* ]]; then
            return 0
        fi
    done <<< "$output"

    return 1
}

init_mamba_shell() {
    local mamba_exe="$1"
    local hook

    hook="$("$mamba_exe" shell hook --shell bash 2>&1)" || {
        echo "错误: 无法初始化 mamba shell hook" >&2
        exit 1
    }

    # shellcheck disable=SC1090
    eval "$hook"
}

echo "==> LNAgent 环境初始化"
echo "项目目录: $PROJECT_ROOT"

MAMBA_EXE="$(find_mamba)" || {
    cat >&2 <<'EOF'
错误: 未找到 mamba。请先安装 Miniforge / Mambaforge，并确保 mamba 在 PATH 中。
参考: https://github.com/conda-forge/miniforge
EOF
    exit 1
}

echo "==> 找到 mamba: $MAMBA_EXE"
echo "    版本: $("$MAMBA_EXE" --version)"

[[ -f "$REQUIREMENTS_FILE" ]] || {
    echo "错误: 未找到依赖文件: $REQUIREMENTS_FILE" >&2
    exit 1
}

if env_exists "$MAMBA_EXE"; then
    echo "==> 环境 '$ENV_NAME' 已存在，跳过创建"
else
    echo "==> 环境 '$ENV_NAME' 不存在，正在创建 (Python $PYTHON_VERSION)..."
    if [[ -n "$ENV_PREFIX" ]]; then
        mkdir -p "$(dirname "$ENV_PREFIX")"
        "$MAMBA_EXE" create -p "$ENV_PREFIX" "python=${PYTHON_VERSION}" -y
    else
        "$MAMBA_EXE" create -n "$ENV_NAME" "python=${PYTHON_VERSION}" -y
    fi
    echo "==> 环境创建完成"
fi

echo "==> 激活环境并安装依赖..."
init_mamba_shell "$MAMBA_EXE"

if [[ -n "$ENV_PREFIX" ]]; then
    mamba activate "$ENV_PREFIX"
else
    mamba activate "$ENV_NAME"
fi

python --version
pip install -r "$REQUIREMENTS_FILE"

echo ""
echo "==> 初始化完成！"
echo "后续使用时请先激活环境:"
if [[ -n "$ENV_PREFIX" ]]; then
    echo "  mamba activate $ENV_PREFIX"
else
    echo "  mamba activate $ENV_NAME"
fi
echo "然后运行: python main.py"
