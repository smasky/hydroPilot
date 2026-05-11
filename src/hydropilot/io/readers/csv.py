import csv
import os
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
from pydantic import BaseModel

from ...config.paths import resolve_existing_file
from ..rows import build_row_selection
from .base import SeriesReader


class CsvReaderSpec(BaseModel):
    file: Path
    headSkip: int = 0
    rows: List[int]
    colNum: int
    delimiter: str = ","
    size: int
    readerType: str = "csv"


class CsvReader(SeriesReader):
    """Reads one numeric column from CSV using 1-based data rows and columns."""

    def __init__(self, encoding: str = "utf-8-sig"):
        self.encoding = encoding

    @classmethod
    def validateSpec(cls, raw_spec: Dict[str, Any], *, base_path: Path, check_file: bool) -> None:
        cls.buildSpec(raw_spec, base_path=base_path, check_file=check_file)

    @classmethod
    def buildSpec(cls, raw_spec: Dict[str, Any], *, base_path: Path, check_file: bool) -> CsvReaderSpec:
        if raw_spec is None:
            raise ValueError("missing csv extract spec")

        file_name = raw_spec.get("file")
        if file_name is None:
            raise ValueError("missing file path for csv extract")

        col_num = raw_spec.get("colNum")
        if col_num is None:
            raise ValueError("missing csv field 'colNum'")
        if int(col_num) <= 0:
            raise ValueError("csv colNum must be a positive 1-based integer")

        head_skip = int(raw_spec.get("headSkip", 0))
        if head_skip < 0:
            raise ValueError("csv headSkip must be a non-negative integer")

        delimiter = str(raw_spec.get("delimiter", ","))
        if len(delimiter) != 1:
            raise ValueError("csv delimiter must be a single character")

        if check_file:
            resolved_file = resolve_existing_file(file_name, base_path, "extract.file")
        else:
            resolved_file = Path(file_name)

        rows = build_row_selection(
            raw_spec,
            missing_message="missing row selection, expected rowRanges or rowList",
            positive_message="csv row selection must use positive 1-based row numbers",
        )
        return CsvReaderSpec.model_validate({
            "file": resolved_file,
            "headSkip": head_skip,
            "rows": rows,
            "colNum": int(col_num),
            "delimiter": delimiter,
            "size": len(rows),
            "readerType": str(raw_spec.get("readerType", "csv")),
        })

    def read(self, dir_path, spec: CsvReaderSpec) -> np.ndarray:
        if dir_path is None:
            path = Path(spec.file)
        else:
            path = Path(os.path.join(dir_path, spec.file))

        values: List[float] = []
        target_rows = set(spec.rows)
        max_row = max(target_rows)

        with path.open("r", encoding=self.encoding, newline="") as f:
            reader = csv.reader(f, delimiter=spec.delimiter)
            for _ in range(spec.headSkip):
                next(reader, None)

            for data_row_num, row in enumerate(reader, start=1):
                if data_row_num > max_row:
                    break
                if data_row_num not in target_rows:
                    continue

                col_idx = spec.colNum - 1
                if col_idx >= len(row):
                    raise ValueError(f"csv row {data_row_num} has no column {spec.colNum}")
                raw_value = row[col_idx].strip()
                if raw_value == "":
                    raise ValueError(f"csv value is empty at row {data_row_num}, column {spec.colNum}")
                try:
                    values.append(float(raw_value))
                except ValueError as exc:
                    raise ValueError(f"csv value is not numeric at row {data_row_num}, column {spec.colNum}: {raw_value}") from exc

        if len(values) != len(spec.rows):
            raise ValueError(f"csv file ended before all selected rows were read; expected {len(spec.rows)}, got {len(values)}")
        return np.asarray(values)
