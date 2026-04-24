from pathlib import Path
from typing import Optional, Union


def resolve_config_file(path: Union[str, Path]) -> Path:
    configFile = Path(path).resolve()
    if not configFile.exists():
        raise FileNotFoundError(f"Config file not found: {configFile}")
    return configFile


def resolve_config_path(path: Optional[Union[str, Path]], basePath: Path) -> Optional[Path]:
    if path is None:
        return None
    rawPath = Path(path)
    if rawPath.is_absolute():
        return rawPath.resolve()
    return (basePath / rawPath).resolve()


def resolve_existing_file(path: Optional[Union[str, Path]], basePath: Path, fieldName: str) -> Optional[Path]:
    fullPath = resolve_config_path(path, basePath)
    if fullPath is None:
        return None
    if not fullPath.exists():
        raise FileNotFoundError(f"{fieldName}: file not found: {fullPath}")
    if not fullPath.is_file():
        raise FileNotFoundError(f"{fieldName}: not a file: {fullPath}")
    return fullPath


def resolve_existing_dir(path: Optional[Union[str, Path]], basePath: Path, fieldName: str) -> Optional[Path]:
    fullPath = resolve_config_path(path, basePath)
    if fullPath is None:
        return None
    if not fullPath.exists():
        raise FileNotFoundError(f"{fieldName}: directory not found: {fullPath}")
    if not fullPath.is_dir():
        raise NotADirectoryError(f"{fieldName}: not a directory: {fullPath}")
    return fullPath
