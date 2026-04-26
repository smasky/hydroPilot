import csv
from pathlib import Path

import numpy as np


def write_test_series_csv(result) -> Path:
    path = result.archivePath / "test_series.csv"
    columns: list[tuple[str, np.ndarray]] = []
    for sid in result.cfg.series_index.keys():
        for suffix in ("sim", "obs"):
            key = f"{sid}.{suffix}"
            if key in result.context:
                columns.append((key, np.asarray(result.context[key], dtype=float).ravel()))

    max_len = max((len(values) for _name, values in columns), default=0)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["index"] + [name for name, _values in columns])
        for row_index in range(max_len):
            row = [row_index + 1]
            for _name, values in columns:
                if row_index >= len(values):
                    row.append("")
                else:
                    row.append(_format_series_value(values[row_index]))
            writer.writerow(row)
    return path


def write_test_param_csv(result) -> Path:
    path = result.archivePath / "test_param.csv"
    records = result.context.get("param.writeRecords", [])
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["file", "param", "old_value", "new_value", "locator"],
            extrasaction="ignore",
        )
        writer.writeheader()
        for record in records:
            writer.writerow({
                "file": record.get("file", ""),
                "param": record.get("param", ""),
                "old_value": _format_scalar(record.get("old_value", "")),
                "new_value": _format_scalar(record.get("new_value", "")),
                "locator": record.get("locator", ""),
            })
    return path


def _format_series_value(value) -> str:
    value = float(value)
    if np.isnan(value):
        return "NaN"
    return str(value)


def _format_scalar(value) -> str:
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
