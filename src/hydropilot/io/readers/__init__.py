from .base import SeriesReader
from .text import TextReader, read_text_extract, parse_fixed_width, parse_col_list

READER_REGISTRY: dict[str, type[SeriesReader]] = {}


def registerReader(readerType: str, readerCls: type[SeriesReader]) -> None:
    READER_REGISTRY[readerType] = readerCls


def getReader(readerType: str) -> type[SeriesReader]:
    if readerType not in READER_REGISTRY:
        available = ", ".join(sorted(READER_REGISTRY.keys())) or "(none)"
        raise ValueError(f"Unknown reader type '{readerType}'. Available readers: {available}")
    return READER_REGISTRY[readerType]


registerReader("text", TextReader)
