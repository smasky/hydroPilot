from pathlib import Path
from typing import List, Optional, Tuple
import os

import numpy as np

from .base import SeriesReader


def parse_fixed_width(line: str, span_1based_inclusive: Tuple[int, int]) -> Optional[float]:
    a, b = span_1based_inclusive
    s = line[a-1:b].strip()
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

    def read(self, dir_path, extract_spec) -> np.ndarray:
        return read_text_extract(dir_path, extract_spec, encoding=self.encoding)


def read_text_extract(dir_path, extract, encoding: str = "utf-8"):
    """Standalone function for reading text-based extract specs.

    Kept as a module-level function for backward compatibility.
    """
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
                    return np.asarray(vals)  # EOF
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
