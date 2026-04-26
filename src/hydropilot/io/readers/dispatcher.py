from . import getReader


def read_extract(workPath, readerSpec):
    readerCls = getReader(readerSpec.readerType)
    reader = readerCls()
    return reader.read(workPath, readerSpec.spec)
