import copy
from typing import Any, Dict, List

from .library import lookupSeriesVariable


def buildXajSeries(rawSeries: List[Dict[str, Any]], meta: Dict[str, Any], readerType: str = "csv") -> List[Dict[str, Any]]:
    result = []
    for item in rawSeries:
        expanded = copy.deepcopy(item)
        sim = expanded.get("sim")
        if isinstance(sim, dict) and "call" not in sim:
            expanded["sim"] = _resolveXajSim(sim, meta, readerType)
        obs = expanded.get("obs")
        if isinstance(obs, dict) and "call" not in obs:
            obs.setdefault("readerType", readerType)
        result.append(expanded)
    return result


def _resolveXajSim(sim: Dict[str, Any], meta: Dict[str, Any], readerType: str) -> Dict[str, Any]:
    rawSim = copy.deepcopy(sim)
    sim = {
        key: value
        for key, value in rawSim.items()
        if key not in {"variable", "rivid", "headSkip"}
    }
    variableName = sim.get("variable")
    variableName = rawSim.get("variable")
    sim.setdefault("readerType", readerType)
    if not variableName:
        return _shiftRows(sim, int(rawSim.get("headSkip", 0)))

    variable = lookupSeriesVariable(str(variableName))
    if not variable:
        raise ValueError(f"Unknown XAJ series variable '{variableName}'")

    sim.setdefault("file", variable["file"])
    headSkip = int(rawSim.get("headSkip", variable.get("headSkip", 1)))

    if variable.get("idHeader"):
        if "colNum" not in sim:
            if "rivid" not in rawSim:
                raise ValueError(f"XAJ series variable '{variableName}' requires rivid")
            sim["colNum"] = _resolveRividColumn(meta, variable["file"], rawSim["rivid"])
    else:
        sim.setdefault("colNum", int(variable["colNum"]))

    return _shiftRows(sim, headSkip)


def _resolveRividColumn(meta: Dict[str, Any], fileName: str, rivid: Any) -> int:
    headers = meta.get("outputHeaders", {})
    if fileName not in headers:
        raise ValueError(f"XAJ output file header not found: {fileName}")
    target = str(rivid)
    matches = [idx + 1 for idx, value in enumerate(headers[fileName]) if value.strip() == target]
    if not matches:
        raise ValueError(f"XAJ output file '{fileName}' has no RIVID column '{target}'")
    if len(matches) > 1:
        raise ValueError(f"XAJ output file '{fileName}' has duplicate RIVID column '{target}'")
    return matches[0]


def _shiftRows(sim: Dict[str, Any], headSkip: int) -> Dict[str, Any]:
    if headSkip == 0:
        return sim
    if "rowRanges" in sim:
        shiftedRanges = []
        for item in sim["rowRanges"]:
            if len(item) == 2:
                shiftedRanges.append([int(item[0]) + headSkip, int(item[1]) + headSkip])
            elif len(item) == 3:
                shiftedRanges.append([int(item[0]) + headSkip, int(item[1]) + headSkip, int(item[2])])
            else:
                raise ValueError(f"rowRanges item must be [start, end] or [start, end, step], got: {item}")
        sim["rowRanges"] = shiftedRanges
    if "rowList" in sim:
        sim["rowList"] = [int(row) + headSkip for row in sim["rowList"]]
    return sim
