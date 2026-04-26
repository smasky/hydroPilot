from pathlib import Path
from typing import Any, Dict, List, Union

import yaml

from .base import ConfigNode
from .basic import BasicSpec
from .parameters import ParametersSpec
from .series import SeriesSpec
from .functions import FunctionSpec, DerivedSpec
from .evaluation import ObjectiveBlock, ConstraintBlock, DiagnosticBlock
from .reporter import ReporterSpec
from ..paths import resolve_config_file


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
        yaml_file = resolve_config_file(path)
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

        objectives = ObjectiveBlock.from_raw(raw.get("objectives", []))
        constraints = ConstraintBlock.from_raw(raw.get("constraints", []))
        diagnostics = DiagnosticBlock.from_raw(raw.get("diagnostics", []))

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

        for item in self.objectives.items:
            env_list, dep_list = item.get_env_dep_list()
            env.update(env_list)
            dep.update(dep_list)

        for item in self.constraints.items:
            env_list, dep_list = item.get_env_dep_list()
            env.update(env_list)
            dep.update(dep_list)

        for item in self.diagnostics.items:
            env_list, dep_list = item.get_env_dep_list()
            env.update(env_list)
            dep.update(dep_list)

        missing = sorted(dep - env)
        if missing:
            raise ValueError(f"Missing dependencies in environment: {missing}")
