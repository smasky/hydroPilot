"""SWAT+ project discovery — minimal MVP parser for TxtInOut directories.

Parses a subset of the SWAT+ project files needed by the template layer.
Currently reads: file.cio, time.sim, print.prt, hru-data.hru (count + attributes),
soils.sol (profile names, NLY, HYD_GRP, ordering).
Not yet parsed: connectivity (hru.con, rout_unit.con), weather data, or management schedules.
"""

import re
from pathlib import Path
from typing import Any, Dict, List


_INTERVAL_MAP = {0: "monthly", 1: "daily", 2: "yearly"}

# Columns in hru-data.hru that can serve as filter dimensions.
# These are the user-facing field names used in parameters.physical[].filter.
# This is the *single source of truth* for supported filter fields.
# builder.py and validate.py import from here — do not duplicate.
FILTERABLE_HRU_FIELDS = ("lu_mgt", "soil", "hydro_name")


def discover_swatplus_project(project_path: Path) -> Dict[str, Any]:
    project_path = Path(project_path)
    cio_path = project_path / "file.cio"
    if not cio_path.exists():
        raise FileNotFoundError(f"SWAT+ file.cio not found: {cio_path}")

    cio_entries = _parse_file_cio(cio_path)

    time_info = _parse_time_sim(project_path / cio_entries.get("time.sim", "time.sim"))
    print_info = _parse_print_prt(project_path / cio_entries.get("print.prt", "print.prt"))

    timestep = _INTERVAL_MAP.get(print_info["interval"], "daily")
    nyskip = print_info["nyskip"]
    output_start_year = time_info["start_year"] + nyskip

    hru_file = project_path / cio_entries.get("hru-data.hru", "hru-data.hru")
    n_hrus, hru_meta = _parse_hru_attributes(hru_file)

    cha_file = project_path / "channel-lte.cha"
    n_reaches, _cha_meta = _parse_channel_attributes(cha_file)

    sol_file = project_path / "soils.sol"
    n_soils, soil_profiles = _parse_soils_sol(sol_file)
    soil_profile_map = build_soil_profile_map(hru_meta, soil_profiles)

    return {
        "start_year": time_info["start_year"],
        "end_year": time_info["end_year"],
        "timestep": timestep,
        "nyskip": nyskip,
        "output_start_year": output_start_year,
        "output_end_year": time_info["end_year"],
        "n_hrus": n_hrus,
        "hru_meta": hru_meta,
        "n_reaches": n_reaches,
        "n_soils": n_soils,
        "soil_profiles": soil_profiles,
        "soil_profile_map": soil_profile_map,
    }


# ---------------------------------------------------------------------------
# HRU attribute parsing (Phase 2 filter)
# ---------------------------------------------------------------------------

def _parse_hru_attributes(file_path: Path) -> tuple:
    """Parse hru-data.hru, returning (n_hrus, hru_meta).

    hru_meta maps ``hru_id (int) -> {lu_mgt, soil, hydro_name}`` where
    each value is the trimmed string from the corresponding column.

    The file has a 2-line header (title + column names) followed by data rows.
    Data rows are space-delimited with columns:
    id, name, topo, hydro, soil, lu_mgt, soil_plant_init, surf_stor, snow, field
    """
    if not file_path.exists():
        return 0, {}

    hru_meta: Dict[int, Dict[str, str]] = {}
    n_hrus = 0

    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    # Skip 2-line header
    for line in lines[2:]:
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split()
        if len(parts) < 6:
            continue
        try:
            hru_id = int(parts[0])
        except ValueError:
            continue
        n_hrus += 1
        hru_meta[hru_id] = {
            "lu_mgt": parts[5] if len(parts) > 5 else "",
            "soil": parts[4] if len(parts) > 4 else "",
            "hydro_name": parts[3] if len(parts) > 3 else "",
        }

    return n_hrus, hru_meta


# ---------------------------------------------------------------------------
# file.cio
# ---------------------------------------------------------------------------

def _parse_file_cio(cio_path: Path) -> Dict[str, str]:
    """Parse SWAT+ file.cio, returning ``{category: first_non_null_filename}``.

    SWAT+ file.cio uses one keyword-per-line format. Each line starts with a
    category name (e.g. ``climate``, ``hru``) followed by whitespace-separated
    filenames. Unused slots contain ``null``. We only keep the first non-null
    entry per category.
    """
    entries: Dict[str, str] = {}
    with open(cio_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("file.cio:"):
                continue
            parts = line.split()
            if not parts:
                continue
            category = parts[0]
            for part in parts[1:]:
                if part != "null":
                    entries[category] = part
                    break
    return entries


# ---------------------------------------------------------------------------
# Numeric table helpers
# ---------------------------------------------------------------------------

def _first_numeric_row(file_path: Path, expected_cols: int) -> list[int]:
    """Return the first data row (all-int tokens) from a SWAT+ table file.

    Skips the ``filename:`` title line and the column-header line by ignoring
    any line whose tokens cannot all be parsed as integers.
    """
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            tokens = stripped.split()
            try:
                values = [int(t) for t in tokens]
            except ValueError:
                continue
            if len(values) >= expected_cols:
                return values
    raise ValueError(f"No numeric data row found in {file_path}")


def _count_data_rows(file_path: Path) -> int:
    """Count data rows in a SWAT+ table file by skipping header lines.

    A "header line" is any line whose first token is non-numeric (column
    names, title line, or section labels like ``aa_int_cnt``).
    """
    if not file_path.exists():
        return 0
    count = 0
    past_header = False
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            if not past_header:
                first_token = stripped.split()[0]
                try:
                    int(first_token)
                    past_header = True
                except ValueError:
                    continue
            if past_header:
                count += 1
    return count


# ---------------------------------------------------------------------------
# channel-lte.cha parsing
# ---------------------------------------------------------------------------

def _parse_channel_attributes(file_path: Path) -> tuple:
    """Parse channel-lte.cha, returning (n_reaches, reach_meta).

    reach_meta maps ``reach_id (int) -> {name}``.  The file has columns:
    id, name, cha_ini, cha_hyd, cha_sed, cha_nut.  Row 1 is a tool metadata
    line, row 2 is column headers — skip both.
    """
    if not file_path.exists():
        return 0, {}

    reach_meta: Dict[int, Dict[str, str]] = {}
    n_reaches = 0

    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    for line in lines[2:]:
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split()
        if len(parts) < 2:
            continue
        try:
            reach_id = int(parts[0])
        except ValueError:
            continue
        n_reaches += 1
        reach_meta[reach_id] = {
            "name": parts[1] if len(parts) > 1 else "",
        }

    return n_reaches, reach_meta


# ---------------------------------------------------------------------------
# soils.sol parsing
# ---------------------------------------------------------------------------

def _parse_soils_sol(file_path: Path) -> tuple:
    """Parse soils.sol, returning (n_soils, soil_profiles).

    soil_profiles maps ``profile_index (1-based int) -> {name, nly, hyd_grp}``.
    Profile rows are identified by the first token being a non-numeric name
    (not a depth value).  Layer rows begin with a numeric depth value.
    """
    if not file_path.exists():
        return 0, {}

    soil_profiles: Dict[int, Dict[str, Any]] = {}
    n_soils = 0

    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    for line in lines[2:]:
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split()
        if len(parts) < 3:
            continue
        first = parts[0]
        try:
            float(first)
            continue  # layer row — depth value is numeric
        except ValueError:
            pass
        n_soils += 1
        soil_profiles[n_soils] = {
            "name": first,
            "nly": int(parts[1]) if len(parts) > 1 else 1,
            "hyd_grp": parts[2] if len(parts) > 2 else "",
        }

    return n_soils, soil_profiles


def build_soil_profile_map(
    hru_meta: Dict[int, Dict[str, str]],
    soil_profiles: Dict[int, Dict[str, Any]],
) -> Dict[int, int]:
    """Map each HRU's soil value to a soils.sol profile index.

    Returns ``{hru_id -> profile_index}`` where profile_index is 1-based.

    Hydro-suffix handling: ``soil_01-h1`` → strip ``-h1`` → match ``soil_01``.
    Both exact-match and suffix-stripped matching are tried; the first match
    wins.  HRUs whose soil value cannot be matched to any profile are omitted
    from the result.
    """
    if not soil_profiles:
        return {}

    # build a lookup set for fast matching
    profile_by_name: Dict[str, int] = {}
    for idx, info in soil_profiles.items():
        profile_by_name[info["name"]] = idx

    result: Dict[int, int] = {}
    for hru_id, attrs in hru_meta.items():
        soil_val = attrs.get("soil", "")
        if not soil_val:
            continue
        # try exact match first
        if soil_val in profile_by_name:
            result[hru_id] = profile_by_name[soil_val]
            continue
        # strip hydro-suffix: everything after the last "-" that looks like
        # a hydro variant marker (e.g. "-h1", "-h3")
        m = re.match(r"^(.+)-[a-z]+\d+$", soil_val)
        if m:
            base = m.group(1)
            if base in profile_by_name:
                result[hru_id] = profile_by_name[base]
    return result


# ---------------------------------------------------------------------------
# time.sim / print.prt
# ---------------------------------------------------------------------------

def _parse_time_sim(time_path: Path) -> Dict[str, Any]:
    """Parse SWAT+ time.sim for simulation start/end years and step.

    Columns: day_start  yrc_start  day_end  yrc_end  step
    (step 0=daily, 1=sub-daily).
    """
    if not time_path.exists():
        raise FileNotFoundError(f"SWAT+ time.sim not found: {time_path}")
    values = _first_numeric_row(time_path, 5)
    return {
        "start_year": values[1],
        "end_year": values[3],
        "step": values[4],
    }


def _parse_print_prt(prt_path: Path) -> Dict[str, Any]:
    """Parse SWAT+ print.prt for output interval and nyskip.

    Columns: nyskip  day_start  yrc_start  day_end  yrc_end  interval
    (interval 0=monthly, 1=daily, 2=yearly).
    """
    if not prt_path.exists():
        raise FileNotFoundError(f"SWAT+ print.prt not found: {prt_path}")
    values = _first_numeric_row(prt_path, 6)
    return {
        "nyskip": values[0],
        "interval": values[5],
    }
