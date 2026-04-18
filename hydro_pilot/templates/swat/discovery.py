import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

# IPRINT value to timestep string mapping
IPRINT_MAP = {0: "monthly", 1: "daily", 2: "yearly"}


def discover_swat_project(project_path: Path) -> Dict[str, Any]:
    """Read SWAT project files to extract metadata.

    Parses:
    - file.cio: simulation period, timestep, output settings
    - fig.fig: subbasin count and IDs
    - *.sub: subbasin area, latitude, elevation, HRU count and file list
    - *.hru header: land_use, soil, slope per HRU

    Returns:
        Dict with time info, subbasin/HRU structure, and output settings.
    """
    meta: Dict[str, Any] = {}

    # 1. Parse file.cio
    cio_path = project_path / "file.cio"
    if not cio_path.exists():
        raise FileNotFoundError(f"file.cio not found in {project_path}")
    meta.update(_parse_file_cio(cio_path))

    # 2. Parse fig.fig
    fig_path = project_path / "fig.fig"
    if not fig_path.exists():
        raise FileNotFoundError(f"fig.fig not found in {project_path}")
    subbasin_ids, sub_files = _parse_fig_fig(fig_path)
    meta["n_subbasins"] = len(subbasin_ids)

    # 3. Parse each .sub and its HRUs
    subbasins: Dict[int, Dict[str, Any]] = {}
    for sub_id, sub_file in zip(subbasin_ids, sub_files):
        sub_path = project_path / sub_file.strip()
        if not sub_path.exists():
            continue
        sub_info = _parse_sub_file(sub_path)
        # Parse HRU headers
        hrus: Dict[int, Dict[str, Any]] = {}
        for hru_idx, hru_files in enumerate(sub_info.get("hru_file_list", []), start=1):
            hru_file = hru_files.get("hru")
            if hru_file:
                hru_path = project_path / hru_file
                if hru_path.exists():
                    hru_info = _parse_hru_header(hru_path)
                    hru_info["files"] = hru_files
                    hrus[hru_idx] = hru_info
        sub_info.pop("hru_file_list", None)
        sub_info["hrus"] = hrus
        sub_info["n_hrus"] = len(hrus)
        subbasins[sub_id] = sub_info

    meta["subbasins"] = subbasins
    return meta


def _read_lines(path: Path) -> List[str]:
    """Read file lines with encoding fallback (utf-8 → latin-1)."""
    for enc in ("utf-8", "latin-1"):
        try:
            with path.open("r", encoding=enc) as f:
                return f.readlines()
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError(f"Cannot decode file: {path}")


def _parse_file_cio(cio_path: Path) -> Dict[str, Any]:
    """Parse file.cio to extract simulation settings.

    Key fields by line number (1-based):
    - Line 8:  NBYR (number of years)
    - Line 9:  IYR (start year)
    - Line 10: IDAF (start julian day)
    - Line 11: IDAL (end julian day)
    - Line 59: IPRINT (output frequency)
    - Line 60: NYSKIP (years to skip output)
    - Line 85: ICALEN (date format in output)
    """
    lines = _read_lines(cio_path)

    def _int_val(line_num: int) -> int:
        """Extract integer value from left side of '|' delimiter."""
        line = lines[line_num - 1]
        val_part = line.split("|")[0].strip()
        return int(float(val_part))

    nbyr = _int_val(8)
    iyr = _int_val(9)
    idaf = _int_val(10)
    idal = _int_val(11)
    iprint = _int_val(59)
    nyskip = _int_val(60)
    icalen = _int_val(85)

    end_year = iyr + nbyr - 1
    timestep = IPRINT_MAP.get(iprint, "unknown")
    output_start_year = iyr + nyskip
    output_years = nbyr - nyskip

    return {
        "n_years": nbyr,
        "start_year": iyr,
        "end_year": end_year,
        "start_jday": idaf,
        "end_jday": idal,
        "iprint": iprint,
        "timestep": timestep,
        "nyskip": nyskip,
        "icalen": icalen,
        "output_start_year": output_start_year,
        "output_end_year": end_year,
        "output_years": output_years,
    }


def _parse_fig_fig(fig_path: Path) -> Tuple[List[int], List[str]]:
    """Parse fig.fig to extract subbasin IDs and .sub file names.

    Format: each subbasin is 2 lines:
        subbasin       1     1     1       Subbasin: 1
                  000010000.sub
    """
    lines = _read_lines(fig_path)

    subbasin_ids: List[int] = []
    sub_files: List[str] = []

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("subbasin"):
            # Extract subbasin ID: 3rd numeric field
            parts = line.split()
            sub_id = int(parts[3])
            subbasin_ids.append(sub_id)
            # Next line has the .sub filename
            if i + 1 < len(lines):
                sub_files.append(lines[i + 1].strip())
            i += 2
        else:
            i += 1

    return subbasin_ids, sub_files


def _parse_sub_file(sub_path: Path) -> Dict[str, Any]:
    """Parse a .sub file to extract subbasin info and HRU file list.

    Extracts via '|' label matching:
    - SUB_KM: subbasin area (km2)
    - LATITUDE: latitude (degrees)
    - ELEV: elevation (m)
    - HRUTOT: total HRU count

    HRU file list is after "HRU: General" line, each line contains
    concatenated filenames like:
        000010001.hru000010001.mgt000010001.sol000010001.chm 000010001.gw ...
    """
    lines = _read_lines(sub_path)

    info: Dict[str, Any] = {}

    for line in lines:
        if "|" not in line:
            continue
        val_part, label_part = line.split("|", 1)
        label = label_part.strip()

        if label.startswith("SUB_KM"):
            info["area_km2"] = float(val_part.strip())
        elif label.startswith("LATITUDE"):
            info["latitude"] = float(val_part.strip())
        elif label.startswith("ELEV :") or label.startswith("ELEV:"):
            info["elevation"] = float(val_part.strip())
        elif label.startswith("HRUTOT"):
            info["n_hrus"] = int(float(val_part.strip()))

    # Parse HRU file list after "HRU: General"
    hru_file_list: List[Dict[str, str]] = []
    in_hru_section = False
    for line in lines:
        stripped = line.strip()
        if "HRU: General" in stripped:
            in_hru_section = True
            continue
        if in_hru_section and stripped:
            files = _split_hru_filenames(stripped)
            if files:
                hru_file_list.append(files)

    info["hru_file_list"] = hru_file_list
    return info


def _split_hru_filenames(line: str) -> Dict[str, str]:
    """Split a concatenated HRU filename line into individual files.

    Input example:
        000010001.hru000010001.mgt000010001.sol000010001.chm 000010001.gw  000010001.sep

    Returns dict keyed by extension: {"hru": "000010001.hru", "mgt": "000010001.mgt", ...}
    """
    # Match patterns like 000010001.hru (9 digits + dot + 2-3 letter extension)
    pattern = re.compile(r"(\d{9}\.[a-zA-Z]{2,3})")
    matches = pattern.findall(line)
    result: Dict[str, str] = {}
    for filename in matches:
        ext = filename.rsplit(".", 1)[-1]
        result[ext] = filename
    return result


def _parse_hru_header(hru_path: Path) -> Dict[str, Any]:
    """Parse the first line of a .hru file to extract land_use, soil, slope.

    Header format:
        .hru file Watershed HRU:1 Subbasin:1 HRU:1 Luse:BARL Soil: Haplic Acrisols Slope: 30-45 ...
    """
    lines = _read_lines(hru_path)
    header = lines[0] if lines else ""

    info: Dict[str, Any] = {}

    # Extract Luse
    luse_match = re.search(r"Luse:(\S+)", header)
    if luse_match:
        info["land_use"] = luse_match.group(1)

    # Extract Soil (may contain spaces, ends before "Slope:")
    soil_match = re.search(r"Soil:\s*(.+?)\s+Slope:", header)
    if soil_match:
        info["soil"] = soil_match.group(1).strip()

    # Extract Slope
    slope_match = re.search(r"Slope:\s*(\S+)", header)
    if slope_match:
        info["slope"] = slope_match.group(1)

    return info
