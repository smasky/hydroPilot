from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .base import ParamWriter


@dataclass
class FixedWidthFileSpec:
    name: str
    line: Union[int, List[int]]
    start: int
    width: int
    precision: int
    maxNum: int
    selectIndex: Optional[int] = None


@dataclass
class FixedWidthWriterSpec:
    name: str
    type: int
    bounds: List[float]
    file: FixedWidthFileSpec

    @property
    def lb(self) -> float:
        return float(self.bounds[0])

    @property
    def ub(self) -> float:
        return float(self.bounds[1])


@dataclass
class SubEntry:
    offset: int
    original_val: float
    line: int
    start: int


@dataclass
class Parameter:
    name: str
    index: int
    entries: List[SubEntry]
    mode: int
    typ: int
    precision: int
    width: int
    lb: Optional[float] = None
    ub: Optional[float] = None
    selectIndex: Optional[int] = None


@dataclass
class Modification:
    offset: int
    width: int
    data: bytes


def _expand_row_ranges(row_ranges: List[List[int]]) -> List[int]:
    out: List[int] = []
    for rr in row_ranges:
        if len(rr) == 2:
            a, b = rr
            step = 1
        elif len(rr) == 3:
            a, b, step = rr
        else:
            raise ValueError(f"Invalid row range: {rr}")
        out.extend(range(int(a), int(b) + 1, int(step)))
    out.sort()
    return out


class FixedWidthWriter(ParamWriter):
    @classmethod
    def validateSpec(cls, raw_spec: Dict[str, Any]) -> None:
        cls.buildSpec(raw_spec)

    @classmethod
    def buildSpec(cls, raw_spec: Dict[str, Any]) -> FixedWidthWriterSpec:
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
        raw_line = file_spec.get("line")
        if raw_line is None:
            raise ValueError("missing fixed_width field 'line'")
        if isinstance(raw_line, list) and raw_line and isinstance(raw_line[0], list):
            parsed_line = _expand_row_ranges(raw_line)
        else:
            parsed_line = raw_line
        start = file_spec.get("start")
        if start is None:
            raise ValueError("missing fixed_width field 'start'")
        width = file_spec.get("width")
        if width is None:
            raise ValueError("missing fixed_width field 'width'")
        precision = file_spec.get("precision")
        if precision is None:
            raise ValueError("missing fixed_width field 'precision'")
        max_num = int(file_spec.get("maxNum", 1))
        raw_select_index = file_spec.get("selectIndex")
        select_index = int(raw_select_index) if raw_select_index is not None else None
        if int(start) <= 0:
            raise ValueError("fixed_width start must be a positive integer")
        if int(width) <= 0:
            raise ValueError("fixed_width width must be a positive integer")
        if int(precision) < 0:
            raise ValueError("fixed_width precision must be a non-negative integer")
        if max_num < 1:
            raise ValueError("fixed_width maxNum must be >= 1")
        if select_index is not None and select_index < 1:
            raise ValueError("fixed_width selectIndex must be >= 1")
        if select_index is not None and select_index > max_num:
            raise ValueError("fixed_width selectIndex must be <= maxNum")
        return FixedWidthWriterSpec(
            name=name,
            type=int(raw_spec.get("type", 0)) if isinstance(raw_spec.get("type"), int) else {"float": 0, "int": 1, "discrete": 2}.get(raw_spec.get("type", "float"), 0),
            bounds=raw_spec.get("bounds", [0, 1]),
            file=FixedWidthFileSpec(
                name=file_name if isinstance(file_name, str) else file_name[0],
                line=parsed_line,
                start=int(start),
                width=int(width),
                precision=int(precision),
                maxNum=max_num,
                selectIndex=select_index,
            ),
        )

    def __init__(self, filepath: str):
        self.filepath = str(filepath)

        with open(self.filepath, "rb") as f:
            content = bytearray(f.read())

        self.base_content = content
        self.file_content = bytearray(content)

        self.line_offsets = self._build_line_index()
        self.params: Dict[int, Parameter] = {}

    def _build_line_index(self) -> List[int]:
        offs = [0]
        pos = 0
        n = len(self.base_content)
        data = self.base_content

        while True:
            j = data.find(b"\n", pos)
            if j == -1:
                break
            if j + 1 < n:
                offs.append(j + 1)
            pos = j + 1

        return offs

    @staticmethod
    def _format_value(val: float, width: int, precision: int, typ: int) -> bytes:
        if typ == 1:
            s = str(int(val))
        else:
            s = f"{float(val):.{precision}f}"

        if len(s) > width:
            return b"*" * width

        return s.rjust(width).encode("ascii")

    @staticmethod
    def _parse_float_field(b: bytes) -> Optional[float]:
        s = b.decode("ascii", errors="ignore").strip()
        if not s:
            return None

        try:
            return float(s)
        except ValueError:
            return None

    def register_param(self, spec, lib_info, hard_bound: bool = True) -> bool:
        if not isinstance(lib_info, FixedWidthWriterSpec):
            lib_info = self.buildSpec({
                "name": lib_info.name,
                "type": lib_info.type,
                "bounds": lib_info.bounds,
                "file": {
                    "name": lib_info.file.name,
                    "line": lib_info.file.line,
                    "start": lib_info.file.start,
                    "width": lib_info.file.width,
                    "precision": lib_info.file.precision,
                    "maxNum": lib_info.file.maxNum,
                    "selectIndex": lib_info.file.selectIndex,
                },
            })
        name = spec.name
        index = spec.index
        mode = spec.mode

        typ = lib_info.type
        staPos = lib_info.file.start
        width = lib_info.file.width
        precision = lib_info.file.precision
        lb = lib_info.lb if hard_bound else None
        ub = lib_info.ub if hard_bound else None
        maxNum = lib_info.file.maxNum
        selectIndex = lib_info.file.selectIndex

        if index in self.params:
            raise ValueError(
                f"Duplicate parameter index registered in file '{Path(self.filepath).name}': {index}"
            )

        if typ == 1:
            if lb is not None:
                lb = int(lb)
            if ub is not None:
                ub = int(ub)

        linePos_data = lib_info.file.line
        lines = linePos_data if isinstance(linePos_data, list) else [linePos_data]

        entries_list: List[SubEntry] = []

        for linePos in lines:
            line_idx = linePos - 1
            if line_idx < 0:
                continue

            if line_idx >= len(self.line_offsets):
                continue

            line_start = self.line_offsets[line_idx]

            if line_idx + 1 < len(self.line_offsets):
                line_end = self.line_offsets[line_idx + 1]
            else:
                line_end = len(self.base_content)

            base_offset = line_start + (staPos - 1)

            row_entries = self._scan_entries(
                start_offset=base_offset,
                width=width,
                max_num=maxNum,
                line_end_offset=line_end,
                line=linePos,
                start=staPos,
            )

            entries_list.extend(row_entries)

        if selectIndex is not None:
            entries_list = [
                entry
                for entry_index, entry in enumerate(entries_list, start=1)
                if entry_index == selectIndex
            ]

        if not entries_list:
            if selectIndex is not None:
                return False
            raise ValueError(
                f"No writable entries found for parameter '{name}' "
                f"in file '{Path(self.filepath).name}'. "
                f"Check line/start/width/maxNum settings."
            )

        self.params[index] = Parameter(
            name=name,
            index=index,
            entries=entries_list,
            mode=mode,
            typ=typ,
            precision=precision,
            width=width,
            lb=lb,
            ub=ub,
            selectIndex=selectIndex,
        )

        return True

    def set_values_and_save(
        self,
        output_filepath: str,
        indices: List[int],
        vals: List[float],
    ) -> List[dict]:
        self.file_content = bytearray(self.base_content)
        mods: List[Modification] = []
        clamp_events: List[dict] = []
        write_records: List[dict] = []

        for idx, input_val in zip(indices, vals):
            p = self.params.get(idx)
            if not p:
                continue

            for entry_index, e in enumerate(p.entries, start=1):
                if p.mode == 0:
                    raw = e.original_val * (1.0 + float(input_val))
                elif p.mode == 1:
                    raw = float(input_val)
                elif p.mode == 2:
                    raw = e.original_val + float(input_val)
                else:
                    raw = float(input_val)

                raw2 = int(raw) if p.typ == 1 else raw

                clamped = raw2
                if p.lb is not None and clamped < p.lb:
                    clamped = p.lb
                if p.ub is not None and clamped > p.ub:
                    clamped = p.ub

                if clamped != raw2:
                    clamp_events.append({
                        "file": Path(output_filepath).name,
                        "param": p.name,
                        "idx": idx,
                        "raw": raw2,
                        "clamped": clamped,
                        "lb": p.lb,
                        "ub": p.ub,
                    })

                b = self._format_value(clamped, p.width, p.precision, p.typ)
                mods.append(Modification(offset=e.offset, width=p.width, data=b))
                write_records.append({
                    "file": Path(output_filepath).name,
                    "param": p.name if p.selectIndex is not None or len(p.entries) == 1 else f"{p.name}_{entry_index}",
                    "old_value": e.original_val,
                    "new_value": clamped,
                    "locator": f"line={e.line};start={e.start};width={p.width}",
                })

        for m in mods:
            self.file_content[m.offset: m.offset + m.width] = m.data

        with open(output_filepath, "wb") as out:
            out.write(self.file_content)

        return {
            "clamp_events": clamp_events,
            "write_records": write_records,
        }

    def _scan_entries(
        self,
        start_offset: int,
        width: int,
        max_num: int,
        line_end_offset: int,
        line: int,
        start: int,
    ) -> List[SubEntry]:
        entries: List[SubEntry] = []

        for i in range(max_num):
            curr_off = start_offset + (i * width)
            curr_end = curr_off + width
            if curr_end > line_end_offset:
                break

            raw = bytes(self.base_content[curr_off:curr_end])
            val = self._parse_float_field(raw)
            if val is None:
                break

            entries.append(SubEntry(offset=curr_off, original_val=val, line=line, start=start + (i * width)))

        return entries
