from pathlib import Path
from typing import Union

import yaml

from .specs import RunConfig


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
    yaml_file = Path(path).resolve()
    if not yaml_file.exists():
        raise FileNotFoundError(f"Config file not found: {yaml_file}")

    with yaml_file.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError("YAML root must be a mapping/object")

    version = raw.get("version", "general")

    if version == "general":
        return RunConfig.from_raw(raw, yaml_file.parent)

    # Template mode: delegate to registered model template
    from ..templates import get_template
    template = get_template(version)
    transformed_raw = template.build_config(raw, yaml_file.parent)

    # Template mode: always dump resolved config for inspection
    _dump_resolved_config(transformed_raw, yaml_file)

    return RunConfig.from_raw(transformed_raw, yaml_file.parent)


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
