"""SWAT template builder — filter, resolve, expand logic.

Converts simplified user config (design/physical/transformer)
into design + physical parameter lists for downstream consumption.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from ..common.params import build_design_items, resolve_physical_params


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class HruMatch:
    """A single HRU that passed filter criteria."""
    subbasinId: int
    hruId: int
    files: Dict[str, str]  # {"hru": "000010001.hru", "mgt": "000010001.mgt", ...}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _toList(value: Any) -> list:
    """Normalize a scalar or list to a list."""
    if isinstance(value, list):
        return value
    return [value]


def _isGlobalFile(filePattern: str) -> bool:
    """Check if a file pattern refers to a global (non-HRU) file."""
    return not filePattern.startswith("*.")


def _matchesNot(subId: int, hru: Dict[str, Any], notSpec: Dict[str, Any]) -> bool:
    """Return True if the HRU matches the NOT exclusion block."""
    if not notSpec:
        return False
    if "subbasin" in notSpec:
        if subId in _toList(notSpec["subbasin"]):
            return True
    if "land_use" in notSpec:
        if hru["land_use"] in _toList(notSpec["land_use"]):
            return True
    if "soil" in notSpec:
        if hru["soil"] in _toList(notSpec["soil"]):
            return True
    if "slope" in notSpec:
        if str(hru["slope"]) in [str(s) for s in _toList(notSpec["slope"])]:
            return True
    return False


# ---------------------------------------------------------------------------
# 3.2  Filter engine
# ---------------------------------------------------------------------------

def filterHrus(meta: Dict[str, Any], filterSpec: Optional[Dict[str, Any]]) -> List[HruMatch]:
    """Filter HRUs from meta based on filter criteria.

    Rules:
    - Same field, multiple values → OR  (subbasin: [1,3,5])
    - Different fields → AND  (land_use: FRST + slope: "30-45")
    - "not" block → exclude matching HRUs
    - No filter → return all HRUs
    """
    subbasins = meta.get("subbasins", {})

    if not filterSpec:
        results = []
        for subId, sub in subbasins.items():
            for hruId, hru in sub["hrus"].items():
                results.append(HruMatch(subId, hruId, hru["files"]))
        return results

    results = []
    notSpec = filterSpec.get("not", {})

    for subId, sub in subbasins.items():
        # Subbasin-level filter
        if "subbasin" in filterSpec:
            allowed = _toList(filterSpec["subbasin"])
            if subId not in allowed:
                continue

        for hruId, hru in sub["hrus"].items():
            # Land use filter (OR within field)
            if "land_use" in filterSpec:
                allowed = _toList(filterSpec["land_use"])
                if hru["land_use"] not in allowed:
                    continue

            # Soil filter
            if "soil" in filterSpec:
                allowed = _toList(filterSpec["soil"])
                if hru["soil"] not in allowed:
                    continue

            # Slope filter
            if "slope" in filterSpec:
                allowed = [str(s) for s in _toList(filterSpec["slope"])]
                if str(hru["slope"]) not in allowed:
                    continue

            # NOT exclusion
            if _matchesNot(subId, hru, notSpec):
                continue

            results.append(HruMatch(subId, hruId, hru["files"]))

    return results


def resolveFileTargets(hruMatches: List[HruMatch], filePattern: str) -> List[str]:
    """Extract concrete filenames from HRU matches for a given pattern.

    For "*.mgt" → collect the "mgt" entry from each HruMatch.files.
    For global files like "basins.bsn" → return as-is (no HRU expansion).
    """
    if _isGlobalFile(filePattern):
        return [filePattern]

    ext = filePattern.lstrip("*.")
    seen = set()
    result = []
    for m in hruMatches:
        fname = m.files.get(ext)
        if fname and fname not in seen:
            seen.add(fname)
            result.append(fname)
    return result


# ---------------------------------------------------------------------------
# 3.3  Location expansion
# ---------------------------------------------------------------------------

def expandLocations(
    physicalParams: List[Dict[str, Any]],
    meta: Dict[str, Any],
    writerType: str,
) -> List[Dict[str, Any]]:
    """Expand physical params into concrete physical entries.

    - With filter: expand HRU files via filterHrus → concrete filename list.
    - Without filter: keep original glob/regex pattern for ParamWritePlan to resolve.
    - Global files (no "*." prefix): always keep as-is.
    """
    physicalItems = []

    for pp in physicalParams:
        filePattern = pp["location"]["name"]
        hasFilter = pp["filter"] is not None

        if hasFilter and not _isGlobalFile(filePattern):
            # Filter mode: expand to concrete file list
            hruMatches = filterHrus(meta, pp["filter"])
            fileList = resolveFileTargets(hruMatches, filePattern)
            targetFiles = fileList if len(fileList) != 1 else fileList[0]
        else:
            # No filter or global file: keep pattern for ParamWritePlan
            targetFiles = filePattern

        loc = pp["location"]
        physicalItems.append({
            "name": pp["name"],
            "type": pp["type"],
            "bounds": pp["bounds"],
            "mode": pp["mode"],
            "writerType": pp.get("writerType", writerType),
            "file": {
                "name": targetFiles,
                "line": loc["line"],
                "start": loc["start"],
                "width": loc["width"],
                "precision": loc["precision"],
                "maxNum": loc.get("maxNum", 1),
            },
        })

    return physicalItems


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def buildSwatParams(
    rawParams: Dict[str, Any],
    meta: Dict[str, Any],
    paramDb: Dict[str, Any],
    workPath: Path,
    writerType: str = "fixed_width",
) -> Dict[str, Any]:
    """Build design + physical parameter lists from user config.

    Args:
        rawParams: The "parameters" block from user YAML (design/physical/transformer).
        meta: Metadata from discover().
        paramDb: SWAT parameter database dict.
        workPath: Directory (unused now, kept for API compatibility).

    Returns:
        Dict with "design", "physical", "hardBound", and optionally "transformer".
    """
    design = rawParams.get("design")
    if not design:
        raise ValueError("parameters.design is required")

    physical = rawParams.get("physical")
    transformer = rawParams.get("transformer")

    # Step 1: Resolve physical params (fill defaults from SWAT parameter database)
    resolvedPhysical = resolve_physical_params(design, physical, transformer, paramDb, modelName="SWAT")

    # Step 2: Expand locations (physical × matched files → physical entries)
    physicalItems = expandLocations(resolvedPhysical, meta, writerType)

    # Step 3: Build design items from the original design list
    designItems = build_design_items(design, paramDb, modelName="SWAT")

    result = {
        "design": designItems,
        "physical": physicalItems,
        "hardBound": rawParams.get("hardBound", True),
    }
    if transformer:
        result["transformer"] = transformer
    return result
