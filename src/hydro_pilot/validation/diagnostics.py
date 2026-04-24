from dataclasses import dataclass
from typing import Literal, Optional

DiagnosticLevel = Literal["error", "warning", "info"]


@dataclass(frozen=True)
class Diagnostic:
    level: DiagnosticLevel
    path: str
    message: str
    suggestion: Optional[str] = None


def error(path: str, message: str, suggestion: Optional[str] = None) -> Diagnostic:
    return Diagnostic(level="error", path=path, message=message, suggestion=suggestion)


def warning(path: str, message: str, suggestion: Optional[str] = None) -> Diagnostic:
    return Diagnostic(level="warning", path=path, message=message, suggestion=suggestion)


def info(path: str, message: str, suggestion: Optional[str] = None) -> Diagnostic:
    return Diagnostic(level="info", path=path, message=message, suggestion=suggestion)


def has_error(diagnostics: list[Diagnostic]) -> bool:
    return any(item.level == "error" for item in diagnostics)
