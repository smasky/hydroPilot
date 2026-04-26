from pathlib import Path
from typing import Any, Dict, List, Optional, Literal

from pydantic import Field

from .base import ConfigNode
from ..paths import resolve_existing_file
from .series import CallSpec


class FunctionSpec(ConfigNode):
    name: str
    kind: Literal["builtin", "external"]
    args: List[str] = Field(default_factory=list)
    file: Optional[Path] = None

    @classmethod
    def from_raw(cls, raw: Dict[str, Any], base_path: Path) -> "FunctionSpec":
        if not isinstance(raw, dict):
            raise ValueError(f"Function must be a mapping/object, got: {type(raw)}")
        name = raw.get("name")
        if not name:
            raise ValueError(f"Function missing name: {raw}")
        kind = raw.get("kind")
        if kind not in ("builtin", "external"):
            raise ValueError(f"Function kind must be builtin or external, got: {kind}")
        args = raw.get("args", [])
        if not isinstance(args, list):
            raise ValueError(f"Function args must be a list, got: {args}")
        payload = {"name": name, "kind": kind, "args": args, "file": None}
        if raw.get("file"):
            payload["file"] = resolve_existing_file(raw["file"], base_path, f"functions[{name}].file")
        return cls.model_validate(payload)


class DerivedSpec(ConfigNode):
    id: str
    desc: str
    call: CallSpec

    @classmethod
    def from_raw(cls, raw: Dict[str, Any]) -> "DerivedSpec":
        if not isinstance(raw, dict):
            raise ValueError(f"Derived must be a mapping/object, got: {type(raw)}")
        did = raw.get("id")
        if not did:
            raise ValueError("Derived item missing id")
        call_raw = raw.get("call")
        if call_raw is None or not isinstance(call_raw, dict):
            raise ValueError(f"Derived {did} must have a 'call' block")
        payload = {
            "id": str(did),
            "desc": str(raw.get("desc", did)),
            "call": CallSpec.model_validate(call_raw),
        }
        return cls.model_validate(payload)

    def get_env_dep_list(self):
        env = [self.id]
        _, call_dep = self.call.get_env_dep_list()
        return env, call_dep
