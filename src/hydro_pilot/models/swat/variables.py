"""SWAT output row calculation module.

Computes rowRanges and size for SWAT output files (output.rch, output.sub,
output.hru) based on project metadata, subbasin/HRU index, and time period.
"""
import calendar
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple, Union

HEADER_LINES = 9


def _stepsInYear(year: int, timestep: str) -> int:
    """Return the number of output steps in a given year."""
    if timestep == "daily":
        return 366 if calendar.isleap(year) else 365
    elif timestep == "monthly":
        return 13  # 12 months + 1 yearly average row
    elif timestep == "yearly":
        return 1
    else:
        raise ValueError(f"Unknown timestep: {timestep}")


def _parseSinglePeriod(item: List) -> Tuple[date, date]:
    """Parse a single [start, end] period into (date, date)."""
    if len(item) != 2:
        raise ValueError(f"Period segment must have 2 elements, got: {item}")

    raw0, raw1 = item[0], item[1]

    def _parseEdge(val, isEnd: bool) -> date:
        if isinstance(val, datetime):
            return val.date()
        if isinstance(val, date):
            return val
        if isinstance(val, int):
            # Year only
            if isEnd:
                return date(val, 12, 31)
            return date(val, 1, 1)
        if isinstance(val, str):
            parts = val.split("-")
            if len(parts) == 3:
                # "YYYY-MM-DD"
                return date(int(parts[0]), int(parts[1]), int(parts[2]))
            elif len(parts) == 2:
                # "YYYY-MM"
                y, m = int(parts[0]), int(parts[1])
                if isEnd:
                    return date(y, m, calendar.monthrange(y, m)[1])
                return date(y, m, 1)
            elif len(parts) == 1:
                # "YYYY"
                y = int(parts[0])
                if isEnd:
                    return date(y, 12, 31)
                return date(y, 1, 1)
        raise ValueError(f"Cannot parse period edge: {val}")

    return (_parseEdge(raw0, False), _parseEdge(raw1, True))


def _parsePeriod(
    period: Optional[Union[List, None]],
    meta: Dict[str, Any],
) -> List[Tuple[date, date]]:
    """Parse period parameter into a list of (startDate, endDate) segments.

    Supported formats:
      None                                → full output period
      [2010, 2015]                        → single segment, year precision
      ["2010-03-01", "2015-09-30"]        → single segment, day precision
      ["2010-03", "2015-09"]              → single segment, month precision
      [[2010, 2010], [2012, 2014]]        → multi-segment
      [["2010-06","2010-09"], ...]         → multi-segment
    """
    if period is None:
        startYear = meta["output_start_year"]
        endYear = meta["output_end_year"]
        return [(date(startYear, 1, 1), date(endYear, 12, 31))]

    if not isinstance(period, list) or len(period) == 0:
        raise ValueError(f"period must be a non-empty list, got: {period}")

    # Detect multi-segment: first element is a list/tuple
    if isinstance(period[0], (list, tuple)):
        return [_parseSinglePeriod(seg) for seg in period]

    # Single segment
    return [_parseSinglePeriod(period)]


def _resolveHruIndex(
    meta: Dict[str, Any],
    subbasin: int,
    hru: int,
) -> int:
    """Convert (subbasin, local HRU index) to global HRU index (1-based)."""
    globalIndex = 0
    for subId in sorted(meta["subbasins"].keys()):
        subInfo = meta["subbasins"][subId]
        if subId == subbasin:
            if hru < 1 or hru > subInfo["n_hrus"]:
                raise ValueError(
                    f"HRU {hru} out of range for subbasin {subbasin} "
                    f"(has {subInfo['n_hrus']} HRUs)"
                )
            return globalIndex + hru
        globalIndex += subInfo["n_hrus"]
    raise ValueError(f"Subbasin {subbasin} not found in meta")


def _calcNHrusTotal(meta: Dict[str, Any]) -> int:
    """Return total number of HRUs across all subbasins."""
    return sum(sub["n_hrus"] for sub in meta["subbasins"].values())


def _mergeRowRanges(
    ranges: List[List[int]],
    step: int,
) -> List[List[int]]:
    """Merge adjacent row ranges with the same step.

    If prev.lastRow + step == next.firstRow and both have the same step,
    merge into a single [first, last, step] range.
    """
    if not ranges:
        return []

    merged: List[List[int]] = [ranges[0]]
    for r in ranges[1:]:
        prev = merged[-1]
        # prev is [first, last, step] or [row, row, 1]
        prevStep = prev[2] if len(prev) == 3 else 1
        curStep = r[2] if len(r) == 3 else 1

        if prevStep == step and curStep == step and prev[1] + step == r[0]:
            # Extend previous range
            prev[1] = r[1]
            if len(prev) == 2:
                prev.append(step)
        elif prevStep == 1 and curStep == 1 and prev[1] + step == r[0]:
            # Two single rows that form a sequence with given step
            merged[-1] = [prev[0], r[1], step]
        else:
            merged.append(r)

    return merged


def _calcRowRanges(
    meta: Dict[str, Any],
    unitIndex: int,
    nUnits: int,
    segments: List[Tuple[date, date]],
    timestep: str,
) -> Tuple[List[List[int]], int]:
    """Core row range calculation.

    Returns (rowRanges, size).
    """
    cumSteps = 0
    rawRanges: List[List[int]] = []
    size = 0

    outputStartYear = meta["output_start_year"]
    outputEndYear = meta["output_end_year"]

    for year in range(outputStartYear, outputEndYear + 1):
        stepsThisYear = _stepsInYear(year, timestep)

        for (segStart, segEnd) in segments:
            if timestep == "daily":
                yearStart = date(year, 1, 1)
                yearEnd = date(year, 12, 31)
                clipStart = max(yearStart, segStart)
                clipEnd = min(yearEnd, segEnd)
                if clipStart <= clipEnd:
                    dayOff0 = (clipStart - yearStart).days
                    dayOff1 = (clipEnd - yearStart).days
                    nDays = dayOff1 - dayOff0 + 1
                    firstRow = HEADER_LINES + (cumSteps + dayOff0) * nUnits + unitIndex
                    lastRow = HEADER_LINES + (cumSteps + dayOff1) * nUnits + unitIndex
                    rawRanges.append([firstRow, lastRow, nUnits])
                    size += nDays

            elif timestep == "monthly":
                for month in range(1, 13):  # Skip MON=13 (yearly avg)
                    monStart = date(year, month, 1)
                    monEnd = date(year, month, calendar.monthrange(year, month)[1])
                    if monStart > segEnd or monEnd < segStart:
                        continue
                    stepIdx = cumSteps + (month - 1)
                    row = HEADER_LINES + stepIdx * nUnits + unitIndex
                    rawRanges.append([row, row, nUnits])
                    size += 1

            elif timestep == "yearly":
                if segStart.year <= year <= segEnd.year:
                    row = HEADER_LINES + cumSteps * nUnits + unitIndex
                    rawRanges.append([row, row, nUnits])
                    size += 1

        cumSteps += stepsThisYear

    rowRanges = _mergeRowRanges(rawRanges, nUnits)
    return rowRanges, size


def calcSwatOutputRows(
    meta: Dict[str, Any],
    outputType: str,
    id: int,
    period: Optional[Union[List, None]] = None,
    timestep: Optional[str] = None,
) -> Dict[str, Any]:
    """Calculate rowRanges and size for a SWAT output file.

    Args:
        meta: Metadata from discover().
        outputType: "rch", "sub", or "hru".
        id: Output object ID. For rch/sub, this is subbasin ID (1-based).
            For hru, this is global HRU ID (1-based).
        period: Time period filter. See _parsePeriod for formats.
        timestep: Override meta timestep ("daily"/"monthly"/"yearly").

    Returns:
        Dict with "rowRanges" and "size" keys.
    """
    timestep = timestep or meta["timestep"]
    segments = _parsePeriod(period, meta)

    if outputType in ("rch", "sub"):
        nUnits = meta["n_subbasins"]
        unitIndex = id
        if unitIndex < 1 or unitIndex > nUnits:
            raise ValueError(
                f"id {id} out of range [1, {nUnits}] for output.{outputType}"
            )
    elif outputType == "hru":
        nUnits = _calcNHrusTotal(meta)
        unitIndex = id
        if unitIndex < 1 or unitIndex > nUnits:
            raise ValueError(
                f"id {id} out of range [1, {nUnits}] for output.hru"
            )
    else:
        raise ValueError(f"Unknown outputType: {outputType}")

    rowRanges, size = _calcRowRanges(meta, unitIndex, nUnits, segments, timestep)
    return {"rowRanges": rowRanges, "size": size}
