from typing import Dict, Type

from .base import ParamWriter
from .fixed_width import FixedWidthWriter

WRITER_REGISTRY: Dict[str, Type[ParamWriter]] = {}


def registerWriter(writerType: str, writerCls: Type[ParamWriter]) -> None:
    WRITER_REGISTRY[writerType] = writerCls


def getWriter(writerType: str) -> Type[ParamWriter]:
    if writerType not in WRITER_REGISTRY:
        available = ", ".join(sorted(WRITER_REGISTRY.keys())) or "(none)"
        raise ValueError(f"Unknown writer type '{writerType}'. Available writers: {available}")
    return WRITER_REGISTRY[writerType]


registerWriter("fixed_width", FixedWidthWriter)
