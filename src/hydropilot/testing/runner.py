from dataclasses import dataclass
from pathlib import Path

import numpy as np

from hydropilot.config.loader import load_config
from hydropilot.reporting.records import record_status
from hydropilot.runtime.session import Session

from .artifacts import write_test_param_csv, write_test_series_csv
from .report import write_test_report
from .vector import build_default_test_vector


@dataclass(slots=True)
class ConfigTestResult:
    status: str
    configPath: Path
    cfg: object
    runPath: Path
    archivePath: Path
    projectCopy: Path
    reportPath: Path
    batchId: int
    runId: int
    xLabels: list[str]
    pLabels: list[str]
    X: np.ndarray
    P: np.ndarray
    objs: np.ndarray
    cons: np.ndarray | None
    diags: np.ndarray | None
    series: dict[str, np.ndarray] | None
    context: dict


def run_config_test(config_path: str | Path) -> ConfigTestResult:
    cfg = load_config(config_path)
    _force_test_runtime(cfg)
    x = build_default_test_vector(cfg)

    session = Session(cfg, str(config_path))
    try:
        batch_id = session.reporter.newBatchId()
        context = session.executor._run_one(x, 0, batch_id)
        session.reporter.close()
        result = _build_result(config_path, cfg, session, x, batch_id, context)
        write_test_series_csv(result)
        write_test_param_csv(result)
        result.reportPath = write_test_report(result)
        return result
    finally:
        session.close()


def _force_test_runtime(cfg) -> None:
    cfg.basic.parallel = 1
    cfg.basic.keepInstances = True


def _build_result(config_path, cfg, session, x, batch_id, context) -> ConfigTestResult:
    p = np.asarray(context.get("P", session.executor.services.paramApplier.get_physical_params(x)), dtype=float).ravel()
    objs = _collect_scalars(context, [item.id for item in cfg.objectives.items], [
        session.executor._objective_penalty(i) for i, _item in enumerate(cfg.objectives.items)
    ])
    cons = None
    if cfg.constraints.items:
        cons = _collect_scalars(context, [item.id for item in cfg.constraints.items], [
            session.executor._constraint_penalty() for _item in cfg.constraints.items
        ])
    diags = None
    if cfg.diagnostics.items:
        diags = _collect_scalars(context, [item.id for item in cfg.diagnostics.items], [
            item.on_error for item in cfg.diagnostics.items
        ])
    series = _collect_series(context, cfg)
    project_copy = _find_project_copy(session.runPath)
    status = _test_status(context)
    return ConfigTestResult(
        status=status,
        configPath=Path(config_path).resolve(),
        cfg=cfg,
        runPath=Path(session.runPath),
        archivePath=Path(session.archivePath),
        projectCopy=project_copy,
        reportPath=Path(session.archivePath) / "test-report.md",
        batchId=int(batch_id),
        runId=int(context.get("i", 0)) + 1,
        xLabels=list(session.xLabels),
        pLabels=[item.name for item in cfg.parameters.physical],
        X=np.asarray(x, dtype=float).ravel(),
        P=p,
        objs=objs,
        cons=cons,
        diags=diags,
        series=series,
        context=context,
    )


def _collect_scalars(context: dict, labels: list[str], defaults: list[float]) -> np.ndarray:
    values = []
    for label, default in zip(labels, defaults):
        values.append(_to_float(context.get(label, default), default))
    return np.asarray(values, dtype=float)


def _to_float(value, default: float) -> float:
    try:
        arr = np.asarray(value)
        if arr.size == 1:
            return float(arr.reshape(-1)[0])
    except Exception:
        pass
    return float(default)


def _collect_series(context: dict, cfg) -> dict[str, np.ndarray] | None:
    series = {}
    for sid in cfg.series_index.keys():
        key = f"{sid}.sim"
        if key in context:
            series[sid] = np.asarray(context[key], dtype=float).reshape(1, -1)
    return series or None


def _find_project_copy(run_path) -> Path:
    candidates = sorted(Path(run_path).glob("instance_*"))
    if not candidates:
        raise FileNotFoundError(f"No instance_* project copy found under {run_path}")
    return candidates[0]


def _test_status(context: dict) -> str:
    status = record_status(context)
    if status == "ok":
        return "passed"
    if status == "warning":
        return "warning"
    return "failed"
