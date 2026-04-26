from pathlib import Path
from typing import Any, Dict, List, Optional


class ModelTemplate:
    def discover(self, project_path: Path) -> Dict[str, Any]:
        raise NotImplementedError

    def resolve_variable(self, var_name: str, meta: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        raise NotImplementedError

    def get_default_library(
        self,
        param_names: List[str],
        meta: Dict[str, Any],
        overrides: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        raise NotImplementedError

    def get_writer_type(self) -> str:
        raise NotImplementedError

    def get_reader_type(self) -> str:
        raise NotImplementedError

    def build_config(self, raw: Dict[str, Any], base_path: Path) -> Dict[str, Any]:
        import copy
        raw = copy.deepcopy(raw)
        raw["version"] = "general"
        return raw
