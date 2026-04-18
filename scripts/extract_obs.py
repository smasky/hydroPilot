"""Extract obs flow data from output.rch for testing.

Reads FLOW_OUT (colSpan [50,61]) for subbasin 33, period 2010-2015 daily,
and writes to obs_flow.txt in the work directory.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pathlib import Path
from hydro_pilot.templates.swat.discovery import discover_swat_project
from hydro_pilot.templates.swat.variables import calcSwatOutputRows
from hydro_pilot.config.specs import expand_row_ranges

PROJECT_PATH = Path(r"E:\DJBasin\TxtInOutFSB")
OUTPUT_FILE = PROJECT_PATH / "output.rch"
OBS_OUTPUT = Path(r"E:\modelDriver\examples") / "obs_flow.txt"

SUBBASIN = 33
PERIOD = [2010, 2015]
TIMESTEP = "daily"
COL_SPAN = (50, 61)  # FLOW_OUTcms, 1-based inclusive


def main():
    print("Discovering SWAT project...")
    meta = discover_swat_project(PROJECT_PATH)
    print(f"  n_subbasins: {meta['n_subbasins']}")
    print(f"  output_start_year: {meta['output_start_year']}")
    print(f"  output_end_year: {meta['output_end_year']}")
    print(f"  timestep: {meta['timestep']}")

    print(f"\nCalculating row ranges for subbasin {SUBBASIN}, period {PERIOD}...")
    result = calcSwatOutputRows(
        meta=meta,
        outputType="rch",
        subbasin=SUBBASIN,
        period=PERIOD,
        timestep=TIMESTEP,
    )
    rowRanges = result["rowRanges"]
    size = result["size"]
    print(f"  rowRanges: {rowRanges[:3]}... ({len(rowRanges)} ranges)")
    print(f"  size: {size}")

    # Expand row ranges to individual row numbers
    rows = expand_row_ranges(rowRanges)
    print(f"  expanded rows: {len(rows)}")

    # Read output.rch and extract FLOW_OUT values
    print(f"\nReading {OUTPUT_FILE}...")
    values = []
    with open(OUTPUT_FILE, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    print(f"  total lines in file: {len(lines)}")

    for row_num in rows:
        if row_num < 1 or row_num > len(lines):
            print(f"  WARNING: row {row_num} out of range")
            values.append(0.0)
            continue
        line = lines[row_num - 1]  # 1-based to 0-based
        # Extract fixed-width column (1-based inclusive)
        col_start = COL_SPAN[0] - 1  # to 0-based
        col_end = COL_SPAN[1]        # exclusive end for slicing
        field = line[col_start:col_end].strip()
        try:
            values.append(float(field))
        except ValueError:
            print(f"  WARNING: cannot parse '{field}' at row {row_num}")
            values.append(0.0)

    print(f"\nExtracted {len(values)} values")
    print(f"  first 5: {values[:5]}")
    print(f"  last 5: {values[-5:]}")
    print(f"  min: {min(values):.6f}, max: {max(values):.6f}")

    # Write obs file: one value per line
    OBS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OBS_OUTPUT, "w", encoding="utf-8") as f:
        for v in values:
            f.write(f"{v:.6E}\n")

    print(f"\nObs file written to: {OBS_OUTPUT}")
    print(f"  {len(values)} lines")


if __name__ == "__main__":
    main()
