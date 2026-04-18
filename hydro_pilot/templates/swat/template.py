import copy
from pathlib import Path
from typing import Any, Dict, List

from ..base import ModelTemplate
from .discovery import discover_swat_project
from .variables import calcSwatOutputRows
from .library import get_swat_library, SWAT_PARAM_LIBRARY
from .builder import buildSwatParams
from .series import buildSwatSeries


class SwatTemplate(ModelTemplate):
    """SWAT model template.

    Converts simplified SWAT config into standard RunConfig format.
    Handles SWAT-specific knowledge: output file formats, variable
    locations, parameter definitions, and project file parsing.
    """

    def discover(self, project_path: Path) -> Dict[str, Any]:
        return discover_swat_project(project_path)

    def resolve_variable(self, var_name: str, meta: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Resolve SWAT output rows. Delegates to calcSwatOutputRows."""
        outputType = kwargs.get("outputType", "rch")
        return calcSwatOutputRows(
            meta=meta,
            outputType=outputType,
            subbasin=kwargs.get("subbasin"),
            period=kwargs.get("period"),
            timestep=kwargs.get("timestep"),
            hru=kwargs.get("hru"),
        )

    def get_default_library(self, param_names: List[str], meta: Dict[str, Any], overrides=None) -> Dict[str, Any]:
        return get_swat_library(param_names, meta, overrides)

    def get_writer_type(self) -> str:
        return "fixed_width"

    def get_reader_type(self) -> str:
        return "text"

    def build_config(self, raw: Dict[str, Any], base_path: Path) -> Dict[str, Any]:
        """Transform simplified SWAT config into general-compatible raw dict.

        Handles the two-layer parameter architecture (design/physical)
        and generates temporary YAML files for downstream ParametersSpec.
        """
        raw = copy.deepcopy(raw)

        projectPath = base_path / Path(raw.get("basic", {}).get("projectPath", "."))
        workPath = base_path / Path(raw.get("basic", {}).get("workPath", "."))
        meta = self.discover(projectPath)

        defaultReaderType = self.get_reader_type()
        raw["series"] = buildSwatSeries(raw.get("series", []), meta, readerType=defaultReaderType)

        # Handle parameters: new two-layer design/physical architecture
        params = raw.get("parameters", {})
        paramsResult = buildSwatParams(
            params,
            meta,
            SWAT_PARAM_LIBRARY,
            workPath,
            writerType=self.get_writer_type(),
        )
        raw["parameters"] = paramsResult

        # Ensure reporter block exists in output
        if "reporter" not in raw or not isinstance(raw["reporter"], dict):
            raw["reporter"] = {}
        raw["reporter"].setdefault("flushInterval", 50)
        raw["reporter"].setdefault("holdingPenLimit", 20)
        raw["reporter"].setdefault("series", [])

        raw["version"] = "general"
        return raw
