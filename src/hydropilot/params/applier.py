from pathlib import Path
from typing import Dict, List

from .transformer import Transformer
from ..runtime.context import append_warning
from ..runtime.errors import RunError


class ParamApplier:
    def __init__(self, cfg, function_manager, write_plan):
        self.cfg = cfg
        transform_func = cfg.parameters.transformer if hasattr(cfg.parameters, "transformer") else None
        self.transformer = Transformer(function_manager, transform_func)
        self.write_plan = write_plan

    def apply(self, work_path: str, X, env) -> None:
        data_source = self.transformer.transform(X)

        work_root = Path(work_path)
        all_clamp_events: List[dict] = []
        all_write_records: List[dict] = []

        for (_task_file, _writer_type), task in self.write_plan.write_tasks.items():
            file_name = task["fileName"]
            handler = task["handler"]
            target_file = work_root / file_name
            indices = task["indices"]
            try:
                if len(data_source) > 0 and len(indices) > 0 and max(indices) >= len(data_source):
                    raise RunError(
                        stage="params",
                        code="INDEX_OUT_OF_BOUNDS",
                        target=file_name,
                        message=f"Data source has {len(data_source)} items, but requested index {max(indices)} for file '{file_name}'.",
                    )
                values_to_write = data_source[indices]
                write_result = handler.set_values_and_save(str(target_file), indices, values_to_write)
                if isinstance(write_result, dict):
                    all_clamp_events.extend(write_result.get("clamp_events", []))
                    all_write_records.extend(write_result.get("write_records", []))
                else:
                    all_clamp_events.extend(write_result)
            except RunError:
                raise
            except Exception as e:
                raise RunError(
                    stage="params",
                    code="FILE_WRITE_ERROR",
                    target=file_name,
                    message=f"Error writing to file {file_name}: {str(e)}",
                )

        env["param.writeRecords"] = all_write_records
        self._aggregate_clamp_warnings(all_clamp_events, env)

    def get_physical_params(self, X):
        return self.transformer.transform(X)

    def _aggregate_clamp_warnings(self, events: List[dict], env: dict) -> None:
        if not events:
            return

        total_files_by_param: Dict[str, int] = {}
        for (_task_file, _writer_type), task in self.write_plan.write_tasks.items():
            param_names = set()
            handler = task["handler"]
            for idx in task["indices"]:
                p = handler.params.get(idx)
                if p:
                    param_names.add(p.name)
            for name in param_names:
                total_files_by_param[name] = total_files_by_param.get(name, 0) + 1

        by_param: Dict[str, List[dict]] = {}
        for ev in events:
            name = ev.get("param", "unknown")
            by_param.setdefault(name, []).append(ev)

        for param_name, param_events in by_param.items():
            n_files = len(param_events)
            n_total = total_files_by_param.get(param_name, n_files)
            first = param_events[0]
            append_warning(env, RunError(
                stage="params",
                code="CLAMPED",
                target=param_name,
                message=(
                    f"value {first['raw']:.6g} clamped to {first['clamped']:.6g}, "
                    f"bounds=[{first['lb']}, {first['ub']}], affected {n_files}/{n_total} files"
                ),
            ))
