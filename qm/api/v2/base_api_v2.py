from abc import ABCMeta
from typing import Any, TypeVar, Protocol, Coroutine

import betterproto

from qm.utils.async_utils import run_async
from qm.exceptions import ErrorType, QopResponseError
from qm.api.base_api import BaseApi, StubType, connection_error_handle_decorator

SuccessType = TypeVar("SuccessType", bound=betterproto.Message)


class ResponseProtocol(Protocol[SuccessType, ErrorType]):
    success: SuccessType
    error: ErrorType


class BaseApiV2(BaseApi[StubType], metaclass=ABCMeta):
    @staticmethod
    @connection_error_handle_decorator
    def _run(coroutine: Coroutine[Any, Any, ResponseProtocol[SuccessType, ErrorType]]) -> SuccessType:
        response = run_async(coroutine)
        try:  # This one replaces the serialized-on-wire method, while we don't know the group name of the object
            return response.success
        except AttributeError:
            raise QopResponseError(error=response.error)
