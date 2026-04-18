import re
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Any, Union, Optional, Tuple

import numpy as np

from .transformer import Transformer
from .writers import getWriter
from ..errors import RunError

# -------------------------------------------------------------
# Constant Mappings
# -------------------------------------------------------------
TYPE_MAP = {"float": 0, "int": 1, "discrete": 2}
MODE_MAP = {"r": 0, "v": 1, "a": 2}


def _expandRowRanges(rowRanges: List[List[int]]) -> List[int]:
    out: List[int] = []
    for rr in rowRanges:
        if len(rr) == 2:
            a, b = rr
            step = 1
        elif len(rr) == 3:
            a, b, step = rr
        else:
            raise ValueError(f"Invalid row range: {rr}")
        out.extend(range(int(a), int(b) + 1, int(step)))
    out.sort()
    return out


def _getItemValue(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


@dataclass
class ParamFileSpec:
    name: str
    line: Union[int, List[int]]
    start: int
    width: int
    precision: int
    maxNum: int


@dataclass
class ParamSpec:
    """Data carrier passed to FixedWidthWriter.register_param as lib_info."""
    name: str
    type: int
    bounds: List[float]
    file: ParamFileSpec

    @staticmethod
    def fromDict(d: Any) -> "ParamSpec":
        name = _getItemValue(d, "name")
        if not name:
            raise ValueError("Physical parameter missing 'name'")
        fileInfo = _getItemValue(d, "file")
        if fileInfo is None:
            raise ValueError(f"Physical parameter '{name}' missing 'file'")

        rawLine = fileInfo["line"]
        if isinstance(rawLine, list) and len(rawLine) > 0 and isinstance(rawLine[0], list):
            parsedLine = _expandRowRanges(rawLine)
        else:
            parsedLine = rawLine

        return ParamSpec(
            name=name,
            type=TYPE_MAP.get(_getItemValue(d, "type", "float"), 0),
            bounds=_getItemValue(d, "bounds", [0, 1]),
            file=ParamFileSpec(
                name=fileInfo["name"] if isinstance(fileInfo["name"], str) else fileInfo["name"][0],
                line=parsedLine,
                start=int(fileInfo["start"]),
                width=int(fileInfo["width"]),
                precision=int(fileInfo["precision"]),
                maxNum=int(fileInfo.get("maxNum", 1)),
            ),
        )

    @property
    def lb(self) -> float:
        return float(self.bounds[0])

    @property
    def ub(self) -> float:
        return float(self.bounds[1])


@dataclass
class DesignParamSpec:
    name: str
    index: int
    type: int
    bounds: List[float]
    sets: List[float]

    @staticmethod
    def fromDict(d: Dict[str, Any], index: int) -> "DesignParamSpec":
        pName = d.get("name")
        if not pName:
            raise ValueError(f"Design parameter at index {index} missing 'name'")
        pType = TYPE_MAP.get(d.get("type", "float"), 0)
        if pType == 2 and "sets" not in d:
            raise ValueError(f"Discrete variable '{pName}' missing 'sets'")
        if pType in (0, 1) and "bounds" not in d:
            raise ValueError(f"Continuous variable '{pName}' missing 'bounds'")
        bounds = [0, 1] if pType == 2 else d.get("bounds", [0, 1])
        return DesignParamSpec(
            name=pName, index=index, type=pType, bounds=bounds,
            sets=d.get("sets", []),
        )

    @property
    def lb(self) -> float:
        return float(self.bounds[0])

    @property
    def ub(self) -> float:
        return float(self.bounds[1])


@dataclass
class PhysicalParamSpec:
    index: int
    name: str
    mode: int

    @staticmethod
    def fromDict(d: Any, index: int) -> "PhysicalParamSpec":
        name = _getItemValue(d, "name")
        if not name:
            raise ValueError(f"Physical parameter at index {index} missing 'name'")
        return PhysicalParamSpec(
            index=index, name=name,
            mode=MODE_MAP.get(_getItemValue(d, "mode", "v"), 1),
        )


# -------------------------------------------------------------
# Parameter Manager
# -------------------------------------------------------------
class ParamManager:
    def __init__(self, cfg, functionManager, backupPath):
        self.cfg = cfg
        self.funcManager = functionManager
        self.backupPath = Path(backupPath) if backupPath else None

        self.writeInTask: Dict[Tuple[str, str], Dict[str, Any]] = {}

        transformFunc = cfg.parameters.transformer if hasattr(cfg.parameters, "transformer") else None
        self.transformer = Transformer(functionManager, transformFunc)

        self.nInput, self.xLabels, self.varType, self.varSet, self.ub, self.lb = self._initParams()

    def _initParams(self) -> Tuple[int, List[str], List[int], Dict[int, List[float]], List[float], List[float]]:
        designList = self.cfg.parameters.design
        physicalList = self.cfg.parameters.physical

        # Parse design parameters
        names: List[str] = []
        seenNames = set()
        types: List[int] = []
        ubs: List[float] = []
        lbs: List[float] = []
        sets: Dict[int, List[float]] = {}

        for i, item in enumerate(designList):
            spec = DesignParamSpec.fromDict(item, i)
            if spec.name in seenNames:
                raise ValueError(f"Duplicate design parameter name: {spec.name}")
            seenNames.add(spec.name)
            names.append(spec.name)
            types.append(spec.type)
            if spec.type == 2:
                sets[i] = spec.sets
            lbs.append(spec.lb)
            ubs.append(spec.ub)

        # Parse physical parameters
        phySpecs: List[PhysicalParamSpec] = []
        seenPhyNames = set()
        for i, item in enumerate(physicalList):
            spec = PhysicalParamSpec.fromDict(item, i)
            seenPhyNames.add(spec.name)
            phySpecs.append(spec)

        self._registerWriteTasks(phySpecs, physicalList)
        return len(names), names, types, sets, ubs, lbs

    def _registerWriteTasks(self, phySpecs: List[PhysicalParamSpec], physicalRaw: List[Any]) -> None:
        projectRoot = Path(self.cfg.basic.projectPath)

        for spec, rawItem in zip(phySpecs, physicalRaw):
            fileInfo = _getItemValue(rawItem, "file")
            if fileInfo is None:
                raise ValueError(f"Physical parameter '{spec.name}' missing 'file' block")

            fileName = fileInfo["name"]

            # file.name supports str (glob/regex/literal) or list[str] (pre-expanded)
            if isinstance(fileName, list):
                realFiles = self._validateFileList(projectRoot, fileName)
            else:
                realFiles = self._resolveFilenames(projectRoot, fileName)

            writerType = _getItemValue(rawItem, "writerType", "fixed_width")
            writerCls = getWriter(writerType)

            # Build a ParamSpec as data carrier for fixed-width-compatible writers
            libInfo = ParamSpec.fromDict(rawItem)

            for relFile in realFiles:
                taskKey = (relFile, writerType)
                if taskKey not in self.writeInTask:
                    absFile = projectRoot / relFile
                    self.writeInTask[taskKey] = {
                        "fileName": relFile,
                        "writerType": writerType,
                        "handler": writerCls(str(absFile)),
                        "indices": [],
                    }
                task = self.writeInTask[taskKey]
                handler = task["handler"]

                # Override file.name in libInfo for this specific file
                fileSpecForFile = ParamFileSpec(
                    name=relFile,
                    line=libInfo.file.line,
                    start=libInfo.file.start,
                    width=libInfo.file.width,
                    precision=libInfo.file.precision,
                    maxNum=libInfo.file.maxNum,
                )
                libInfoForFile = ParamSpec(
                    name=libInfo.name,
                    type=libInfo.type,
                    bounds=libInfo.bounds,
                    file=fileSpecForFile,
                )

                handler.register_param(spec, libInfoForFile, self.cfg.parameters.hardBound)
                task["indices"].append(spec.index)

    def setValues(self, workPath: str, X, env) -> None:
        dataSource = self.transformer.transform(X)

        workRoot = Path(workPath)
        allClampEvents: List[dict] = []

        for (_taskFile, _writerType), task in self.writeInTask.items():
            fileName = task["fileName"]
            handler = task["handler"]
            targetFile = workRoot / fileName
            indices = task["indices"]
            try:
                if len(dataSource) > 0 and len(indices) > 0 and max(indices) >= len(dataSource):
                    raise RunError(
                        stage="params", code="INDEX_OUT_OF_BOUNDS", target=fileName,
                        message=f"Data source has {len(dataSource)} items, but requested index {max(indices)} for file '{fileName}'."
                    )
                valuesToWrite = dataSource[indices]
                clampEvents = handler.set_values_and_save(str(targetFile), indices, valuesToWrite)
                allClampEvents.extend(clampEvents)
            except RunError:
                raise
            except Exception as e:
                raise RunError(
                    stage="params", code="FILE_WRITE_ERROR", target=fileName,
                    message=f"Error writing to file {fileName}: {str(e)}"
                )

        self._aggregateClampWarnings(allClampEvents, env)

    def _aggregateClampWarnings(self, events: List[dict], env: dict) -> None:
        """Aggregate clamp events by parameter and append as warnings to context."""
        if not events:
            return
        warnings = env.get("warnings", [])

        # Count total files per parameter name
        totalFilesByParam: Dict[str, int] = {}
        for (_taskFile, _writerType), task in self.writeInTask.items():
            paramNames = set()
            handler = task["handler"]
            for idx in task["indices"]:
                p = handler.params.get(idx)
                if p:
                    paramNames.add(p.name)
            for name in paramNames:
                totalFilesByParam[name] = totalFilesByParam.get(name, 0) + 1

        # Group by parameter name
        byParam: Dict[str, List[dict]] = {}
        for ev in events:
            name = ev.get("param", "unknown")
            byParam.setdefault(name, []).append(ev)

        for paramName, paramEvents in byParam.items():
            nFiles = len(paramEvents)
            nTotal = totalFilesByParam.get(paramName, nFiles)
            first = paramEvents[0]
            warnings.append(RunError(
                stage="params",
                code="CLAMPED",
                target=paramName,
                message=(
                    f"value {first['raw']:.6g} clamped to {first['clamped']:.6g}, "
                    f"bounds=[{first['lb']}, {first['ub']}], affected {nFiles}/{nTotal} files"
                ),
                severity="warning",
            ))

    def getPhysicalParams(self, X):
        """Return the transformed physical parameter array P."""
        return self.transformer.transform(X)

    def getParamInfo(self):
        return self.nInput, self.xLabels, self.varType, self.varSet, self.ub, self.lb

    def _validateFileList(self, projectPath: Union[str, Path], fileList: List[str]) -> List[str]:
        """Validate a pre-expanded file list. Each entry must exist under projectPath."""
        root = Path(projectPath)
        result = []
        for f in fileList:
            p = root / f
            if not p.exists():
                raise FileNotFoundError(f"File not found: {p}")
            if not p.is_file():
                raise FileNotFoundError(f"Path is not a file: {p}")
            result.append(p.relative_to(root).as_posix())
        return result

    def _resolveFilenames(self, projectPath: Union[str, Path], filePattern: str) -> List[str]:
        root = Path(projectPath)
        if filePattern.startswith("regex:"):
            pattern = filePattern[len("regex:"):].strip()
            try:
                regex = re.compile(pattern)
            except re.error as e:
                raise ValueError(f"Invalid regex pattern '{filePattern}': {e}") from e
            matches: List[str] = []
            for p in root.rglob("*"):
                if not p.is_file():
                    continue
                rel = p.relative_to(root).as_posix()
                if regex.fullmatch(rel):
                    matches.append(rel)
            matches.sort()
            if not matches:
                raise FileNotFoundError(f"Regex pattern '{filePattern}' matched 0 files under {root}")
            return matches

        if any(ch in filePattern for ch in ["*", "?", "["]):
            matches = sorted(p for p in root.glob(filePattern) if p.is_file())
            if not matches:
                raise FileNotFoundError(f"Glob pattern '{filePattern}' matched 0 files under {root}")
            return [p.relative_to(root).as_posix() for p in matches]
        p = root / filePattern
        if not p.exists():
            raise FileNotFoundError(f"File not found: {p}")
        if not p.is_file():
            raise FileNotFoundError(f"Path is not a file: {p}")
        return [p.relative_to(root).as_posix()]
