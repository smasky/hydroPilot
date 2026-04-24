import re
from pathlib import Path
from typing import List, Union


def resolve_file_targets(projectPath: Union[str, Path], fileName) -> List[str]:
    root = Path(projectPath)
    if isinstance(fileName, list):
        return validate_file_list(root, fileName)
    return resolve_file_pattern(root, str(fileName))


def validate_file_list(projectPath: Union[str, Path], fileList: List[str]) -> List[str]:
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


def resolve_file_pattern(projectPath: Union[str, Path], filePattern: str) -> List[str]:
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
