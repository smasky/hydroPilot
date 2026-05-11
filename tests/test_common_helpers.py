from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from hydropilot.io.rows import build_row_selection, shift_row_selection
from hydropilot.io.value_ops import apply_param_mode, clamp_value


def test_build_row_selection_merges_ranges_and_list_as_positive_sorted_rows():
    rows = build_row_selection(
        {
            "rowRanges": [[3, 5], [10, 14, 2]],
            "rowList": [1, 4],
        },
        missing_message="missing row selection",
    )

    assert rows == [1, 3, 4, 5, 10, 12, 14]


def test_build_row_selection_rejects_missing_and_non_positive_rows():
    with pytest.raises(ValueError, match="missing row selection"):
        build_row_selection({}, missing_message="missing row selection")

    with pytest.raises(ValueError, match="positive 1-based"):
        build_row_selection({"rowList": [0]}, missing_message="missing row selection")


def test_shift_row_selection_moves_ranges_and_lists_without_changing_step():
    shifted = shift_row_selection(
        {
            "rowRanges": [[1, 3], [10, 20, 5]],
            "rowList": [2, 7],
        },
        offset=1,
    )

    assert shifted == {
        "rowRanges": [[2, 4], [11, 21, 5]],
        "rowList": [3, 8],
    }


def test_param_value_ops_apply_modes_types_and_clamps():
    assert apply_param_mode(10.0, 0.2, mode=0, typ=0) == 12.0
    assert apply_param_mode(10.0, 3.7, mode=1, typ=1) == 3
    assert apply_param_mode(10.0, -2.0, mode=2, typ=0) == 8.0

    assert clamp_value(12.0, lb=0.0, ub=10.0) == (10.0, True)
    assert clamp_value(-1.0, lb=0.0, ub=10.0) == (0.0, True)
    assert clamp_value(5.0, lb=0.0, ub=10.0) == (5.0, False)
