from pathlib import Path
from typing import Any, Dict, Tuple

from ..io.writers import getWriter
from ..io.writers.targets import resolve_file_targets
from ..runtime.initializer import InstanceInitializer


class ParamWritePlan(InstanceInitializer):
    def __init__(self, cfg):
        self.cfg = cfg
        self.write_tasks: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self.instance_tasks: Dict[str, Dict[Tuple[str, str], Dict[str, Any]]] = {}
        self.instanceRegistrationSummary: Dict[str, list[dict]] = {}
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
            names_by_index[spec.index] = spec.label

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
                    self.write_tasks[task_key] = {
                        "fileName": rel_file,
                        "writerType": writer_type,
                        "indices": [],
                    }
                task = self.write_tasks[task_key]

                raw_item_for_file = dict(raw_item)
                raw_file_for_file = dict(raw_item_for_file["file"])
                raw_file_for_file["name"] = rel_file
                raw_item_for_file["file"] = raw_file_for_file
                lib_info_for_file = writer_cls.buildSpec(raw_item_for_file)

                if has_skel:
                    # defer registration — skeleton is written during
                    # initialize() and the instance-local handler cannot
                    # read it yet.
                    task.setdefault("_pending_reg", []).append(
                        (spec, lib_info_for_file, self.cfg.parameters.hardBound)
                    )
                    task["indices"].append(spec.index)
                    registered_by_index[spec.index] += 1
                else:
                    task.setdefault("_registrations", []).append(
                        (spec, lib_info_for_file, self.cfg.parameters.hardBound)
                    )
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
        """Build instance-local writer handlers and register parameters.

        Implements ``InstanceInitializer.initialize``. Runs once per instance
        after the project copy is created. Writer handlers are isolated per
        instance so parallel runs never share mutable writer state.
        """
        root = Path(instance_path)
        tasks_for_instance: Dict[Tuple[str, str], Dict[str, Any]] = {}
        summary = {
            spec.index: {"index": spec.index, "param": spec.label, "matchedFiles": 0, "skippedFiles": 0}
            for spec in self.cfg.parameters.physical
        }

        for task_key, task in self.write_tasks.items():
            writer_cls = getWriter(task["writerType"])
            target = root / task["fileName"]
            handler = writer_cls(str(target))

            skel = task.get("_skel")
            pending = task.get("_pending_reg", [])
            registrations = task.get("_registrations", [])

            if skel is not None:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(skel, encoding="utf-8")

            handler.initialize(str(target))

            indices = []
            for spec, lib_info, hard_bound in registrations + pending:
                if handler.register_param(spec, lib_info, hard_bound):
                    indices.append(spec.index)
                    summary[spec.index]["matchedFiles"] += 1
                else:
                    summary[spec.index]["skippedFiles"] += 1

            if indices:
                tasks_for_instance[task_key] = {
                    "fileName": task["fileName"],
                    "writerType": task["writerType"],
                    "handler": handler,
                    "indices": indices,
                }

        for item in summary.values():
            if item["matchedFiles"] == 0:
                raise ValueError(
                    f"No writable entries found for parameter '{item['param']}' in any target file. "
                    "Check file pattern and fixed_width line/start/width/maxNum/selectIndex settings."
                )

        self.instance_tasks[instance_path] = tasks_for_instance
        self.instanceRegistrationSummary[instance_path] = list(summary.values())

    def get_instance_tasks(self, instance_path: str) -> Dict[Tuple[str, str], Dict[str, Any]]:
        try:
            return self.instance_tasks[instance_path]
        except KeyError as exc:
            raise ValueError(f"Instance handlers not initialized for path: {instance_path}") from exc

    def clear_instance_tasks(self) -> None:
        self.instance_tasks.clear()
        self.instanceRegistrationSummary.clear()
