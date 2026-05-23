import shutil
from pathlib import Path

import numpy as np
import yaml


def apply_design_params(cfg, X, out_dir: str | Path) -> Path:
    from ..runtime.services import ExecutionServices

    services = ExecutionServices.from_config(cfg)
    ordered = _coerce_named_or_positional_values(X, [item.name for item in cfg.parameters.design], "design")
    target = _prepare_target_dir(cfg, out_dir)
    services.paramWritePlan.initialize(str(target))
    env: dict = {"warnings": []}
    services.paramApplier.apply(str(target), ordered, env)
    return target


def apply_physical_params(cfg, P, out_dir: str | Path) -> Path:
    from ..runtime.services import ExecutionServices

    services = ExecutionServices.from_config(cfg)
    target = _prepare_target_dir(cfg, out_dir)
    services.paramWritePlan.initialize(str(target))
    env: dict = {"warnings": []}
    ordered = _coerce_named_or_positional_values(P, [item.name for item in cfg.parameters.physical], "physical")
    services.paramApplier.apply(str(target), ordered, env)
    return target


def apply_from_yaml(path: str | Path) -> tuple[str, Path]:
    spec_path = Path(path)
    with spec_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise ValueError("apply YAML root must be a mapping/object")

    config_path = raw.get("config")
    mode = raw.get("mode")
    values = raw.get("values")
    out_dir = raw.get("outDir")

    if not config_path:
        raise ValueError("apply YAML missing config")
    if mode not in ("design", "physical"):
        raise ValueError("apply YAML mode must be design or physical")
    if values is None:
        raise ValueError("apply YAML missing values")
    if not out_dir:
        raise ValueError("apply YAML missing outDir")

    from ..config.loader import load_config

    cfg = load_config(config_path)
    if mode == "design":
        return mode, apply_design_params(cfg, values, out_dir)
    return mode, apply_physical_params(cfg, values, out_dir)


def _prepare_target_dir(cfg, out_dir: str | Path) -> Path:
    target = Path(out_dir)
    if target.exists():
        raise FileExistsError(f"apply target already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(cfg.basic.projectPath, target)
    return target


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
