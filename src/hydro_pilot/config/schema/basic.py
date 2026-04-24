from pathlib import Path
from typing import Any, Dict

from pydantic import Field

from .base import ConfigNode
from ..paths import resolve_config_path, resolve_existing_dir


class BasicSpec(ConfigNode):
    projectPath: Path = Field(alias="project_path")
    workPath: Path = Field(alias="work_path")
    configPath: Path = Field(alias="config_path")
    command: str
    timeout: int = -1
    parallel: int = 1

    @classmethod
    def from_raw(cls, raw: Dict[str, Any], base_path: Path) -> "BasicSpec":
        if not isinstance(raw, dict):
            raise ValueError("basic must be a mapping/object")
        for key in ("projectPath", "workPath", "command"):
            if not raw.get(key):
                raise ValueError(f"basic.{key} is required")
        payload = dict(raw)
        payload["projectPath"] = resolve_existing_dir(raw.get("projectPath"), base_path, "basic.projectPath")
        payload["workPath"] = resolve_config_path(raw.get("workPath"), base_path)
        payload["configPath"] = base_path.resolve()
        return cls.model_validate(payload)
