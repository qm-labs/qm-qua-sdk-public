import json
import datetime
from enum import Enum
from dataclasses import dataclass
from typing import Any, List, Tuple, cast

DtypeType = List[List[str]]


class InsertDirection(Enum):
    start = 1
    end = 2


@dataclass(frozen=True)
class PendingJobData:
    job_id: str
    position_in_queue: int
    time_added: datetime.datetime
    added_by: str


@dataclass
class JobNamedResult:
    data: bytes
    count_of_items: int
    output_name: str


@dataclass
class JobResultItemSchema:
    name: str
    bare_dtype: str
    shape: Tuple[int, ...]
    is_single: bool
    expected_count: int

    @property
    def dtype(self) -> DtypeType:
        return _parse_dtype(self.bare_dtype)


@dataclass
class JobStreamingState:
    job_id: str
    done: bool
    closed: bool
    has_dataloss: bool


@dataclass
class JobNamedResultHeader:
    count_so_far: int
    bare_dtype: str
    shape: tuple[int, ...]
    has_dataloss: bool
    has_execution_errors: bool

    @property
    def d_type(self) -> DtypeType:
        return _parse_dtype(self.bare_dtype)


def _parse_dtype(simple_dtype: str) -> DtypeType:
    def hinted_tuple_hook(obj: Any) -> Any:
        if "__tuple__" in obj:
            return tuple(obj["items"])
        else:
            return obj

    dtype = json.loads(simple_dtype, object_hook=hinted_tuple_hook)
    return cast(DtypeType, dtype)
