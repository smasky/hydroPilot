from typing import Dict, Type

from .base import SeriesReader
from .text_reader import TextReader

READER_REGISTRY: Dict[str, Type[SeriesReader]] = {}


def registerReader(readerType: str, readerCls: Type[SeriesReader]) -> None:
    READER_REGISTRY[readerType] = readerCls


def getReader(readerType: str) -> Type[SeriesReader]:
    if readerType not in READER_REGISTRY:
        available = ", ".join(sorted(READER_REGISTRY.keys())) or "(none)"
        raise ValueError(f"Unknown reader type '{readerType}'. Available readers: {available}")
    return READER_REGISTRY[readerType]


registerReader("text", TextReader)
