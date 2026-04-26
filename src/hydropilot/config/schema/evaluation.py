from typing import Any, Dict, List, Optional, Literal

from .base import ConfigNode


class RefItemSpec(ConfigNode):
    id: str
    ref: str

    def get_env_dep_list(self):
        env = [self.id]
        dep = [self.ref] if self.ref != self.id else []
        return env, dep


class ObjectiveSpec(RefItemSpec):
    desc: str
    sense: Literal["max", "min"] = "min"
    on_error: Optional[float] = None

    @classmethod
    def from_raw(cls, raw: Dict[str, Any]) -> "ObjectiveSpec":
        if not isinstance(raw, dict):
            raise ValueError(f"Objective must be a mapping/object, got: {type(raw)}")
        oid = raw.get("id")
        if not oid:
            raise ValueError("Objective missing id")
        ref = raw.get("ref")
        if not ref:
            raise ValueError(f"Objective {oid} missing 'ref'")
        sense = raw.get("sense", "min")
        on_error = raw.get("on_error", None)
        if on_error is None:
            on_error = float("-inf") if sense == "max" else float("inf")
        payload = {
            "id": str(oid),
            "desc": str(raw.get("desc", oid)),
            "sense": sense,
            "ref": str(ref),
            "on_error": on_error,
        }
        return cls.model_validate(payload)


class ConstraintSpec(RefItemSpec):
    desc: str
    on_error: Optional[float] = None

    @classmethod
    def from_raw(cls, raw: Dict[str, Any]) -> "ConstraintSpec":
        if not isinstance(raw, dict):
            raise ValueError(f"Constraint must be a mapping/object, got: {type(raw)}")
        cid = raw.get("id")
        if not cid:
            raise ValueError("Constraint missing id")
        ref = raw.get("ref")
        if not ref:
            raise ValueError(f"Constraint {cid} missing 'ref'")
        on_error = raw.get("on_error", None)
        if on_error is None:
            on_error = float("inf")
        payload = {
            "id": str(cid),
            "desc": str(raw.get("desc", cid)),
            "ref": str(ref),
            "on_error": on_error,
        }
        return cls.model_validate(payload)


class DiagnosticSpec(RefItemSpec):
    name: str
    on_error: Optional[float] = None

    @classmethod
    def from_raw(cls, raw: Dict[str, Any]) -> "DiagnosticSpec":
        if not isinstance(raw, dict):
            raise ValueError(f"Diagnostic must be a mapping/object, got: {type(raw)}")
        did = raw.get("id")
        ref = raw.get("ref")
        if not did or not ref:
            raise ValueError("Diagnostic must have 'id' and 'ref'")
        on_error = raw.get("on_error", None)
        if on_error is None:
            on_error = float("nan")
        payload = {
            "id": str(did),
            "name": str(raw.get("name", did)),
            "ref": str(ref),
            "on_error": on_error,
        }
        return cls.model_validate(payload)


class ObjectiveBlock(ConfigNode):
    items: List[ObjectiveSpec]

    @classmethod
    def from_raw(cls, raw: Any) -> "ObjectiveBlock":
        if raw is None:
            raw = []
        if not isinstance(raw, list):
            raise ValueError("objectives must be a list")
        items: List[ObjectiveSpec] = []
        seen: set[str] = set()
        for item_raw in raw:
            item = ObjectiveSpec.from_raw(item_raw)
            if item.id in seen:
                raise ValueError(f"Duplicate objective id: {item.id}")
            seen.add(item.id)
            items.append(item)
        return cls.model_validate({"items": items})


class ConstraintBlock(ConfigNode):
    items: List[ConstraintSpec]

    @classmethod
    def from_raw(cls, raw: Any) -> "ConstraintBlock":
        if raw is None:
            raw = []
        if not isinstance(raw, list):
            raise ValueError("constraints must be a list")
        items: List[ConstraintSpec] = []
        seen: set[str] = set()
        for item_raw in raw:
            item = ConstraintSpec.from_raw(item_raw)
            if item.id in seen:
                raise ValueError(f"Duplicate constraint id: {item.id}")
            seen.add(item.id)
            items.append(item)
        return cls.model_validate({"items": items})


class DiagnosticBlock(ConfigNode):
    items: List[DiagnosticSpec]

    @classmethod
    def from_raw(cls, raw: Any) -> "DiagnosticBlock":
        if raw is None:
            raw = []
        if not isinstance(raw, list):
            raise ValueError("diagnostics must be a list")
        items: List[DiagnosticSpec] = []
        seen: set[str] = set()
        for item_raw in raw:
            item = DiagnosticSpec.from_raw(item_raw)
            if item.id in seen:
                raise ValueError(f"Duplicate diagnostic id: {item.id}")
            seen.add(item.id)
            items.append(item)
        return cls.model_validate({"items": items})
