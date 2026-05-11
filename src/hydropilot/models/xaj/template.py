import copy
from pathlib import Path
from typing import Any, Dict, List

from ...config.paths import resolve_config_path
from ..base import ModelTemplate
from .builder import buildXajParams
from .discovery import discover_xaj_project
from .library import XAJ_PARAM_LIBRARY
from .series import buildXajSeries


class XajTemplate(ModelTemplate):
    """XAJ model template backed by CSV input and output files."""

    def discover(self, project_path: Path) -> Dict[str, Any]:
        return discover_xaj_project(project_path)

    def resolve_variable(self, var_name: str, meta: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        raise NotImplementedError("XAJ variables are resolved through buildXajSeries")

    def get_default_library(self, param_names: List[str], meta: Dict[str, Any], overrides=None) -> Dict[str, Any]:
        raise NotImplementedError("XAJ default library expansion is handled by buildXajParams")

    def get_writer_type(self) -> str:
        return "csv"

    def get_reader_type(self) -> str:
        return "csv"

    def build_config(self, raw: Dict[str, Any], base_path: Path) -> Dict[str, Any]:
        raw = copy.deepcopy(raw)

        projectPath = resolve_config_path(raw.get("basic", {}).get("projectPath", "."), base_path)
        meta = self.discover(projectPath)

        raw["series"] = buildXajSeries(raw.get("series", []), meta, readerType=self.get_reader_type())
        raw["parameters"] = buildXajParams(
            raw.get("parameters", {}),
            meta,
            XAJ_PARAM_LIBRARY,
            writerType=self.get_writer_type(),
        )

        raw["version"] = "general"
        return raw
