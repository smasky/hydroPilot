import copy
from typing import Any, Dict, List, Optional

from .library import SWATPLUS_SERIES_SOURCES, lookupSeriesFile, lookupSeriesVariable


SWATPLUS_OUTPUT_OBJECTS = ("basin", "hru", "hru-lte", "lsunit", "ru",
                           "channel", "aquifer", "reservoir", "hyd", "region")


def buildSwatPlusSeries(
    rawSeries: List[Dict[str, Any]],
    meta: Dict[str, Any],
    readerType: str = "text",
) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for item in rawSeries:
        expanded = copy.deepcopy(item)
        sim = expanded.get("sim")
        if isinstance(sim, dict) and "call" not in sim:
            _resolveSwatPlusExtract(expanded, sim, meta, readerType)
        obs = expanded.get("obs")
        if isinstance(obs, dict) and "call" not in obs:
            obs.setdefault("readerType", readerType)
        result.append(expanded)
    return result


def _resolveSwatPlusExtract(
    series: Dict[str, Any],
    sim: Dict[str, Any],
    meta: Dict[str, Any],
    readerType: str,
) -> None:
    """Resolve a SWAT+ sim block — modelled on SWAT 2012's _resolveSwatExtract."""
    sim.setdefault("readerType", readerType)

    simFile = sim.get("file", "")
    outputType = inferSwatPlusObjectType(simFile)

    _resolveSwatPlusColumn(series, sim, outputType)

    if outputType is not None and _needsRowResolution(sim):
        objectId = sim.pop("id", None)
        period = sim.pop("period", None)
        if objectId is not None:
            result = calcSwatPlusOutputRows(
                meta=meta,
                outputFile=sim.get("file", simFile),
                objectType=outputType,
                id=int(objectId),
                period=period,
            )
            sim["rowRanges"] = result["rowRanges"]


def _resolveSwatPlusColumn(
    series: Dict[str, Any],
    sim: Dict[str, Any],
    outputType: Optional[str],
) -> None:
    """Resolve ``variable`` → colSpan / colNum, matching SWAT 2012's _resolveSwatColumn."""
    if "colSpan" in sim or "colNum" in sim:
        return

    variableName = sim.pop("variable", None)
    if variableName is None:
        return

    simFile = sim.get("file", "")

    # Scope lookup to the declared file when both file and variable are present
    # (matches SWAT 2012's file + variable pair semantics).
    fileFilter = simFile if simFile else None
    variable = lookupSeriesVariable(str(variableName), fileFilter=fileFilter)
    if variable is None:
        seriesId = series.get("id", "<unknown>")
        msg = (
            f"Series '{seriesId}' variable '{variableName}' "
            f"is not a known SWAT+ output variable."
        )
        if simFile:
            msg += f" It was not found in output file '{simFile}'."
        msg += " Check swatplus_db.yaml for known variables."
        raise ValueError(msg)

    sim.setdefault("file", variable["file"])
    if "colSpan" in variable:
        sim["colSpan"] = variable["colSpan"]
    elif "colNum" in variable:
        sim["colNum"] = variable["colNum"]


def _needsRowResolution(sim: Dict[str, Any]) -> bool:
    return "rowRanges" not in sim and "rowList" not in sim


def calcSwatPlusOutputRows(
    meta: Dict[str, Any],
    outputFile: str = "",
    objectType: str = "hru",
    id: int = 1,
    period: Optional[list] = None,
) -> Dict[str, Any]:
    """Calculate rowRanges and size for a SWAT+ output file.

    Args:
        meta: Metadata from discover().
        outputFile: Output file name (used to infer frequency and header_lines).
        objectType: Object type inferred from file prefix (basin, hru, ru, ...).
        id: Spatial object ID (1-based).
        period: Time period (year-based list, multi-segment supported).

    Returns:
        Dict with ``rowRanges`` and ``size`` keys.
    """
    source = lookupSeriesFile(outputFile)

    headerLines = 1
    frequency = "aa"
    if source is not None:
        headerLines = int(source.get("header_lines", 1))
        frequency = source.get("frequency", "aa")
    else:
        frequency = _detectFrequency(outputFile)

    rowsPerYear = _rowsPerFrequency(frequency)
    nUnits = _objectCount(meta, objectType)
    if nUnits == 0:
        raise ValueError(
            f"SWAT+ object type '{objectType}' has count 0 in this project "
            f"(output file: '{outputFile}')."
        )
    if id < 1 or id > nUnits:
        raise ValueError(
            f"id {id} out of range [1, {nUnits}] for SWAT+ {objectType} output."
        )

    outputStartYear = meta.get("output_start_year", meta.get("start_year", 0))
    outputEndYear = meta.get("output_end_year", meta.get("end_year", 0))

    if period is None:
        segments = [(outputStartYear, outputEndYear)]
    else:
        segments = _parsePeriodYearSegments(period)

    step = nUnits
    rowRanges: List[List[int]] = []
    size = 0

    for segStartYear, segEndYear in segments:
        segStartYear = max(segStartYear, outputStartYear)
        segEndYear = min(segEndYear, outputEndYear)
        if segStartYear > segEndYear:
            continue

        for year in range(segStartYear, segEndYear + 1):
            yearIndex = year - outputStartYear
            first = headerLines + yearIndex * rowsPerYear * nUnits + id
            last = first + (rowsPerYear - 1) * step
            rowRanges.append([first, last, step])
            size += rowsPerYear

    if not rowRanges:
        raise ValueError(
            f"Period {period} produces no rows within output window "
            f"[{outputStartYear}, {outputEndYear}]."
        )

    return {"rowRanges": rowRanges, "size": size}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def inferSwatPlusObjectType(fileName: str) -> Optional[str]:
    """Infer SWAT+ object type from output file name prefix.

    Returns ``None`` when the file does not match any known SWAT+ output prefix,
    which causes row resolution to be skipped (same as SWAT 2012's
    ``inferSwatOutputType`` returning None for non-standard files).
    """
    if not fileName:
        return None
    for prefix in SWATPLUS_OUTPUT_OBJECTS:
        if fileName.startswith(prefix + "_"):
            return prefix
    return None


def _detectFrequency(fileName: str) -> str:
    if fileName.endswith("_aa.txt"):
        return "aa"
    if fileName.endswith("_yr.txt"):
        return "yr"
    if fileName.endswith("_mon.txt"):
        return "mo"
    if fileName.endswith("_day.txt"):
        return "da"
    if fileName.endswith("_mo.txt"):
        return "mo"
    if fileName.endswith("_da.txt"):
        return "da"
    return "aa"


def _rowsPerFrequency(freq: str) -> int:
    return {"aa": 1, "yr": 1, "mo": 12, "da": 365, "mon": 12, "day": 365}.get(freq, 1)


def _objectCount(meta: Dict[str, Any], objType: str) -> int:
    fieldMap = {"hru": "n_hrus", "hru-lte": "n_hrus",
                "ru": "n_rtu", "lsunit": "n_lsunits"}
    field = fieldMap.get(objType, f"n_{objType}s")
    count = meta.get(field, 0)
    if count == 0 and objType in ("basin", "hyd", "region"):
        count = 1
    return int(count)


def _parsePeriodYearSegments(period) -> List[tuple]:
    if not isinstance(period, list):
        raise ValueError(f"period must be a list, got: {type(period).__name__}")

    def _edgeYear(edge) -> int:
        return int(str(edge).split("-")[0])

    if not period:
        raise ValueError("period is empty")

    if isinstance(period[0], list):
        segments = []
        for seg in period:
            if len(seg) < 2:
                raise ValueError(f"period segment must have 2 elements, got: {seg}")
            segments.append((_edgeYear(seg[0]), _edgeYear(seg[1])))
        return segments

    if len(period) >= 2:
        return [(_edgeYear(period[0]), _edgeYear(period[1]))]

    raise ValueError(f"Cannot parse SWAT+ period: {period}")
