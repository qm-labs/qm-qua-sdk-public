from abc import ABCMeta
from typing import Any, TypeVar, Optional, Protocol, Coroutine

import betterproto

from qm.api.base_api import BaseApi, StubType
from qm.exceptions import ErrorType, QopResponseError

SuccessType = TypeVar("SuccessType", bound=betterproto.Message)


class ResponseProtocol(Protocol[SuccessType, ErrorType]):
    success: SuccessType
    error: ErrorType


class BaseApiV2(BaseApi[StubType], metaclass=ABCMeta):
    def _run(self, coroutine: Coroutine[Any, Any, ResponseProtocol[SuccessType, ErrorType]], timeout: Optional[float] = None) -> SuccessType:  # type: ignore[override]
        response = super()._run(coroutine, timeout)  # type: ignore[type-var]
        if response.is_set("success"):  # type: ignore[attr-defined]
            return response.success
        else:
            raise QopResponseError(error=response.error)
