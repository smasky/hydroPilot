from pathlib import Path
from typing import Any, Dict

from pydantic import Field, field_validator

from .base import ConfigNode
from ..paths import resolve_config_path, resolve_existing_dir


class BasicSpec(ConfigNode):
    projectPath: Path = Field(alias="project_path")
    workPath: Path = Field(alias="work_path")
    configPath: Path = Field(alias="config_path")
    command: str | list[str]
    timeout: int = -1
    parallel: int = 1
    keepCopies: bool = Field(default=False, alias="keep_copies")
    workDirName: str | None = Field(default=None, alias="work_dir_name")
    reset: bool = False

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

    @field_validator("workDirName")
    @classmethod
    def _validate_work_dir_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("basic.workDirName must not be empty")
        path = Path(value)
        if path.is_absolute() or len(path.parts) != 1 or value in {".", ".."}:
            raise ValueError("basic.workDirName must be a single directory name under basic.workPath")
        return value
