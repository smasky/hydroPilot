from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import os

import numpy as np
from pydantic import BaseModel

from ...config.paths import resolve_existing_file
from ...config.schema.base import expand_row_ranges
from .base import SeriesReader


class TextColumnSpec(BaseModel):
    kind: str
    span: Optional[Tuple[int, int]] = None
    col: Optional[int] = None
    delimiter: str = "whitespace"


class TextReaderSpec(BaseModel):
    file: Path
    rows: List[int]
    column: TextColumnSpec
    size: int
    readerType: str = "text"


def parse_fixed_width(line: str, span_1based_inclusive: Tuple[int, int]) -> Optional[float]:
    a, b = span_1based_inclusive
    s = line[a - 1:b].strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_col_list(line: str, cols_1based: int, delimiter: str = "whitespace") -> Optional[float]:
    parts = line.split() if delimiter == "whitespace" else line.split(delimiter)
    if not cols_1based:
        return None
    idx = cols_1based - 1
    if idx < 0 or idx >= len(parts):
        return None
    try:
        return float(parts[idx])
    except ValueError:
        return None


class TextReader(SeriesReader):
    """Reads series data from fixed-width or delimited text files."""

    def __init__(self, encoding: str = "utf-8"):
        self.encoding = encoding

    @classmethod
    def validateSpec(cls, raw_spec: Dict[str, Any], *, base_path: Path, check_file: bool) -> None:
        cls.buildSpec(raw_spec, base_path=base_path, check_file=check_file)

    @classmethod
    def buildSpec(cls, raw_spec: Dict[str, Any], *, base_path: Path, check_file: bool) -> TextReaderSpec:
        if raw_spec is None:
            raise ValueError("missing extract spec")

        file_node = raw_spec.get("file")
        file_spec = file_node if isinstance(file_node, dict) else None
        file_name = file_spec.get("name") if file_spec is not None else file_node
        if file_name is None:
            raise ValueError("missing file path for extract")

        rr_source = file_spec.get("rowRanges") if file_spec is not None and "rowRanges" in file_spec else raw_spec.get("rowRanges", [])
        if rr_source and not isinstance(rr_source, list):
            raise ValueError(f"rowRanges must be a list, got: {rr_source}")

        row_ranges: List[List[int]] = []
        for item in rr_source:
            if not isinstance(item, list) or len(item) not in (2, 3):
                raise ValueError(f"rowRanges item must be [start, end] or [start, end, step], got: {item}")
            row_ranges.append([int(x) for x in item])

        expanded_rows = expand_row_ranges(row_ranges) if row_ranges else []
        row_list_source = file_spec.get("rowList") if file_spec is not None and "rowList" in file_spec else raw_spec.get("rowList", [])
        if row_list_source and (not isinstance(row_list_source, list) or not all(isinstance(x, int) for x in row_list_source)):
            raise ValueError(f"rowList must be a list of integers, got: {row_list_source}")

        rows = sorted(set(expanded_rows + [int(x) for x in row_list_source]))
        if not rows:
            raise ValueError("missing row selection, expected rowRanges or rowList")

        if file_spec is not None and "colSpan" in file_spec:
            cs = file_spec["colSpan"]
            if not isinstance(cs, list) or len(cs) != 2:
                raise ValueError(f"colSpan must be [start, end], got: {cs}")
            column = TextColumnSpec.model_validate({"kind": "span", "span": (int(cs[0]), int(cs[1]))})
        elif file_spec is not None and "colNum" in file_spec:
            col = file_spec["colNum"]
            if not isinstance(col, int):
                raise ValueError(f"colNum must be an int, got: {col}")
            column = TextColumnSpec.model_validate({
                "kind": "col",
                "col": col,
                "delimiter": file_spec.get("delimiter", "whitespace"),
            })
        elif "colSpan" in raw_spec:
            cs = raw_spec["colSpan"]
            if not isinstance(cs, list) or len(cs) != 2:
                raise ValueError(f"colSpan must be [start, end], got: {cs}")
            column = TextColumnSpec.model_validate({"kind": "span", "span": (int(cs[0]), int(cs[1]))})
        elif "colNum" in raw_spec:
            col = raw_spec["colNum"]
            if not isinstance(col, int):
                raise ValueError(f"colNum must be an int, got: {col}")
            column = TextColumnSpec.model_validate({
                "kind": "col",
                "col": col,
                "delimiter": raw_spec.get("delimiter", "whitespace"),
            })
        else:
            raise ValueError("missing column location, expected one of colSpan or colNum|add colSpan: [start, end] or colNum: <int>")

        if check_file:
            resolved_file = resolve_existing_file(file_name, base_path, "extract.file")
        else:
            # Sim outputs belong to the runtime workdir/project copy, not the config directory.
            resolved_file = Path(file_name)

        return TextReaderSpec.model_validate({
            "file": resolved_file,
            "rows": rows,
            "column": column,
            "size": int(raw_spec.get("size", len(rows))),
            "readerType": str(raw_spec.get("readerType", raw_spec.get("reader_type", "text"))),
        })

    def read(self, dir_path, spec: TextReaderSpec) -> np.ndarray:
        return read_text_extract(dir_path, spec, encoding=self.encoding)


def read_text_extract(dir_path, extract: TextReaderSpec, encoding: str = "utf-8"):
    """Standalone function for reading text-based extract specs."""
    targets = extract.rows
    if not targets:
        return np.array([])

    if dir_path is None:
        p = Path(extract.file)
    else:
        p = Path(os.path.join(dir_path, extract.file))

    vals: List[float] = []

    with p.open("r", encoding=encoding, errors="ignore") as f:
        cur = 1
        for t in targets:
            skip = t - cur
            for _ in range(skip):
                if not f.readline():
                    return np.asarray(vals)
            line = f.readline()
            if not line:
                return np.asarray(vals)
            cur = t + 1

            col = extract.column
            if col.kind == "span":
                v = parse_fixed_width(line, col.span)
            else:
                v = parse_col_list(line, col.col or [], delimiter=col.delimiter)

            if v is not None:
                vals.append(v)

    return np.asarray(vals)
