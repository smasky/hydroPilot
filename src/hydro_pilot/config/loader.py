from dataclasses import dataclass
from pathlib import Path
from typing import Any, Union

import yaml

from ..models.registry import get_template
from ..models.swat.validate import translate_swat_exception, validate_swat_config
from ..validation.diagnostics import Diagnostic
from ..validation.general import validate_general_config
from .paths import resolve_config_file
from .specs import RunConfig


@dataclass
class PreparedConfig:
    yaml_file: Path
    raw: dict[str, Any]
    expanded_raw: dict[str, Any]
    config: RunConfig
    version: str


class ConfigPreparationError(Exception):
    def __init__(self, diagnostics: list[Diagnostic]):
        self.diagnostics = diagnostics
        message = diagnostics[0].message if diagnostics else "Config preparation failed"
        super().__init__(message)


def prepare_config(path: Union[str, Path]) -> PreparedConfig:
    yaml_file = resolve_config_file(path)
    raw = _load_raw_yaml(yaml_file)
    version = raw.get("version", "general")

    if version == "general":
        expanded_raw = raw
    else:
        expanded_raw = _expand_template_config(raw, yaml_file.parent, version)

    diagnostics = validate_general_config(expanded_raw, yaml_file.parent)
    if diagnostics:
        raise ConfigPreparationError(diagnostics)

    try:
        config = RunConfig.from_raw(expanded_raw, yaml_file.parent)
    except ValueError as exc:
        raise ConfigPreparationError([_translate_run_config_exception(expanded_raw, exc)]) from exc
    return PreparedConfig(
        yaml_file=yaml_file,
        raw=raw,
        expanded_raw=expanded_raw,
        config=config,
        version=version,
    )


def load_config(path: Union[str, Path]) -> RunConfig:
    """Public entry point for loading config.

    For version='general', parses directly into RunConfig.
    For other versions (swat, vic, etc.), delegates to the
    corresponding ModelTemplate to transform simplified config
    into a standard RunConfig.

    When a template expands a simplified config, the resolved
    general config is automatically written to
    ``<workPath>/<original_name>_general.yaml`` for user inspection.
    """
    prepared = prepare_config(path)
    if prepared.version != "general":
        _dump_resolved_config(prepared.expanded_raw, prepared.yaml_file)
    return prepared.config


def _load_raw_yaml(yaml_file: Path) -> dict[str, Any]:
    with yaml_file.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError("YAML root must be a mapping/object")
    return raw


def _expand_template_config(raw: dict[str, Any], base_path: Path, version: str) -> dict[str, Any]:
    if version == "swat":
        diagnostics = validate_swat_config(raw, base_path)
        if diagnostics:
            raise ConfigPreparationError(diagnostics)

    try:
        template = get_template(version)
    except ValueError as exc:
        raise ConfigPreparationError([_translate_unknown_version(version, exc)]) from exc

    try:
        return template.build_config(raw, base_path)
    except (ValueError, FileNotFoundError, yaml.YAMLError, KeyError, IndexError) as exc:
        if version == "swat":
            translated = translate_swat_exception(raw, exc)
            raise ConfigPreparationError([translated]) from exc
        raise ConfigPreparationError([Diagnostic(level="error", path="config.version", message=str(exc), suggestion=None)]) from exc


def _translate_unknown_version(version: Any, exc: Exception) -> Diagnostic:
    message = f"unsupported config version: {version}"
    suggestion = str(exc)
    return Diagnostic(level="error", path="config.version", message=message, suggestion=suggestion)


def _translate_run_config_exception(raw: dict[str, Any], exc: ValueError) -> Diagnostic:
    message = str(exc)
    if message == "series must be a non-empty list":
        return Diagnostic(
            level="error",
            path="series",
            message=message,
            suggestion="add at least one series item",
        )
    if message.startswith("Duplicate series id: "):
        series_id = message.removeprefix("Duplicate series id: ")
        return Diagnostic(
            level="error",
            path=f"series[{series_id}]",
            message=f"duplicate series id: {series_id}",
            suggestion="make each series.id unique",
        )
    if message == "functions must be a list":
        return Diagnostic(
            level="error",
            path="functions",
            message=message,
            suggestion="set functions to a list, for example: functions: []",
        )
    if message.startswith("Duplicate function name: "):
        function_name = message.removeprefix("Duplicate function name: ")
        return Diagnostic(
            level="error",
            path=f"functions[{function_name}]",
            message=f"duplicate function name: {function_name}",
            suggestion="make each function.name unique",
        )
    if message == "derived must be a list":
        return Diagnostic(
            level="error",
            path="derived",
            message=message,
            suggestion="set derived to a list, for example: derived: []",
        )
    if message.startswith("Missing dependencies in environment: "):
        return Diagnostic(
            level="error",
            path="config.dependencies",
            message=message,
            suggestion="check derived/objectives/constraints/diagnostics refs and function args",
        )
    return Diagnostic(level="error", path="config", message=message, suggestion=None)


def _dump_resolved_config(raw: dict, source_file: Path) -> None:
    """Write the resolved general config next to the source YAML file."""
    out_dir = source_file.parent
    out_name = source_file.stem + "_general.yaml"
    out_path = out_dir / out_name

    dumper = _make_compact_dumper()
    with open(out_path, "w", encoding="utf-8") as f:
        yaml.dump(
            raw, f,
            Dumper=dumper,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
            indent=2,
        )


def _make_compact_dumper():
    """Create a YAML dumper that renders lists compactly.

    Rules:
    - Short all-scalar list (<=6 items, no filenames) → flow: [35, 98]
    - List of all-scalar lists → block outer, flow inner:
          - [42, 72312, 33]
    - Long string lists (filenames etc.) → block:
          - 000010001.mgt
          - 000010002.mgt
    - Otherwise → default block style
    """
    class CompactDumper(yaml.SafeDumper):
        # Disable YAML anchors/aliases (&id001 / *id001) for readability
        def ignore_aliases(self, data):
            return True

    # Indent block sequences inside mappings (adds 2 spaces before "- ")
    CompactDumper.best_indent = 2
    CompactDumper.best_sequence_dash_offset = 0
    CompactDumper.best_map_representor = None

    def _increase_indent(self, flow=False, indentless=False):
        return yaml.SafeDumper.increase_indent(self, flow, False)

    CompactDumper.increase_indent = _increase_indent

    def _is_short_scalar_list(data):
        """True for short lists of scalars that look good inline."""
        if not (isinstance(data, list) and data):
            return False
        if not all(isinstance(v, (int, float, str, bool)) for v in data):
            return False
        # Long lists or lists with filename-like strings → block
        if len(data) > 6:
            return False
        if any(isinstance(v, str) and '.' in v and len(v) > 4 and not v.endswith(('.sim', '.obs')) for v in data):
            return False
        return True

    def _represent_list(dumper, data):
        if not data:
            return dumper.represent_sequence(
                "tag:yaml.org,2002:seq", data, flow_style=True,
            )
        # Short scalars → flow: [35, 98]
        if _is_short_scalar_list(data):
            return dumper.represent_sequence(
                "tag:yaml.org,2002:seq", data, flow_style=True,
            )
        # List of short scalar-lists → block outer, flow inner:
        #   - [42, 72312, 33]
        if all(_is_short_scalar_list(v) for v in data):
            return dumper.represent_sequence(
                "tag:yaml.org,2002:seq", data, flow_style=False,
            )
        return dumper.represent_sequence(
            "tag:yaml.org,2002:seq", data, flow_style=False,
        )

    CompactDumper.add_representer(list, _represent_list)
    return CompactDumper
