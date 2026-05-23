from typing import Any, Dict, List, Optional

from ..common.params import build_design_items, resolve_physical_params
from .discovery import FILTERABLE_HRU_FIELDS

# calibration.cal record layout — column positions for the VAL field
#   NAME(12) CHG_TYPE(15) VAL(16) CONDS(8) LYR1(8) LYR2(8) YEAR1(8) YEAR2(8) DAY1(8) DAY2(8) OBJ_TOT(8)
#   VAL starts at column 30 after NAME + 1 space + CHG_TYPE + 1 space.
_CAL_VAL_COL = 30
_CAL_VAL_WIDTH = 16
_CAL_VAL_PRECISION = 6

# mode → CHG_TYPE mapping
_MODE_TO_CHG_TYPE = {"v": "absval", "a": "abschg", "r": "pctchg"}

# Original files whose parameters are per-HRU and eligible for filter→object-ID
# expansion via hru_meta.
#   hydrology.hyd — per-HRU hydrologic params
#   soils.sol     — per-soil params; FORTRAN confirms ob_typ=sol uses HRU IDs
#                   (cal_parmchg_read.f90: case("sol")→sp_ob%hru).
#                   soil-name filter resolves to HRU IDs via hru_meta.soil
#                   (exact match, no hydro-suffix expansion in this path).
# Basin-level files (parameters.bsn) are excluded.
_HRU_SCOPED_ORIGIN_FILES = {"hydrology.hyd", "soils.sol"}

# Files whose parameters support object_id passthrough (direct IDs in
# the calibration record tail).  Attribute-based filter keys are rejected
# by validation — only object_id is accepted.
_OBJECT_ID_SCOPED_FILES = {"hyd-sed-lte.cha"}


def buildSwatPlusParams(
    rawParams: Dict[str, Any],
    meta: Dict[str, Any],
    paramDb: Dict[str, Any],
    writerType: str = "formatted_text",
) -> Dict[str, Any]:
    design = rawParams.get("design")
    if not design:
        raise ValueError("parameters.design is required")

    physical = rawParams.get("physical")
    transformer = rawParams.get("transformer")
    resolvedPhysical = resolve_physical_params(
        design, physical, transformer, paramDb, modelName="SWAT+"
    )
    hru_meta = meta.get("hru_meta", {})
    n_reaches = meta.get("n_reaches", 0)
    physicalItems = _build_calibration_entries(resolvedPhysical, hru_meta, n_reaches, writerType)
    designItems = build_design_items(design, paramDb, modelName="SWAT+")

    result: Dict[str, Any] = {
        "design": designItems,
        "physical": physicalItems,
        "hardBound": rawParams.get("hardBound", True),
    }
    if transformer:
        result["transformer"] = transformer
    return result


def build_calibration_skeleton(physicalParams: List[Dict[str, Any]]) -> str:
    """Build the calibration.cal skeleton text from *resolved* physical entries.

    Must be called with the same list that drives
    ``_build_calibration_entries`` so that row count, row order, parameter
    names, and CHG_TYPE values are all consistent with the write-plan rows.

    Object IDs resolved from filters are embedded in the skeleton record
    tail so that the per-run ``set_values_and_save`` only writes the VAL
    column — object targeting is static through the session.
    """
    n = len(physicalParams)
    lines: List[str] = []

    # header
    lines.append("Number of parameters:")
    lines.append(str(n))
    lines.append("")
    lines.append(
        "NAME        CHG_TYPE             VAL    CONDS    LYR1    LYR2"
        "   YEAR1   YEAR2    DAY1    DAY2OBJ_TOT"
    )

    # parameter records — one row per resolved physical entry
    for pp in physicalParams:
        record = _format_cal_record(pp)
        lines.append(record)

    lines.append("")  # trailing newline
    return "\n".join(lines)


def _format_cal_record(pp: Dict[str, Any]) -> str:
    """Format a single calibration.cal record line from a resolved entry."""
    param_name = pp.get("name", "?")
    mode = pp.get("mode", "v")
    chg_type = _MODE_TO_CHG_TYPE.get(mode, "absval")
    obj_ids = pp.get("_resolved_ids", [])
    obj_tot = len(obj_ids)

    record = (
        f"{param_name:<12} "
        f"{chg_type:<15} "
        f"{0.0:>{_CAL_VAL_WIDTH}.{_CAL_VAL_PRECISION}f}"
        f"{0:>9d}"    # CONDS
        f"{0:>8d}"    # LYR1
        f"{0:>8d}"    # LYR2
        f"{0:>8d}"    # YEAR1
        f"{0:>9d}"    # YEAR2
        f"{0:>8d}"    # DAY1
        f"{0:>8d}"    # DAY2
        f"{obj_tot:>8d}"  # OBJ_TOT
    )
    if obj_tot > 0:
        obj_tail = "".join(f"{oid:>8d}" for oid in obj_ids)
        record += obj_tail
    return record


def _resolve_object_ids(
    filterSpec: Optional[Dict[str, Any]],
    hru_meta: Dict[int, Dict[str, str]],
) -> List[int]:
    """Resolve a filter spec into a sorted list of HRU object IDs.

    Supported filter keys:
      - ``object_id`` — explicit ID list, returned directly.
      - ``lu_mgt``, ``soil``, ``hydro_name`` — matched against
        ``hru_meta`` attributes.  Single value or list (OR within key),
        multiple keys combined with AND.

    Returns an empty list when *filterSpec* is None or has no recognised
    filterable keys.
    """
    if not filterSpec:
        return []

    # explicit object IDs take priority
    raw_ids = filterSpec.get("object_id")
    if raw_ids is not None:
        if isinstance(raw_ids, list):
            return sorted(int(i) for i in raw_ids)
        return [int(raw_ids)]

    # resolve HRU-attribute filters against project metadata
    matched_ids: Optional[set] = None
    for field in FILTERABLE_HRU_FIELDS:
        expected = filterSpec.get(field)
        if expected is None:
            continue
        expected_set = set(str(v) for v in expected) if isinstance(expected, list) else {str(expected)}
        field_ids = {
            hru_id for hru_id, attrs in hru_meta.items()
            if str(attrs.get(field, "")) in expected_set
        }
        if matched_ids is None:
            matched_ids = field_ids
        else:
            matched_ids &= field_ids  # AND across fields

    if matched_ids is None:
        return []
    return sorted(matched_ids)


def _resolve_cha_ids(
    filterSpec: Optional[Dict[str, Any]],
    n_reaches: int = 0,
) -> List[int]:
    """Resolve object_id filter for channel (hyd-sed-lte.cha) parameters.

    Only ``object_id`` is accepted — attribute-based filters are rejected
    by validation before reaching the builder.  IDs are validated against
    the project's reach count (n_reaches from channel-lte.cha).
    """
    if not filterSpec:
        return []

    raw_ids = filterSpec.get("object_id")
    if raw_ids is None:
        return []
    ids = sorted(int(i) for i in raw_ids) if isinstance(raw_ids, list) else [int(raw_ids)]

    if n_reaches > 0:
        for oid in ids:
            if oid < 1 or oid > n_reaches:
                raise ValueError(
                    f"channel object_id {oid} is out of range "
                    f"[1..{n_reaches}] (from channel-lte.cha)"
                )
    return ids


def _build_calibration_entries(
    physicalParams: List[Dict[str, Any]],
    hru_meta: Dict[int, Dict[str, str]],
    n_reaches: int,
    writerType: str,
) -> List[Dict[str, Any]]:
    """Build formatted_text physical entries targeting calibration.cal.

    Each resolved physical entry maps to one record row.  The VAL column
    is the runtime write target.  Filters are resolved to object IDs and
    embedded in the skeleton tail — they do not change the VAL position.
    """
    items: List[Dict[str, Any]] = []
    for i, pp in enumerate(physicalParams):
        row = 5 + i  # 4 header lines → first record starts at row 5
        mode = pp.get("mode", "v")

        fileSpec: Dict[str, Any] = {
            "name": "calibration.cal",
            "row": row,
            "col": _CAL_VAL_COL,
            "width": _CAL_VAL_WIDTH,
            "precision": _CAL_VAL_PRECISION,
        }

        origin_file = pp.get("location", {}).get("name", "")
        if origin_file in _HRU_SCOPED_ORIGIN_FILES:
            obj_ids = _resolve_object_ids(pp.get("filter"), hru_meta)
        elif origin_file in _OBJECT_ID_SCOPED_FILES:
            obj_ids = _resolve_cha_ids(pp.get("filter"), n_reaches)
        else:
            obj_ids = []  # basin params do not get object targeting

        item: Dict[str, Any] = {
            "name": pp["name"],
            "type": pp.get("type", "float"),
            "mode": mode,
            "writerType": writerType,
            "file": fileSpec,
            "_resolved_ids": obj_ids,
        }
        if pp.get("bounds"):
            item["bounds"] = pp["bounds"]
        if pp.get("filter"):
            item["filter"] = pp["filter"]
        items.append(item)
    return items
