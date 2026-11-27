import traceback
from pathlib import Path

from qm.exceptions import QmQuaException

QM_PACKAGE_DIR = Path(__file__).resolve().parent
_MAX_LINE_LENGTH = 200
_ELLIPSIS = "..."


def _shorten(line: str) -> str:
    if len(line) <= _MAX_LINE_LENGTH:
        return line
    return line[: _MAX_LINE_LENGTH - len(_ELLIPSIS)] + _ELLIPSIS


def _get_loc() -> str:
    tb = traceback.extract_stack()
    for trace in reversed(tb):
        if QM_PACKAGE_DIR not in Path(trace.filename).parents:
            return f'File "{trace.filename}", line {trace.lineno}: {_shorten(trace.line or "")}'
    raise QmQuaException("Could not find location")
