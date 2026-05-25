import os
from dataclasses import dataclass, replace
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """从环境变量加载的运行配置。"""

    api_key: str
    model: str
    base_url: str | None = None
    project_id: str | None = None
    projects_dir: Path = Path("projects")

    @classmethod
    def from_env(cls) -> "Settings":
        api_key = os.environ.get("API_KEY")
        if not api_key:
            raise ValueError("环境变量 API_KEY 未设置")

        projects_dir = Path(os.environ.get("LNAGENT_PROJECTS_DIR", "projects"))

        return cls(
            api_key=api_key,
            model=os.environ.get("MODEL", "gpt-4o-mini"),
            base_url=os.environ.get("API_BASE_URL"),
            projects_dir=projects_dir,
        )

    def with_project(self, project_id: str) -> "Settings":
        return replace(self, project_id=project_id)

    @property
    def project_dir(self) -> Path:
        if not self.project_id:
            raise ValueError("project_id 未设置")
        return self.projects_dir / self.project_id
