from typing import Any, Dict, List

from .library import getSeriesVariableNames, lookupSeriesVariable
from .variables import calcSwatOutputRows


SWAT_OUTPUT_TYPES = ("rch", "sub", "hru")


def buildSwatSeries(
    rawSeries: List[Dict[str, Any]],
    meta: Dict[str, Any],
    readerType: str = "text",
) -> List[Dict[str, Any]]:
    for series in rawSeries:
        sim = series.get("sim", {})
        if isinstance(sim, dict) and "call" not in sim:
            _resolveSwatExtract(series, sim, meta, readerType)

        obs = series.get("obs")
        if isinstance(obs, dict):
            obs.setdefault("readerType", readerType)

    return rawSeries


def _hasExplicitColumn(sim: Dict[str, Any]) -> bool:
    return "colSpan" in sim or "colNum" in sim


def _resolveSwatColumn(series: Dict[str, Any], sim: Dict[str, Any], outputType: str | None) -> None:
    if _hasExplicitColumn(sim):
        return

    variableName = sim.pop("variable", None)
    if variableName is None:
        return

    simFile = sim.get("file", "")
    seriesId = series.get("id", "<unknown>")
    if outputType is None:
        raise ValueError(
            f"Series '{seriesId}' sim.variable requires a SWAT output file when colSpan/colNum is omitted: {simFile}"
        )

    variableDef = lookupSeriesVariable(simFile, variableName)
    if variableDef is None:
        available = getSeriesVariableNames(simFile)
        raise ValueError(
            f"Series '{seriesId}' variable '{variableName}' does not match file '{simFile}'. "
            f"Available variables: {available}"
        )

    colSpan = variableDef.get("colSpan")
    if colSpan is None:
        raise ValueError(
            f"SWAT variable '{variableName}' for file '{simFile}' has no colSpan in swat_db.yaml"
        )
    sim["colSpan"] = list(colSpan)


def _resolveSwatExtract(
    series: Dict[str, Any],
    sim: Dict[str, Any],
    meta: Dict[str, Any],
    readerType: str,
) -> None:
    sim.setdefault("readerType", readerType)

    simFile = sim.get("file", "")
    outputType = inferSwatOutputType(simFile)
    _resolveSwatColumn(series, sim, outputType)
    if outputType is None:
        return

    objectId = sim.pop("id", None)
    period = sim.pop("period", None)
    timestep = sim.pop("timestep", None)
    if "subbasin" in sim or "hru" in sim:
        seriesId = series.get("id", "<unknown>")
        raise ValueError(f"Series '{seriesId}' uses deprecated subbasin/hru fields; use sim.id instead")
    if objectId is None:
        return

    result = calcSwatOutputRows(
        meta=meta,
        outputType=outputType,
        id=objectId,
        period=period,
        timestep=timestep,
    )
    sim["rowRanges"] = result["rowRanges"]
    series["size"] = result["size"]


def inferSwatOutputType(fileName: str) -> str | None:
    for ext in SWAT_OUTPUT_TYPES:
        if fileName == f"output.{ext}" or fileName.endswith(f"/output.{ext}") or fileName.endswith(f"\\output.{ext}"):
            return ext
    return None
