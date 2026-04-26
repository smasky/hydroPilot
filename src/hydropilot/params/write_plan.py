from pathlib import Path
from typing import Any, Dict, Tuple

from ..io.writers import getWriter
from ..io.writers.targets import resolve_file_targets


class ParamWritePlan:
    def __init__(self, cfg):
        self.cfg = cfg
        self.write_tasks: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._build_plan()

    @staticmethod
    def _to_raw_mapping(item: Any) -> Dict[str, Any]:
        if hasattr(item, "model_dump"):
            return dict(item.model_dump())
        if isinstance(item, dict):
            return dict(item)
        raise ValueError(f"Unsupported physical parameter item type: {type(item)}")

    def _build_plan(self) -> None:
        project_root = Path(self.cfg.basic.projectPath)
        registered_by_index: Dict[int, int] = {}
        names_by_index: Dict[int, str] = {}

        for spec in self.cfg.parameters.physical:
            raw_item = self._to_raw_mapping(spec)
            file_info = spec.file
            writer_type = spec.writerType
            writer_cls = getWriter(writer_type)
            lib_info = writer_cls.buildSpec(raw_item)
            writer_cls.validateSpec(raw_item)
            registered_by_index.setdefault(spec.index, 0)
            names_by_index[spec.index] = spec.name

            real_files = resolve_file_targets(project_root, file_info["name"])
            for rel_file in real_files:
                task_key = (rel_file, writer_type)
                if task_key not in self.write_tasks:
                    abs_file = project_root / rel_file
                    self.write_tasks[task_key] = {
                        "fileName": rel_file,
                        "writerType": writer_type,
                        "handler": writer_cls(str(abs_file)),
                        "indices": [],
                    }
                task = self.write_tasks[task_key]
                handler = task["handler"]

                lib_info_for_file = writer_cls.buildSpec({
                    "name": lib_info.name,
                    "type": lib_info.type,
                    "bounds": lib_info.bounds,
                    "file": {
                        "name": rel_file,
                        "line": lib_info.file.line,
                        "start": lib_info.file.start,
                        "width": lib_info.file.width,
                        "precision": lib_info.file.precision,
                        "maxNum": lib_info.file.maxNum,
                        "selectIndex": lib_info.file.selectIndex,
                    },
                })

                if handler.register_param(spec, lib_info_for_file, self.cfg.parameters.hardBound):
                    task["indices"].append(spec.index)
                    registered_by_index[spec.index] += 1

        for index, count in registered_by_index.items():
            if count == 0:
                name = names_by_index.get(index, str(index))
                raise ValueError(
                    f"No writable entries found for parameter '{name}' in any target file. "
                    f"Check file pattern and fixed_width line/start/width/maxNum/selectIndex settings."
                )
