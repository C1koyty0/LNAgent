"""项目级配置命令处理。"""

from __future__ import annotations

import shlex
from dataclasses import replace
from typing import Any, Protocol

from lnagent.memory.models import ProjectConfig


class ConfigCommandError(ValueError):
    """用户输入的 /config 子命令无效。"""


class ConfigurableSession(Protocol):
    @property
    def config(self) -> ProjectConfig: ...

    def update_config(self, config: ProjectConfig) -> None: ...


_CONFIG_KEYS: dict[str, tuple[str, str]] = {
    "context.char_budget": ("context", "char_budget"),
    "context.messages_limit": ("context", "messages_limit"),
    "context.adopted_prose_limit": ("context", "adopted_prose_limit"),
    "context.hot_canon_limit": ("context", "hot_canon_limit"),
    "context.global_limit": ("context", "global_limit"),
    "context.prior_scene_cold_limit": ("context", "prior_scene_cold_limit"),
    "context.scene_tail_limit": ("context", "scene_tail_limit"),
    "context.meta_limit": ("context", "meta_limit"),
    "scene_switch.min_adopts": ("scene_switch", "min_adopts"),
    "scene_switch.no_adopt_turns": ("scene_switch", "no_adopt_turns"),
}


def run_config(session: ConfigurableSession, args: str) -> str:
    updated, message = handle_config_args(session.config, args)
    if updated != session.config:
        session.update_config(updated)
    return message


def handle_config_args(config: ProjectConfig, args: str) -> tuple[ProjectConfig, str]:
    """解析 /config 参数，返回更新后的配置和展示文本。"""

    tokens = shlex.split(args)
    if not tokens:
        return config, format_project_config(config)

    action = tokens[0].lower()
    if action == "get":
        _require_arg_count(tokens, 2, "用法: /config get <key>")
        key = tokens[1]
        return config, _format_value(key, _get_config_value(config, key))

    if action == "set":
        _require_arg_count(tokens, 3, "用法: /config set <key> <value>")
        key = tokens[1]
        value = _parse_int(tokens[2])
        updated = _set_config_value(config, key, value)
        return updated, "已更新 " + _format_value(key, value)

    if action == "reset":
        _require_arg_count(tokens, 2, "用法: /config reset <key|all>")
        target = tokens[1]
        updated = ProjectConfig.default() if target == "all" else _reset_config_value(config, target)
        if target == "all":
            return updated, "已重置全部项目配置。"
        return updated, "已重置 " + _format_value(target, _get_config_value(updated, target))

    raise ConfigCommandError(
        "未知 /config 子命令。用法: /config [get|set|reset] ..."
    )


def format_project_config(config: ProjectConfig) -> str:
    lines = ["当前项目配置:"]
    for key in _CONFIG_KEYS:
        lines.append(f"  {key} = {_get_config_value(config, key)}")
    return "\n".join(lines)


def _require_arg_count(tokens: list[str], count: int, usage: str) -> None:
    if len(tokens) != count:
        raise ConfigCommandError(usage)


def _parse_int(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigCommandError("配置值必须是整数。") from exc
    if value < 0:
        raise ConfigCommandError("配置值必须是非负整数。")
    return value


def _get_config_value(config: ProjectConfig, key: str) -> int:
    section_name, attr_name = _resolve_key(key)
    section = getattr(config, section_name)
    value = getattr(section, attr_name)
    return int(value)


def _set_config_value(config: ProjectConfig, key: str, value: int) -> ProjectConfig:
    section_name, attr_name = _resolve_key(key)
    section = getattr(config, section_name)
    updated_section = replace(section, **{attr_name: value})
    return replace(config, **{section_name: updated_section})


def _reset_config_value(config: ProjectConfig, key: str) -> ProjectConfig:
    default_value = _get_config_value(ProjectConfig.default(), key)
    return _set_config_value(config, key, default_value)


def _resolve_key(key: str) -> tuple[str, str]:
    path = _CONFIG_KEYS.get(key)
    if path is None:
        raise ConfigCommandError(f"未知配置项: {key}")
    return path


def _format_value(key: str, value: Any) -> str:
    return f"{key} = {value}"
