from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..value_ops import apply_param_mode, clamp_value
from .base import ParamWriter


@dataclass
class FormattedTextFileSpec:
    name: str
    row: int
    col: int
    width: int
    precision: int


@dataclass
class FormattedTextWriterSpec:
    name: str
    type: int
    bounds: List[float]
    file: FormattedTextFileSpec

    @property
    def lb(self) -> float:
        return float(self.bounds[0])

    @property
    def ub(self) -> float:
        return float(self.bounds[1])


@dataclass
class TextEntry:
    row: int
    col: int
    width: int
    original_val: float


@dataclass
class TextParameter:
    name: str
    index: int
    entries: List[TextEntry]
    mode: int
    typ: int
    precision: int
    width: int
    lb: Optional[float] = None
    ub: Optional[float] = None


class FormattedTextWriter(ParamWriter):
    """General-purpose formatted-text file writer.

    Two-phase lifecycle:
    1. Initialization: reads the skeleton file and records parameter positions.
       Called via ``initialize(instance_filepath)`` after the project copy is
       created.  This is where the static text skeleton is loaded.
    2. Apply: ``set_values_and_save`` backfills dynamic values into the
       recorded positions and writes the result.
    """

    @classmethod
    def validateSpec(cls, raw_spec: Dict[str, Any]) -> None:
        cls.buildSpec(raw_spec)

    @classmethod
    def buildSpec(cls, raw_spec: Dict[str, Any]) -> FormattedTextWriterSpec:
        if not isinstance(raw_spec, dict):
            raise ValueError("physical parameter must be a mapping")
        name = raw_spec.get("name")
        if not name:
            raise ValueError("Physical parameter missing 'name'")
        file_spec = raw_spec.get("file")
        if not isinstance(file_spec, dict):
            raise ValueError(
                f"Physical parameter '{name}' missing writer-specific file spec"
            )
        file_name = file_spec.get("name")
        if not file_name:
            raise ValueError("missing formatted_text file name")
        row = file_spec.get("row")
        if row is None:
            raise ValueError("missing formatted_text field 'row'")
        if int(row) <= 0:
            raise ValueError("formatted_text row must be a positive 1-based integer")
        col = file_spec.get("col")
        if col is None:
            raise ValueError("missing formatted_text field 'col'")
        if int(col) <= 0:
            raise ValueError("formatted_text col must be a positive 1-based integer")
        width = file_spec.get("width")
        if width is None:
            raise ValueError("missing formatted_text field 'width'")
        if int(width) <= 0:
            raise ValueError("formatted_text width must be a positive integer")
        precision = file_spec.get("precision")
        if precision is None:
            raise ValueError("missing formatted_text field 'precision'")
        if int(precision) < 0:
            raise ValueError("formatted_text precision must be a non-negative integer")
        return FormattedTextWriterSpec(
            name=str(name),
            type=int(raw_spec.get("type", 0))
            if isinstance(raw_spec.get("type"), int)
            else {"float": 0, "int": 1, "discrete": 2}.get(
                raw_spec.get("type", "float"), 0
            ),
            bounds=raw_spec.get("bounds", [0, 1]),
            file=FormattedTextFileSpec(
                name=str(file_name),
                row=int(row),
                col=int(col),
                width=int(width),
                precision=int(precision),
            ),
        )

    def __init__(self, filepath: str):
        self.filepath = str(filepath)
        self._skeleton_lines: List[str] = []
        self.params: Dict[int, TextParameter] = {}

    # -- skeleton helpers ---------------------------------------------------

    def _ensure_skeleton(self) -> None:
        """Load the static text skeleton from *self.filepath* if not already loaded."""
        if not self._skeleton_lines:
            with open(self.filepath, "r", encoding="utf-8") as f:
                self._skeleton_lines = f.read().splitlines(keepends=True)

    def _clear_skeleton(self) -> None:
        self._skeleton_lines = []

    # -- ParamWriter interface -----------------------------------------------

    def initialize(self, output_filepath: str) -> None:
        """Reload the static skeleton from the instance-copy file.

        After an instance copy is created this must be called once so that
        subsequent ``set_values_and_save`` calls operate on the current
        skeleton rather than the original project file.
        """
        self.filepath = str(output_filepath)
        self._clear_skeleton()
        self._ensure_skeleton()

    def register_param(
        self, spec, lib_info, hard_bound: bool = True
    ) -> bool:
        if not isinstance(lib_info, FormattedTextWriterSpec):
            lib_info = self.buildSpec({
                "name": lib_info.name,
                "type": lib_info.type,
                "bounds": lib_info.bounds,
                "file": {
                    "name": lib_info.file.name,
                    "row": lib_info.file.row,
                    "col": lib_info.file.col,
                    "width": lib_info.file.width,
                    "precision": lib_info.file.precision,
                },
            })

        self._ensure_skeleton()

        row_1b = lib_info.file.row
        row_idx = row_1b - 1
        if row_idx < 0 or row_idx >= len(self._skeleton_lines):
            raise ValueError(
                f"Row {row_1b} out of range for file "
                f"'{Path(self.filepath).name}' "
                f"({len(self._skeleton_lines)} rows)"
            )

        line_str = self._skeleton_lines[row_idx]
        col_1b = lib_info.file.col
        col_idx = col_1b - 1
        end_idx = col_idx + lib_info.file.width

        if col_idx >= len(line_str):
            raise ValueError(
                f"Column {col_1b} out of range "
                f"on row {row_1b} of '{Path(self.filepath).name}'"
            )

        field_str = line_str[col_idx:end_idx].rstrip("\n").rstrip("\r")
        try:
            original_val = float(field_str.strip())
        except ValueError:
            raise ValueError(
                f"Cannot parse float from "
                f"'{Path(self.filepath).name}' "
                f"row {row_1b} columns {col_1b}-{col_1b + lib_info.file.width - 1}: "
                f"'{field_str.strip()}'"
            ) from None

        if spec.index in self.params:
            raise ValueError(
                f"Duplicate parameter index in file "
                f"'{Path(self.filepath).name}': {spec.index}"
            )

        lb = lib_info.lb if hard_bound else None
        ub = lib_info.ub if hard_bound else None
        if lib_info.type == 1:
            if lb is not None:
                lb = int(lb)
            if ub is not None:
                ub = int(ub)

        self.params[spec.index] = TextParameter(
            name=spec.name,
            index=spec.index,
            entries=[
                TextEntry(
                    row=row_1b,
                    col=col_1b,
                    width=lib_info.file.width,
                    original_val=original_val,
                )
            ],
            mode=spec.modeCode,
            typ=lib_info.type,
            precision=lib_info.file.precision,
            width=lib_info.file.width,
            lb=lb,
            ub=ub,
        )
        return True

    def set_values_and_save(
        self,
        output_filepath: str,
        indices: List[int],
        vals: List[float],
    ) -> Dict[str, List[dict]]:
        lines = list(self._skeleton_lines)
        clamp_events: List[dict] = []
        write_records: List[dict] = []

        for idx, input_val in zip(indices, vals):
            p = self.params.get(idx)
            if not p:
                continue

            for entry in p.entries:
                raw_value = apply_param_mode(
                    entry.original_val, input_val, mode=p.mode, typ=p.typ
                )
                clamped, was_clamped = clamp_value(
                    raw_value, lb=p.lb, ub=p.ub
                )

                if was_clamped:
                    clamp_events.append({
                        "file": Path(output_filepath).name,
                        "param": p.name,
                        "idx": idx,
                        "raw": raw_value,
                        "clamped": clamped,
                        "lb": p.lb,
                        "ub": p.ub,
                    })

                formatted = self._format_value(
                    clamped, p.width, p.precision, p.typ
                )

                row_idx = entry.row - 1
                col_idx = entry.col - 1
                line_str = lines[row_idx]
                lines[row_idx] = (
                    line_str[:col_idx]
                    + formatted
                    + line_str[col_idx + entry.width :]
                )

                write_records.append({
                    "file": Path(output_filepath).name,
                    "param": p.name,
                    "old_value": entry.original_val,
                    "new_value": clamped,
                    "locator": f"row={entry.row};col={entry.col};width={entry.width}",
                })

        with open(output_filepath, "w", encoding="utf-8") as f:
            f.writelines(lines)

        return {
            "clamp_events": clamp_events,
            "write_records": write_records,
        }

    @staticmethod
    def _format_value(
        val: float, width: int, precision: int, typ: int
    ) -> str:
        if typ == 1:
            s = str(int(val))
        else:
            s = f"{float(val):.{precision}f}"

        if len(s) > width:
            return "*" * width

        return s.rjust(width)
