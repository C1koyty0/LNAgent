"""场景切换建议规则。"""

from __future__ import annotations

from dataclasses import dataclass

from lnagent.memory.models import SceneSwitchConfig


@dataclass(frozen=True)
class SceneSwitchSuggestion:
    should_suggest: bool
    reason: str = ""


class SceneSwitchAdvisor:
    def __init__(self, config: SceneSwitchConfig) -> None:
        self._config = config

    def suggest(
        self,
        *,
        adopt_count: int,
        turns_since_last_adopt: int,
    ) -> SceneSwitchSuggestion:
        if self._config.min_adopts > 0 and adopt_count >= self._config.min_adopts:
            return SceneSwitchSuggestion(
                should_suggest=True,
                reason=f"本场景已有 {adopt_count} 次采纳",
            )
        if (
            self._config.no_adopt_turns > 0
            and turns_since_last_adopt >= self._config.no_adopt_turns
        ):
            return SceneSwitchSuggestion(
                should_suggest=True,
                reason=f"已连续 {turns_since_last_adopt} 轮未采纳",
            )
        return SceneSwitchSuggestion(should_suggest=False)
