from typing import Any, Dict, List, Optional

from ..common.params import build_design_items, resolve_physical_params


def _toList(value: Any) -> list:
    if isinstance(value, list):
        return value
    return [value]


def expandLocations(
    physicalParams: List[Dict[str, Any]],
    meta: Dict[str, Any],
    writerType: str,
) -> List[Dict[str, Any]]:
    physicalItems = []
    for pp in physicalParams:
        loc = pp["location"]
        rowList = _resolveRows(meta, pp.get("filter"))
        fileName = loc.get("name", meta["parameterFile"])
        if fileName == "parameters.csv":
            fileName = meta["parameterFile"]

        fileSpec = {
            "name": fileName,
            "rowList": _toGeneralRows(rowList, int(loc.get("headSkip", 1))),
            "colNum": int(loc["colNum"]),
            "delimiter": loc.get("delimiter", ","),
        }
        if "precision" in loc:
            fileSpec["precision"] = int(loc["precision"])

        item = {
            "name": pp["name"],
            "type": pp["type"],
            "mode": pp["mode"],
            "writerType": writerType,
            "file": fileSpec,
        }
        if pp.get("bounds") is not None:
            item["bounds"] = pp["bounds"]
        physicalItems.append(item)
    return physicalItems


def buildXajParams(
    rawParams: Dict[str, Any],
    meta: Dict[str, Any],
    paramDb: Dict[str, Any],
    writerType: str = "csv",
) -> Dict[str, Any]:
    design = rawParams.get("design")
    if not design:
        raise ValueError("parameters.design is required")

    physical = rawParams.get("physical")
    transformer = rawParams.get("transformer")
    resolvedPhysical = resolve_physical_params(design, physical, transformer, paramDb, modelName="XAJ")
    physicalItems = expandLocations(resolvedPhysical, meta, writerType)
    designItems = build_design_items(design, paramDb, modelName="XAJ")

    result = {
        "design": designItems,
        "physical": physicalItems,
        "hardBound": rawParams.get("hardBound", True),
    }
    if transformer:
        result["transformer"] = transformer
    return result


def _resolveRows(meta: Dict[str, Any], filterSpec: Optional[Dict[str, Any]]) -> List[int]:
    if not filterSpec:
        return list(meta["allDataRows"])
    unsupported = set(filterSpec.keys()) - {"rivid"}
    if unsupported:
        raise ValueError(f"Unsupported XAJ parameter filter fields: {sorted(unsupported)}")
    if "rivid" not in filterSpec:
        return list(meta["allDataRows"])

    rows = []
    for rivid in _toList(filterSpec["rivid"]):
        key = str(rivid)
        if key not in meta["rividRows"]:
            raise ValueError(f"XAJ RIVID not found in parameter file: {key}")
        rows.append(meta["rividRows"][key])
    return rows


def _toGeneralRows(rows: List[int], headSkip: int) -> List[int]:
    return [headSkip + row for row in rows]
