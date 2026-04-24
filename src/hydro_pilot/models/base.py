from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional


class ModelTemplate(ABC):
    """Abstract interface for model-specific templates.

    Each hydrological model implements a Template that converts
    simplified user config into a full RunConfig. The template
    handles model-specific knowledge (file formats, variable
    locations, parameter definitions) so users don't have to.
    """

    @abstractmethod
    def discover(self, project_path: Path) -> Dict[str, Any]:
        """Discover metadata from model project files.

        Args:
            project_path: Path to the model project directory.

        Returns:
            Dict of metadata, e.g. {"n_subbasins": 13, "start_year": 2000, ...}
        """

    @abstractmethod
    def resolve_variable(self, var_name: str, meta: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Resolve a variable name to ExtractSpec-compatible dict.

        Args:
            var_name: Variable name (e.g. "FLOW_OUT").
            meta: Metadata from discover().
            **kwargs: Additional user params (subbasin, period, timestep, etc.)

        Returns:
            Dict with keys like file, rowRanges, colSpan, etc.
        """

    @abstractmethod
    def get_default_library(self, param_names: List[str], meta: Dict[str, Any], overrides: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Return library definitions for the given parameter names.

        Args:
            param_names: List of parameter names to calibrate.
            meta: Metadata from discover().
            overrides: Per-parameter overrides, e.g.
                {"CN2": {"bounds": [40, 90], "mode": "r"}}

        Returns:
            Dict in parameter_library YAML format.
        """

    @abstractmethod
    def get_writer_type(self) -> str:
        """Return the default writer type for this model."""

    @abstractmethod
    def get_reader_type(self) -> str:
        """Return the default reader type for this model."""

    def build_config(self, raw: Dict[str, Any], base_path: Path) -> Dict[str, Any]:
        """Transform simplified user config into general-compatible raw dict.

        This is the main entry point called by load_config().
        Subclasses should override this to handle model-specific
        series resolution, parameter expansion, etc.
        The default implementation only sets version to "general".
        """
        import copy
        raw = copy.deepcopy(raw)
        raw["version"] = "general"
        return raw
