import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..value_ops import apply_param_mode, clamp_value
from ..rows import build_row_selection
from .base import ParamWriter


@dataclass
class CsvFileSpec:
    name: str
    headSkip: int
    rows: List[int]
    colNum: int
    delimiter: str
    precision: Optional[int] = None
    selectIndex: Optional[int] = None


@dataclass
class CsvWriterSpec:
    name: str
    type: int
    bounds: List[float]
    file: CsvFileSpec

    @property
    def lb(self) -> float:
        return float(self.bounds[0])

    @property
    def ub(self) -> float:
        return float(self.bounds[1])


@dataclass
class CsvEntry:
    row: int
    col: int
    original_val: float


@dataclass
class CsvParameter:
    name: str
    index: int
    entries: List[CsvEntry]
    mode: int
    typ: int
    lb: Optional[float]
    ub: Optional[float]
    selectIndex: Optional[int]
    headSkip: int
    delimiter: str
    precision: Optional[int]


class CsvWriter(ParamWriter):
    @classmethod
    def validateSpec(cls, raw_spec: Dict[str, Any]) -> None:
        cls.buildSpec(raw_spec)

    @classmethod
    def buildSpec(cls, raw_spec: Dict[str, Any]) -> CsvWriterSpec:
        if not isinstance(raw_spec, dict):
            raise ValueError("physical parameter must be a mapping")
        name = raw_spec.get("name")
        if not name:
            raise ValueError("Physical parameter missing 'name'")
        file_spec = raw_spec.get("file")
        if not isinstance(file_spec, dict):
            raise ValueError(f"Physical parameter '{name}' missing writer-specific file spec")
        file_name = file_spec.get("name")
        if not file_name:
            raise ValueError("missing physical file name")

        col_num = file_spec.get("colNum")
        if col_num is None:
            raise ValueError("missing csv field 'colNum'")
        if int(col_num) <= 0:
            raise ValueError("csv colNum must be a positive 1-based integer")

        head_skip = int(file_spec.get("headSkip", 0))
        if head_skip < 0:
            raise ValueError("csv headSkip must be a non-negative integer")

        delimiter = str(file_spec.get("delimiter", ","))
        if len(delimiter) != 1:
            raise ValueError("csv delimiter must be a single character")

        raw_select_index = file_spec.get("selectIndex")
        select_index = int(raw_select_index) if raw_select_index is not None else None
        if select_index is not None and select_index < 1:
            raise ValueError("csv selectIndex must be >= 1")
        raw_precision = file_spec.get("precision")
        precision = int(raw_precision) if raw_precision is not None else None
        if precision is not None and precision < 0:
            raise ValueError("csv precision must be a non-negative integer")

        return CsvWriterSpec(
            name=str(name),
            type=int(raw_spec.get("type", 0)) if isinstance(raw_spec.get("type"), int) else {"float": 0, "int": 1, "discrete": 2}.get(raw_spec.get("type", "float"), 0),
            bounds=raw_spec.get("bounds", [0, 1]),
            file=CsvFileSpec(
                name=file_name if isinstance(file_name, str) else file_name[0],
                headSkip=head_skip,
                rows=build_row_selection(
                    file_spec,
                    missing_message="missing csv row selection, expected rowRanges or rowList",
                    positive_message="csv row selection must use positive 1-based row numbers",
                ),
                colNum=int(col_num),
                delimiter=delimiter,
                precision=precision,
                selectIndex=select_index,
            ),
        )

    def __init__(self, filepath: str):
        self.filepath = str(filepath)
        self.params: Dict[int, CsvParameter] = {}

    def register_param(self, spec, lib_info, hard_bound: bool = True) -> bool:
        if not isinstance(lib_info, CsvWriterSpec):
            raise ValueError("CsvWriter requires CsvWriterSpec")

        rows = self._read_rows(lib_info.file.delimiter)
        entries: List[CsvEntry] = []
        for data_row in lib_info.file.rows:
            physical_index = lib_info.file.headSkip + data_row - 1
            if physical_index < 0 or physical_index >= len(rows):
                raise ValueError(f"csv file has no selected row {data_row}")
            row = rows[physical_index]
            col_idx = lib_info.file.colNum - 1
            if col_idx >= len(row):
                raise ValueError(f"csv row {data_row} has no column {lib_info.file.colNum}")
            raw_value = row[col_idx].strip()
            if raw_value == "":
                raise ValueError(f"csv value is empty at row {data_row}, column {lib_info.file.colNum}")
            try:
                original_val = float(raw_value)
            except ValueError as exc:
                raise ValueError(f"csv value is not numeric at row {data_row}, column {lib_info.file.colNum}: {raw_value}") from exc
            entries.append(CsvEntry(row=data_row, col=lib_info.file.colNum, original_val=original_val))

        if lib_info.file.selectIndex is not None:
            entries = [
                entry
                for entry_index, entry in enumerate(entries, start=1)
                if entry_index == lib_info.file.selectIndex
            ]

        if not entries:
            return False

        lb = lib_info.lb if hard_bound else None
        ub = lib_info.ub if hard_bound else None
        if lib_info.type == 1:
            if lb is not None:
                lb = int(lb)
            if ub is not None:
                ub = int(ub)

        self.params[spec.index] = CsvParameter(
            name=spec.name,
            index=spec.index,
            entries=entries,
            mode=spec.modeCode,
            typ=lib_info.type,
            lb=lb,
            ub=ub,
            selectIndex=lib_info.file.selectIndex,
            headSkip=lib_info.file.headSkip,
            delimiter=lib_info.file.delimiter,
            precision=lib_info.file.precision,
        )
        return True

    def set_values_and_save(
        self,
        output_filepath: str,
        indices: List[int],
        vals: List[float],
    ) -> Dict[str, List[dict]]:
        delimiter = self._single_registered_delimiter()
        rows = self._read_rows(delimiter)
        clamp_events: List[dict] = []
        write_records: List[dict] = []

        for idx, input_val in zip(indices, vals):
            p = self.params.get(idx)
            if not p:
                continue

            for entry_index, entry in enumerate(p.entries, start=1):
                raw_value = apply_param_mode(entry.original_val, input_val, mode=p.mode, typ=p.typ)
                clamped, was_clamped = clamp_value(raw_value, lb=p.lb, ub=p.ub)

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

                physical_index = self._physical_row_index(p, entry.row)
                rows[physical_index][entry.col - 1] = self._format_value(clamped, p.typ, p.precision)
                write_records.append({
                    "file": Path(output_filepath).name,
                    "param": p.name if p.selectIndex is not None or len(p.entries) == 1 else f"{p.name}_{entry_index}",
                    "old_value": entry.original_val,
                    "new_value": clamped,
                    "locator": f"row={entry.row};col={entry.col}",
                })

        with open(output_filepath, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter=delimiter)
            writer.writerows(rows)

        return {
            "clamp_events": clamp_events,
            "write_records": write_records,
        }

    def _read_rows(self, delimiter: str) -> List[List[str]]:
        with open(self.filepath, "r", encoding="utf-8-sig", newline="") as f:
            return list(csv.reader(f, delimiter=delimiter))

    def _single_registered_delimiter(self) -> str:
        delimiters = {param.delimiter for param in self.params.values()}
        if len(delimiters) > 1:
            raise ValueError("csv writer cannot mix delimiters for one file")
        return next(iter(delimiters), ",")

    def _physical_row_index(self, param: CsvParameter, data_row: int) -> int:
        return param.headSkip + data_row - 1

    @staticmethod
    def _format_value(value: float, typ: int, precision: Optional[int]) -> str:
        if typ == 1:
            return str(int(value))
        if precision is not None:
            return f"{float(value):.{precision}f}"
        return str(float(value))
