from typing import List, Tuple

from pydantic import BaseModel, ConfigDict


class ConfigNode(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
        arbitrary_types_allowed=True,
    )

    def get_env_dep_list(self) -> Tuple[List[str], List[str]]:
        return [], []


def expand_row_ranges(row_ranges: List[List[int]]) -> List[int]:
    rows: List[int] = []
    for item in row_ranges:
        if len(item) == 2:
            start, end = item
            step = 1
        elif len(item) == 3:
            start, end, step = item
        else:
            raise ValueError(f"rowRanges item must be [start, end] or [start, end, step], got: {item}")
        rows.extend(range(int(start), int(end) + 1, int(step)))
    return sorted(rows)
