from pathlib import Path
from typing import Any, Dict, Tuple

from ..io.writers import getWriter
from ..io.writers.targets import resolve_file_targets
from ..runtime.initializer import InstanceInitializer


class ParamWritePlan(InstanceInitializer):
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

            raw_file_name = file_info["name"]
            has_skel = "_skel" in file_info
            if has_skel and isinstance(raw_file_name, str):
                # skeleton-provided file — created during instance init,
                # does not need to pre-exist in the source project.
                real_files = [raw_file_name]
            else:
                real_files = resolve_file_targets(project_root, raw_file_name)
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

                raw_item_for_file = dict(raw_item)
                raw_file_for_file = dict(raw_item_for_file["file"])
                raw_file_for_file["name"] = rel_file
                raw_item_for_file["file"] = raw_file_for_file
                lib_info_for_file = writer_cls.buildSpec(raw_item_for_file)

                if has_skel:
                    # defer registration — skeleton is written during
                    # initialize() and the handler cannot read it yet.
                    task.setdefault("_pending_reg", []).append(
                        (spec, lib_info_for_file, self.cfg.parameters.hardBound)
                    )
                    task["indices"].append(spec.index)
                    registered_by_index[spec.index] += 1
                elif handler.register_param(spec, lib_info_for_file, self.cfg.parameters.hardBound):
                    task["indices"].append(spec.index)
                    registered_by_index[spec.index] += 1

                if has_skel and "_skel" not in task:
                    task["_skel"] = file_info["_skel"]

        for index, count in registered_by_index.items():
            if count == 0:
                name = names_by_index.get(index, str(index))
                raise ValueError(
                    f"No writable entries found for parameter '{name}' in any target file. "
                    f"Check file pattern and fixed_width line/start/width/maxNum/selectIndex settings."
                )

    def initialize(self, instance_path: str) -> None:
        """Call ``initialize()`` on every writer handler that opts in.

        Implements ``InstanceInitializer.initialize``.  Runs once per instance
        after the project copy is created.

        For skeleton-provided files (``_skel`` on the task) the skeleton is
        written to the instance before the handler loads it, and any
        registrations that were deferred in ``_build_plan`` (because the
        skeleton did not exist in the source project) are replayed.
        """
        from pathlib import Path

        root = Path(instance_path)
        for (_task_file, _writer_type), task in self.write_tasks.items():
            handler = task["handler"]
            target = root / task["fileName"]

            skel = task.get("_skel")
            pending = task.get("_pending_reg", [])
            if skel is not None:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(skel, encoding="utf-8")
                handler.initialize(str(target))
                for spec, lib_info, hard_bound in pending:
                    handler.register_param(spec, lib_info, hard_bound)
            else:
                handler.initialize(str(target))
