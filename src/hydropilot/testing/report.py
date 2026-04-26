from pathlib import Path
from typing import Iterable

import numpy as np

from hydropilot.reporting.records import collect_error_entries


def write_test_report(result) -> Path:
    path = result.archivePath / "test-report.md"
    lines = [
        "# HydroPilot Test Report",
        "",
        "## Verdict",
        "",
        "| item | value |",
        "|---|---|",
        f"| status | {result.status} |",
        f"| batch_id | {result.batchId} |",
        f"| run_id | {result.runId} |",
        "",
        "## Runtime",
        "",
        "| item | value |",
        "|---|---|",
        "| mode | hydropilot-test |",
        "| parallel | 1 |",
        "| keepInstances | true |",
        f"| run path | {result.runPath} |",
        f"| project copy | {result.projectCopy} |",
        f"| archive | {result.archivePath} |",
        f"| command | {_format_value(result.cfg.basic.command)} |",
        f"| timeout | {result.cfg.basic.timeout} |",
        "",
        "## Inputs",
        "",
        "### Design Parameters",
        "",
        "| name | value |",
        "|---|---:|",
    ]
    lines.extend(_param_rows(result.xLabels, result.X))
    lines.extend([
        "",
        "### Physical Parameters",
        "",
        "| name | value |",
        "|---|---:|",
    ])
    lines.extend(_param_rows(result.pLabels, result.P))
    lines.extend([
        "",
        "## Results",
        "",
        "### Objectives",
        "",
    ])
    lines.extend(_scalar_table([item.id for item in result.cfg.objectives.items], result.objs))
    lines.extend([
        "",
        "### Constraints",
        "",
    ])
    lines.extend(_scalar_table([item.id for item in result.cfg.constraints.items], result.cons))
    lines.extend([
        "",
        "### Diagnostics",
        "",
    ])
    lines.extend(_scalar_table([item.id for item in result.cfg.diagnostics.items], result.diags))
    lines.extend([
        "",
        "## Series Check",
        "",
        "| id | sim length | nan count |",
        "|---|---:|---:|",
    ])
    if result.series:
        for sid, values in result.series.items():
            arr = np.asarray(values).reshape(-1)
            lines.append(f"| {sid} | {arr.size} | {int(np.isnan(arr).sum())} |")
    else:
        lines.append("| none | 0 | 0 |")
    lines.extend([
        "",
        "## Errors And Warnings",
        "",
    ])
    entries = collect_error_entries(result.context.get("error"), result.context.get("warnings", []))
    if entries:
        lines.extend(["| severity | stage | code | target | message |", "|---|---|---|---|---|"])
        for entry in entries:
            lines.append(
                "| "
                + " | ".join([
                    _escape_md(entry.get("severity", "")),
                    _escape_md(entry.get("stage", "")),
                    _escape_md(entry.get("code", "")),
                    _escape_md(entry.get("target", "")),
                    _escape_md(entry.get("message", "")),
                ])
                + " |"
            )
    else:
        lines.append("none")
    lines.extend([
        "",
        "## Files",
        "",
        "| item | path |",
        "|---|---|",
        f"| report | {path} |",
        f"| summary | {result.archivePath / 'summary.csv'} |",
        f"| test series | {result.archivePath / 'test_series.csv'} |",
        f"| test params | {result.archivePath / 'test_param.csv'} |",
        f"| errors | {result.archivePath / 'error.log'} |",
        f"| runner stdout | {result.projectCopy / 'runner.stdout.log'} |",
        f"| runner stderr | {result.projectCopy / 'runner.stderr.log'} |",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def format_terminal_summary(result) -> str:
    verdict = {
        "passed": "PASSED",
        "warning": "PASSED WITH WARNINGS",
        "failed": "FAILED",
    }.get(result.status, result.status.upper())
    lines = [
        f"HydroPilot test {verdict}",
        "",
        f"Config: {result.configPath}",
        f"Archive: {result.archivePath}",
        f"Run: batch={result.batchId} run={result.runId}",
        "",
        "Runtime:",
        "  parallel: 1",
        "  keep project copy: yes",
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
    entries = collect_error_entries(result.context.get("error"), result.context.get("warnings", []))
    if entries:
        lines.extend(["", "Errors And Warnings:"])
        for entry in entries:
            lines.append(
                f"  {entry.get('severity', '').upper()} "
                f"{entry.get('stage', '')}/{entry.get('code', '')} "
                f"{entry.get('target', '')}: {entry.get('message', '')}"
            )
    lines.extend([
        "",
        "Files:",
        f"  report: {result.reportPath}",
        f"  summary: {result.archivePath / 'summary.csv'}",
        f"  test series: {result.archivePath / 'test_series.csv'}",
        f"  test params: {result.archivePath / 'test_param.csv'}",
        f"  errors: {result.archivePath / 'error.log'}",
        f"  runner stdout: {result.projectCopy / 'runner.stdout.log'}",
        f"  runner stderr: {result.projectCopy / 'runner.stderr.log'}",
    ])
    return "\n".join(lines)


def _param_rows(labels: Iterable[str], values) -> list[str]:
    return [f"| {name} | {_format_number(value)} |" for name, value in zip(labels, np.asarray(values).ravel())]


def _scalar_table(labels: list[str], values) -> list[str]:
    if not labels:
        return ["none"]
    rows = ["| id | value |", "|---|---:|"]
    rows.extend(f"| {label} | {_format_number(value)} |" for label, value in zip(labels, np.asarray(values).ravel()))
    return rows


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


def _format_value(value) -> str:
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return str(value)


def _escape_md(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
