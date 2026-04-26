from .base import ParamWriter
from .fixed_width import FixedWidthWriter

WRITER_REGISTRY: dict[str, type[ParamWriter]] = {}


def registerWriter(writerType: str, writerCls: type[ParamWriter]) -> None:
    WRITER_REGISTRY[writerType] = writerCls


def getWriter(writerType: str) -> type[ParamWriter]:
    if writerType not in WRITER_REGISTRY:
        available = ", ".join(sorted(WRITER_REGISTRY.keys())) or "(none)"
        raise ValueError(f"Unknown writer type '{writerType}'. Available writers: {available}")
    return WRITER_REGISTRY[writerType]


registerWriter("fixed_width", FixedWidthWriter)
