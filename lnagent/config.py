import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """从环境变量加载的运行配置。"""

    api_key: str
    model: str
    base_url: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        api_key = os.environ.get("API_KEY")
        if not api_key:
            raise ValueError("环境变量 API_KEY 未设置")

        return cls(
            api_key=api_key,
            model=os.environ.get("MODEL", "gpt-4o-mini"),
            base_url=os.environ.get("API_BASE_URL"),
        )
