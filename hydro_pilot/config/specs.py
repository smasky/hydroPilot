from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union, Literal

import yaml
from pydantic import BaseModel, Field, ConfigDict, model_validator

def resolve_existing_file(path: Optional[Union[str, Path]], base_path: Path, field_name: str) -> Optional[Path]:
    if path is None:
        return None
    full_path = (base_path / Path(path)).resolve()
    if not full_path.exists():
        raise FileNotFoundError(f"{field_name}: file not found: {full_path}")
    return full_path

def expand_row_ranges(row_ranges: List[List[int]]) -> List[int]:
    rows: List[int] = []
    for item in row_ranges:
        if len(item) == 2:
            start, end = item
            step = 1
        elif len(item) == 3:
            start, end, step = item
        else:
            raise ValueError(f"rowRanges item must be [start, end] or [start, end, step], got: {item}")
        rows.extend(range(int(start), int(end) + 1, int(step)))
    return sorted(rows)



class ConfigNode(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
        arbitrary_types_allowed=True,
    )

    def get_env_dep_list(self) -> Tuple[List[str], List[str]]:
        return [], []


# -------------------------
# 1. Basic
# -------------------------

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
        payload["configPath"] = base_path.resolve()
        return cls.model_validate(payload)


# -------------------------
# 2. Parameters
# -------------------------

class PhysicalParameterSpec(ConfigNode):
    name: str
    type: str = "float"
    mode: str = "v"
    bounds: List[float] = Field(default_factory=lambda: [0, 1])
    writerType: str = "fixed_width"
    file: Dict[str, Any]
    sets: List[float] = Field(default_factory=list)

    @classmethod
    def from_raw(cls, raw: Dict[str, Any], index: int) -> "PhysicalParameterSpec":
        if not isinstance(raw, dict):
            raise ValueError(f"Physical parameter at index {index} must be a mapping/object")
        if "name" not in raw:
            raise ValueError(f"Physical parameter at index {index} missing 'name'")
        if "file" not in raw or not isinstance(raw["file"], dict):
            raise ValueError(f"Physical parameter '{raw.get('name', index)}' missing 'file' block")
        payload = dict(raw)
        payload.setdefault("type", "float")
        payload.setdefault("mode", "v")
        payload.setdefault("bounds", [0, 1])
        payload.setdefault("writerType", raw.get("writer_type", "fixed_width"))
        payload.setdefault("sets", [])
        return cls.model_validate(payload)


class ParametersSpec(ConfigNode):
    design: List[Dict[str, Any]]
    physical: List[PhysicalParameterSpec]
    hardBound: bool = Field(default=True, alias="hard_bound")
    transformer: Optional[str] = None

    @classmethod
    def from_raw(cls, raw: Dict[str, Any], base_path: Path) -> "ParametersSpec":
        if not isinstance(raw, dict):
            raise ValueError("parameters must be a mapping/object")
        design = raw.get("design")
        if not design or not isinstance(design, list):
            raise ValueError("parameters.design is required and must be a list")
        physical = raw.get("physical")
        if not physical or not isinstance(physical, list):
            raise ValueError("parameters.physical is required and must be a list")
        payload = {
            "design": design,
            "physical": [PhysicalParameterSpec.from_raw(item, i) for i, item in enumerate(physical)],
            "hardBound": raw.get("hardBound", True),
            "transformer": raw.get("transformer"),
        }
        return cls.model_validate(payload)

    def get_env_dep_list(self) -> Tuple[List[str], List[str]]:
        return ["P"], []


# -------------------------
# 3. Series extraction
# -------------------------

ColumnKind = Literal["span", "col"]

class ColumnSpec(ConfigNode):
    kind: ColumnKind
    span: Optional[Tuple[int, int]] = None
    col: Optional[int] = None
    delimiter: str = "whitespace"

    @model_validator(mode="after")
    def validate_structure(self) -> "ColumnSpec":
        if self.kind == "span":
            if self.span is None or self.col is not None:
                raise ValueError("ColumnSpec(kind='span') requires span and must not have col")
        elif self.kind == "col":
            if self.col is None or self.span is not None:
                raise ValueError("ColumnSpec(kind='col') requires col and must not have span")
        return self

    @classmethod
    def from_raw(cls, raw: Dict[str, Any]) -> "ColumnSpec":
        has_span = "colSpan" in raw
        has_num = "colNum" in raw
        if has_span == has_num:
            raise ValueError("Must set exactly one of colSpan or colNum")
        if has_span:
            cs = raw["colSpan"]
            if not (isinstance(cs, list) and len(cs) == 2):
                raise ValueError(f"colSpan must be [start, end], got: {cs}")
            payload = {"kind": "span", "span": (int(cs[0]), int(cs[1]))}
            return cls.model_validate(payload)
        col_num = raw["colNum"]
        if not isinstance(col_num, int):
            raise ValueError(f"colNum must be an int, got: {col_num}")
        payload = {"kind": "col", "col": col_num, "delimiter": raw.get("delimiter", "whitespace")}
        return cls.model_validate(payload)


class CallSpec(ConfigNode):
    func: str
    args: List[str] = Field(default_factory=list)

    def get_env_dep_list(self) -> Tuple[List[str], List[str]]:
        deps = [v for v in self.args if isinstance(v, str)]
        return [], deps


class ExtractSpec(ConfigNode):
    file: Path
    rows: List[int]
    column: ColumnSpec
    size: int
    readerType: str = "text"

    @classmethod
    def from_raw(cls, raw: Dict[str, Any], base_path: Path, field_name: str, check_file: bool = True) -> "ExtractSpec":
        if not isinstance(raw, dict):
            raise ValueError(f"{field_name} must be a mapping/object, got: {type(raw)}")
        if "file" not in raw:
            raise ValueError(f"{field_name} missing 'file': {raw}")

        rr = raw.get("rowRanges", [])
        if rr and not isinstance(rr, list):
            raise ValueError(f"{field_name}.rowRanges must be a list, got: {rr}")

        row_ranges: List[List[int]] = []
        for item in rr:
            if not isinstance(item, list) or len(item) not in (2, 3):
                raise ValueError(
                    f"{field_name}.rowRanges item must be [start, end] or [start, end, step], got: {item}"
                )
            row_ranges.append([int(x) for x in item])

        expanded_rows = expand_row_ranges(row_ranges) if row_ranges else []

        row_list = raw.get("rowList", [])
        if row_list and (not isinstance(row_list, list) or not all(isinstance(x, int) for x in row_list)):
            raise ValueError(f"{field_name}.rowList must be a list of integers, got: {row_list}")

        merged_rows = sorted(set(expanded_rows + [int(x) for x in row_list]))
        if not merged_rows:
            raise ValueError(
                f"{field_name} must define at least one row via 'rowRanges' or 'rowList'"
            )

        actual_size = len(merged_rows)
        declared_size = int(raw.get("size", actual_size))
        if declared_size != actual_size:
            raise ValueError(
                f"{field_name} size mismatch: you set size={declared_size} but actual size is {actual_size}"
            )

        file_path = raw.get("file")
        if file_path is None:
            raise ValueError(f"{field_name} missing 'file'")

        if check_file:
            file_path_resolved = resolve_existing_file(file_path, base_path, f"{field_name}.file")
        else:
            file_path_resolved = Path(file_path)

        payload = {
            "file": file_path_resolved,
            "rows": merged_rows,
            "size": actual_size,
            "column": ColumnSpec.from_raw(raw),
            "readerType": raw.get("readerType", raw.get("reader_type", "text")),
        }
        return cls.model_validate(payload)


class SeriesSpec(ConfigNode):
    id: str
    name: str
    sim: Union[ExtractSpec, CallSpec]
    obs: Optional[ExtractSpec] = None
    size: int = -1

    @classmethod
    def from_raw(cls, raw: Dict[str, Any], base_path: Path) -> "SeriesSpec":
        if not isinstance(raw, dict):
            raise ValueError("SeriesSpec must be a mapping/object")
        sid = raw.get("id")
        if not sid:
            raise ValueError(f"SeriesSpec missing id: {raw}")

        sim_raw = raw.get("sim")
        if not isinstance(sim_raw, dict):
            raise ValueError(f"Series {sid}: 'sim' block must be a dictionary")

        if "call" in sim_raw:
            call_raw = sim_raw["call"]
            if not isinstance(call_raw, dict):
                raise ValueError(f"Series {sid}: sim.call must be a dictionary")
            sim = CallSpec.model_validate(call_raw)
        else:
            sim = ExtractSpec.from_raw(sim_raw, base_path, f"series[{sid}].sim", check_file=False)

        obs_raw = raw.get("obs")
        obs = None if obs_raw is None else ExtractSpec.from_raw(obs_raw, base_path, f"series[{sid}].obs", check_file=True)

        payload = {
            "id": str(sid),
            "name": str(raw.get("desc", sid)),
            "sim": sim,
            "obs": obs,
            "size": int(raw.get("size", -1)),
        }
        return cls.model_validate(payload)

    def get_env_dep_list(self) -> Tuple[List[str], List[str]]:
        env: List[str] = [f"{self.id}.sim"]
        dep: List[str] = []
        if self.obs:
            env.append(f"{self.id}.obs")
        sim_env, sim_dep = self.sim.get_env_dep_list()
        env.extend(sim_env)
        dep.extend(sim_dep)
        return env, dep


# -------------------------
# 4. Functions & Derived
# -------------------------

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

    def get_env_dep_list(self) -> Tuple[List[str], List[str]]:
        env = [self.id]
        _, call_dep = self.call.get_env_dep_list()
        return env, call_dep


# -------------------------
# 5. Objectives & Diagnostics
# -------------------------

class RefItemSpec(ConfigNode):
    id: str
    ref: str

    def get_env_dep_list(self) -> Tuple[List[str], List[str]]:
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
        # Default on_error: worst possible value based on sense
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
        # Default on_error: +inf (constraint violated)
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
        # Default on_error: NaN (does not affect optimization)
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


# -------------------------
# 6. Reporter
# -------------------------

class ReporterSpec(ConfigNode):
    flushInterval: int = 50
    holdingPenLimit: int = 20
    series: List[str] = Field(default_factory=list)

    @classmethod
    def from_raw(cls, raw: Any) -> "ReporterSpec":
        if not isinstance(raw, dict):
            raw = {}
        # Support legacy key name
        if "flush_interval" in raw and "flushInterval" not in raw:
            raw["flushInterval"] = raw.pop("flush_interval")
        return cls.model_validate(raw)


# -------------------------
# 7. RunConfig
# -------------------------

class RunConfig(ConfigNode):
    version: str
    basic: BasicSpec
    parameters: ParametersSpec
    series: List[SeriesSpec]
    functions: Dict[str, FunctionSpec]
    derived: List[DerivedSpec]
    objectives: ObjectiveBlock
    constraints: ConstraintBlock
    diagnostics: DiagnosticBlock
    reporter: ReporterSpec
    series_index: Dict[str, SeriesSpec]

    @classmethod
    def from_yaml(cls, path: Union[str, Path]) -> "RunConfig":
        yaml_file = Path(path).resolve()
        if not yaml_file.exists():
            raise FileNotFoundError(f"Config file not found: {yaml_file}")
        with yaml_file.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        return cls.from_raw(raw, yaml_file.parent)

    @classmethod
    def from_raw(cls, raw: Dict[str, Any], base_path: Path) -> "RunConfig":
        if not isinstance(raw, dict):
            raise ValueError("YAML root must be a mapping/object")
        version = raw.get("version")
        if version != "general":
            raise ValueError(f"Unsupported version: {version}")

        basic = BasicSpec.from_raw(raw.get("basic", {}), base_path)
        parameters = ParametersSpec.from_raw(raw.get("parameters", {}), base_path)
        reporter = ReporterSpec.from_raw(raw.get("reporter", {}))

        series_raw = raw.get("series", [])
        if not isinstance(series_raw, list) or not series_raw:
            raise ValueError("series must be a non-empty list")
        series_list = [SeriesSpec.from_raw(item, base_path) for item in series_raw]

        series_index: Dict[str, SeriesSpec] = {}
        for item in series_list:
            if item.id in series_index:
                raise ValueError(f"Duplicate series id: {item.id}")
            series_index[item.id] = item

        functions_raw = raw.get("functions", [])
        if not isinstance(functions_raw, list):
            raise ValueError("functions must be a list")
        functions: Dict[str, FunctionSpec] = {}
        for item_raw in functions_raw:
            func = FunctionSpec.from_raw(item_raw, base_path)
            if func.name in functions:
                raise ValueError(f"Duplicate function name: {func.name}")
            functions[func.name] = func

        derived_raw = raw.get("derived", [])
        if not isinstance(derived_raw, list):
            raise ValueError("derived must be a list")
        derived = [DerivedSpec.from_raw(item) for item in derived_raw]

        objectives = ObjectiveBlock.from_raw(raw.get("objectives", {}))
        constraints = ConstraintBlock.from_raw(raw.get("constraints", {}))
        diagnostics = DiagnosticBlock.from_raw(raw.get("diagnostics", {}))

        cfg = cls.model_validate({
            "version": version,
            "basic": basic,
            "parameters": parameters,
            "series": series_list,
            "functions": functions,
            "derived": derived,
            "objectives": objectives,
            "constraints": constraints,
            "diagnostics": diagnostics,
            "reporter": reporter,
            "series_index": series_index,
        })
        cfg.validate_dependencies()
        return cfg

    def validate_dependencies(self) -> None:
        env = {"X", "i"}
        dep = set()

        env_list, dep_list = self.parameters.get_env_dep_list()
        env.update(env_list)
        dep.update(dep_list)

        for item in self.series:
            env_list, dep_list = item.get_env_dep_list()
            env.update(env_list)
            dep.update(dep_list)

        for item in self.derived:
            env_list, dep_list = item.get_env_dep_list()
            env.update(env_list)
            dep.update(dep_list)

        for item in self.objectives.items.values():
            env_list, dep_list = item.get_env_dep_list()
            env.update(env_list)
            dep.update(dep_list)

        for item in self.constraints.items.values():
            env_list, dep_list = item.get_env_dep_list()
            env.update(env_list)
            dep.update(dep_list)

        for item in self.diagnostics.items.values():
            env_list, dep_list = item.get_env_dep_list()
            env.update(env_list)
            dep.update(dep_list)

        missing = sorted(dep - env)
        if missing:
            raise ValueError(f"Missing dependencies in environment: {missing}")
