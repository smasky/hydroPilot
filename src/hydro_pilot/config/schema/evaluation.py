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
    use: List[str]
    items: Dict[str, ObjectiveSpec]

    @classmethod
    def from_raw(cls, raw: Dict[str, Any]) -> "ObjectiveBlock":
        if not isinstance(raw, dict):
            raw = {}
        items_raw = raw.get("items", [])
        if not isinstance(items_raw, list):
            raise ValueError("objectives.items must be a list")
        items: Dict[str, ObjectiveSpec] = {}
        for item_raw in items_raw:
            item = ObjectiveSpec.from_raw(item_raw)
            if item.id in items:
                raise ValueError(f"Duplicate objective id: {item.id}")
            items[item.id] = item
        use = raw.get("use", list(items.keys()))
        if not isinstance(use, list):
            raise ValueError("objectives.use must be a list")
        for oid in use:
            if oid not in items:
                raise ValueError(f"objectives.use references unknown objective id: {oid}")
        return cls.model_validate({"use": use, "items": items})


class ConstraintBlock(ConfigNode):
    use: List[str]
    items: Dict[str, ConstraintSpec]

    @classmethod
    def from_raw(cls, raw: Dict[str, Any]) -> "ConstraintBlock":
        if not isinstance(raw, dict):
            raw = {}
        items_raw = raw.get("items", [])
        if not isinstance(items_raw, list):
            raise ValueError("constraints.items must be a list")
        items: Dict[str, ConstraintSpec] = {}
        for item_raw in items_raw:
            item = ConstraintSpec.from_raw(item_raw)
            if item.id in items:
                raise ValueError(f"Duplicate constraint id: {item.id}")
            items[item.id] = item
        use = raw.get("use", list(items.keys()))
        if not isinstance(use, list):
            raise ValueError("constraints.use must be a list")
        for cid in use:
            if cid not in items:
                raise ValueError(f"constraints.use references unknown constraint id: {cid}")
        return cls.model_validate({"use": use, "items": items})


class DiagnosticBlock(ConfigNode):
    use: List[str]
    items: Dict[str, DiagnosticSpec]

    @classmethod
    def from_raw(cls, raw: Dict[str, Any]) -> "DiagnosticBlock":
        if not isinstance(raw, dict):
            raw = {}
        items_raw = raw.get("items", [])
        if not isinstance(items_raw, list):
            raise ValueError("diagnostics.items must be a list")
        items: Dict[str, DiagnosticSpec] = {}
        for item_raw in items_raw:
            item = DiagnosticSpec.from_raw(item_raw)
            if item.id in items:
                raise ValueError(f"Duplicate diagnostic id: {item.id}")
            items[item.id] = item
        use = raw.get("use", list(items.keys()))
        if not isinstance(use, list):
            raise ValueError("diagnostics.use must be a list")
        for did in use:
            if did not in items:
                raise ValueError(f"diagnostics.use references unknown diagnostic id: {did}")
        return cls.model_validate({"use": use, "items": items})
