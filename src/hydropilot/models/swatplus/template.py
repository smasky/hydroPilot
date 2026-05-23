import copy
from pathlib import Path
from typing import Any, Dict, List

from typing import Any, Dict, List

from ...config.paths import resolve_config_path
from ..base import ModelTemplate
from .builder import buildSwatPlusParams, build_calibration_skeleton
from .discovery import discover_swatplus_project
from .library import SWATPLUS_PARAM_LIBRARY
from .series import buildSwatPlusSeries
from .validate import validate_swatplus_config


class SwatPlusTemplate(ModelTemplate):
    """SWAT+ model template — calibration.cal-driven formatted-text output."""

    def discover(self, project_path: Path) -> Dict[str, Any]:
        return discover_swatplus_project(project_path)

    def get_writer_type(self) -> str:
        return "formatted_text"

    def get_reader_type(self) -> str:
        return "text"

    def validate(self, raw: Dict[str, Any], base_path: Path) -> list:
        return validate_swatplus_config(raw, base_path)

    def build_config(self, raw: Dict[str, Any], base_path: Path) -> Dict[str, Any]:
        raw = copy.deepcopy(raw)

        projectPath = resolve_config_path(
            raw.get("basic", {}).get("projectPath", "."), base_path
        )
        meta = self.discover(projectPath)

        raw["series"] = buildSwatPlusSeries(
            raw.get("series", []), meta, readerType=self.get_reader_type()
        )
        raw["parameters"] = buildSwatPlusParams(
            raw.get("parameters", {}),
            meta,
            SWATPLUS_PARAM_LIBRARY,
            writerType=self.get_writer_type(),
        )

        # Build skeleton from the SAME resolved physical list that drives
        # row assignment — guarantees row count, order, names, and CHG_TYPE
        # are all consistent between skeleton and write-plan rows.
        phys = raw["parameters"].get("physical", [])
        skeleton = build_calibration_skeleton(phys)
        for pp in phys:
            f = pp.get("file", {})
            if isinstance(f, dict) and f.get("name") == "calibration.cal":
                f["_skel"] = skeleton
            # _resolved_ids and filter are internal builder artifacts consumed
            # during skeleton generation — not part of the general config schema.
            pp.pop("_resolved_ids", None)
            pp.pop("filter", None)

        raw["version"] = "general"
        return raw
