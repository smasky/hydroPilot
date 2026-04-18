from typing import Any, Dict, List

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


def _resolveSwatExtract(
    series: Dict[str, Any],
    sim: Dict[str, Any],
    meta: Dict[str, Any],
    readerType: str,
) -> None:
    sim.setdefault("readerType", readerType)

    simFile = sim.get("file", "")
    outputType = inferSwatOutputType(simFile)
    if outputType is None:
        return

    subbasin = sim.pop("subbasin", None)
    hru = sim.pop("hru", None)
    period = sim.pop("period", None)
    timestep = sim.pop("timestep", None)
    if subbasin is None:
        return

    result = calcSwatOutputRows(
        meta=meta,
        outputType=outputType,
        subbasin=subbasin,
        period=period,
        timestep=timestep,
        hru=hru,
    )
    sim["rowRanges"] = result["rowRanges"]
    series["size"] = result["size"]


def inferSwatOutputType(fileName: str) -> str | None:
    for ext in SWAT_OUTPUT_TYPES:
        if fileName == f"output.{ext}" or fileName.endswith(f"/output.{ext}") or fileName.endswith(f"\\output.{ext}"):
            return ext
    return None
