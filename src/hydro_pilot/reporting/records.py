from datetime import datetime
from typing import Any

import numpy as np


def sanitize_labels(labels):
    cleaned = []
    seen = set()
    for i, x in enumerate(labels):
        name = str(x)
        name = name.replace("[", "_").replace("]", "_").replace(".", "_").strip()
        if not name:
            name = f"x_{i+1}"
        base = name
        suffix = 1
        while name in seen:
            suffix += 1
            name = f"{base}_{suffix}"
        seen.add(name)
        cleaned.append(name)
    return cleaned


def parse_report_ids(cfg):
    allSeriesIds = [f"{k}_sim" for k in cfg.series_index.keys()]

    orderedScalars = []
    seen = set()
    for oid in cfg.objectives.use:
        if oid not in seen:
            orderedScalars.append(oid)
            seen.add(oid)
    for cid in cfg.constraints.use:
        if cid not in seen:
            orderedScalars.append(cid)
            seen.add(cid)
    for did in cfg.diagnostics.use:
        if did not in seen:
            orderedScalars.append(did)
            seen.add(did)
    for d in cfg.derived:
        if d.id not in seen:
            orderedScalars.append(d.id)
            seen.add(d.id)

    repCfg = getattr(cfg, "reporter", None)
    if repCfg:
        rawOutSeries = list(getattr(repCfg, "series", []))
        outSeriesIds = []
        for s in rawOutSeries:
            s = str(s)
            outSeriesIds.append(f"{s}_sim" if not s.endswith("_sim") else s)
    else:
        outSeriesIds = []

    return allSeriesIds, orderedScalars, outSeriesIds


def build_csv_fields(allScalarIds, xLabels, pLabels):
    fields = ["batch_id", "run_id", "status"]
    fields += allScalarIds
    fields += [f"X_{x}" for x in xLabels]
    if pLabels:
        fields += [f"P_{p}" for p in pLabels]
    return fields


def to_scalar_or_nan(value):
    if value is None:
        return np.nan
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if isinstance(value, (list, tuple, np.ndarray)):
        arr = np.asarray(value)
        if arr.size == 0:
            return np.nan
        if arr.size == 1:
            return arr.reshape(-1)[0].item() if hasattr(arr.reshape(-1)[0], "item") else arr.reshape(-1)[0]
        raise ValueError(f"Expected scalar-compatible value, but got shape {arr.shape}")
    return value


def normalize_batch_run(item):
    batchId = item.get("batch_id", -1)
    if hasattr(batchId, "item"):
        batchId = batchId.item()
    batchId = int(batchId)

    runId = item.get("i", -1)
    if hasattr(runId, "item"):
        runId = runId.item()
    runId = int(runId) + 1
    return batchId, runId


def record_status(item):
    if "error" in item:
        return "error"
    if item.get("warnings"):
        return "warning"
    return "ok"


def collect_error_entries(error, warnings):
    entries = []
    if error:
        entries.append(error)
    for w in warnings:
        if isinstance(w, dict):
            entries.append(w)
        else:
            entries.append({
                "stage": w.stage,
                "code": w.code,
                "target": w.target,
                "message": w.message,
                "severity": w.severity,
                "traceback": getattr(w, "traceback", ""),
            })
    return entries


def make_error_json(batchId, runId, entry):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    jsonObj = {
        "ts": ts,
        "batch": batchId,
        "run": runId,
        "severity": entry.get("severity", "fatal"),
        "stage": entry.get("stage", ""),
        "code": entry.get("code", ""),
        "target": entry.get("target", ""),
        "msg": entry.get("message", ""),
    }
    if entry.get("traceback", ""):
        jsonObj["tb"] = entry["traceback"]
    return ts, jsonObj
