from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml

from hydropilot.config.loader import load_config
from hydropilot.reporting.records import record_status
from hydropilot.runtime.context import (
    apply_on_error_defaults,
    create_context,
    ensure_warnings,
    has_error,
    set_physical_params,
    set_run_error,
    set_unexpected_error,
)
from hydropilot.runtime.errors import RunError
from hydropilot.runtime.session import Session
from hydropilot.testing.runner import _collect_scalars, _find_project_copy


@dataclass(slots=True)
class SingleRunResult:
    status: str
    configPath: Path
    cfg: object
    runPath: Path
    archivePath: Path
    projectCopy: Path
    batchId: int
    runId: int
    xLabels: list[str]
    pLabels: list[str]
    X: np.ndarray
    P: np.ndarray
    objs: np.ndarray
    cons: np.ndarray | None
    diags: np.ndarray | None
    context: dict


def run_from_yaml(path: str | Path) -> tuple[str, SingleRunResult]:
    spec_path = Path(path)
    with spec_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise ValueError("run YAML root must be a mapping/object")

    config_path = raw.get("config")
    mode = raw.get("mode")
    values = raw.get("values")

    if not config_path:
        raise ValueError("run YAML missing config")
    if mode not in ("design", "physical"):
        raise ValueError("run YAML mode must be design or physical")
    if values is None:
        raise ValueError("run YAML missing values")

    cfg = load_config(config_path)
    result = run_once(cfg, config_path, mode, values)
    return mode, result


def run_once(cfg, config_path: str | Path, mode: str, values) -> SingleRunResult:
    session = Session(cfg, str(config_path))
    try:
        batch_id = session.reporter.newBatchId()
        x, context = _run_single(session, cfg, mode, values, batch_id)
        session.reporter.close()
        return _build_single_run_result(config_path, cfg, session, x, batch_id, context)
    finally:
        session.close()


def format_run_summary(result: SingleRunResult) -> str:
    verdict = {
        "passed": "PASSED",
        "warning": "PASSED WITH WARNINGS",
        "failed": "FAILED",
    }.get(result.status, result.status.upper())
    lines = [
        f"HydroPilot run {verdict}",
        "",
        f"Config: {result.configPath}",
        f"Archive: {result.archivePath}",
        f"Run: batch={result.batchId} run={result.runId}",
        "",
        "Runtime:",
        f"  parallel: {result.cfg.basic.parallel}",
        f"  keep project copy: {'yes' if result.cfg.basic.keepInstances else 'no'}",
        f"  run path: {result.runPath}",
        f"  project copy: {result.projectCopy}",
        "",
        "Inputs:",
        "  X:",
    ]
    lines.extend(f"    {name} = {_format_number(value)}" for name, value in zip(result.xLabels, result.X))
    lines.append("  P:")
    lines.extend(f"    {name} = {_format_number(value)}" for name, value in zip(result.pLabels, result.P))
    lines.extend([
        "",
        "Objectives:",
    ])
    lines.extend(_terminal_scalar_rows([item.id for item in result.cfg.objectives.items], result.objs))
    if result.cfg.constraints.items:
        lines.extend(["", "Constraints:"])
        lines.extend(_terminal_scalar_rows([item.id for item in result.cfg.constraints.items], result.cons))
    if result.cfg.diagnostics.items:
        lines.extend(["", "Diagnostics:"])
        lines.extend(_terminal_scalar_rows([item.id for item in result.cfg.diagnostics.items], result.diags))
    lines.extend([
        "",
        "Files:",
        f"  summary: {result.archivePath / 'summary.csv'}",
        f"  errors: {result.archivePath / 'error.log'}",
        f"  runner stdout: {result.projectCopy / 'runner.stdout.log'}",
        f"  runner stderr: {result.projectCopy / 'runner.stderr.log'}",
    ])
    return "\n".join(lines)


def _resolve_input_vector(session, cfg, mode: str, values) -> np.ndarray:
    labels = [item.name for item in cfg.parameters.design]
    return _coerce_named_or_positional_values(values, labels, mode)


def _run_single(session, cfg, mode: str, values, batch_id: int) -> tuple[np.ndarray, dict]:
    if mode == "design":
        x = _resolve_input_vector(session, cfg, mode, values)
        return x, session.executor._run_one(x, 0, batch_id)

    p_labels = [item.name for item in cfg.parameters.physical]
    p = _coerce_named_or_positional_values(values, p_labels, mode)
    x = np.full(len(cfg.parameters.design), np.nan, dtype=float)
    return x, _run_one_physical(session, cfg, p, batch_id)


def _run_one_physical(session, cfg, p: np.ndarray, batch_id: int) -> dict:
    work_path = session.workspace.acquire_instance()
    context = create_context(np.full(len(cfg.parameters.design), np.nan, dtype=float), 0, batch_id)
    try:
        session.executor.services.paramApplier.apply(work_path, p, context)
        set_physical_params(context, p)
        session.executor.services.runner.run(work_path, cfg.basic.command, cfg.basic.timeout)
        context = session.executor.services.seriesExtractor.extract(work_path, context)
        ensure_warnings(context)
        scalars = session.executor.services.evaluator.evaluate_all(context)
        context.update(scalars)
    except RunError as e:
        session.executor._archive_runner_logs(work_path, context, e)
        set_run_error(context, e)
    except Exception as e:
        session.executor._archive_runner_logs(work_path, context, e)
        set_unexpected_error(context, e)
    finally:
        session.workspace.release_instance(work_path)
        if has_error(context):
            apply_on_error_defaults(context, cfg)
        if session.reporter is not None:
            try:
                session.reporter.submit(context)
            except RuntimeError:
                pass
    return context


def _build_single_run_result(config_path, cfg, session, x, batch_id, context) -> SingleRunResult:
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
    project_copy = _find_project_copy(session.runPath)
    return SingleRunResult(
        status=_run_status(context),
        configPath=Path(config_path).resolve(),
        cfg=cfg,
        runPath=Path(session.runPath),
        archivePath=Path(session.archivePath),
        projectCopy=project_copy,
        batchId=int(batch_id),
        runId=int(context.get("i", 0)) + 1,
        xLabels=list(session.xLabels),
        pLabels=[item.name for item in cfg.parameters.physical],
        X=np.asarray(x, dtype=float).ravel(),
        P=p,
        objs=objs,
        cons=cons,
        diags=diags,
        context=context,
    )


def _coerce_named_or_positional_values(values, labels: list[str], mode: str) -> np.ndarray:
    if isinstance(values, dict):
        missing = [label for label in labels if label not in values]
        extra = sorted(key for key in values.keys() if key not in labels)
        if missing:
            raise ValueError(f"missing {mode} values for: {missing}")
        if extra:
            raise ValueError(f"unexpected {mode} values: {extra}")
        return np.asarray([values[label] for label in labels], dtype=float)
    return np.asarray(values, dtype=float)


def _run_status(context: dict) -> str:
    status = record_status(context)
    if status == "ok":
        return "passed"
    if status == "warning":
        return "warning"
    return "failed"


def _terminal_scalar_rows(labels: list[str], values) -> list[str]:
    if not labels:
        return ["  none"]
    return [f"  {label} = {_format_number(value)}" for label, value in zip(labels, np.asarray(values).ravel())]


def _format_number(value) -> str:
    try:
        value = float(value)
    except Exception:
        return str(value)
    if np.isnan(value):
        return "NaN"
    if np.isposinf(value):
        return "inf"
    if np.isneginf(value):
        return "-inf"
    return str(value)
