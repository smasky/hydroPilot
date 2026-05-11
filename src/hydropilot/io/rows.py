from typing import Any, Dict, List

from ..config.schema.base import expand_row_ranges


def build_row_selection(
    raw_spec: Dict[str, Any],
    *,
    missing_message: str,
    positive_message: str = "row selection must use positive 1-based row numbers",
) -> List[int]:
    row_ranges_source = raw_spec.get("rowRanges", [])
    if row_ranges_source and not isinstance(row_ranges_source, list):
        raise ValueError(f"rowRanges must be a list, got: {row_ranges_source}")

    row_ranges: List[List[int]] = []
    for item in row_ranges_source:
        if not isinstance(item, list) or len(item) not in (2, 3):
            raise ValueError(f"rowRanges item must be [start, end] or [start, end, step], got: {item}")
        row_ranges.append([int(x) for x in item])

    expanded_rows = expand_row_ranges(row_ranges) if row_ranges else []
    row_list_source = raw_spec.get("rowList", [])
    if row_list_source and (not isinstance(row_list_source, list) or not all(isinstance(x, int) for x in row_list_source)):
        raise ValueError(f"rowList must be a list of integers, got: {row_list_source}")

    rows = sorted(set(expanded_rows + [int(x) for x in row_list_source]))
    if not rows:
        raise ValueError(missing_message)
    if rows[0] <= 0:
        raise ValueError(positive_message)
    return rows


def shift_row_selection(raw_spec: Dict[str, Any], *, offset: int) -> Dict[str, Any]:
    shifted: Dict[str, Any] = {}
    if "rowRanges" in raw_spec:
        shiftedRanges = []
        for item in raw_spec["rowRanges"]:
            if len(item) == 2:
                shiftedRanges.append([int(item[0]) + offset, int(item[1]) + offset])
            elif len(item) == 3:
                shiftedRanges.append([int(item[0]) + offset, int(item[1]) + offset, int(item[2])])
            else:
                raise ValueError(f"rowRanges item must be [start, end] or [start, end, step], got: {item}")
        shifted["rowRanges"] = shiftedRanges
    if "rowList" in raw_spec:
        shifted["rowList"] = [int(row) + offset for row in raw_spec["rowList"]]
    return shifted
