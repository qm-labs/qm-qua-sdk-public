from abc import ABCMeta
from typing import Union, TypeVar, Callable, Optional, Protocol, cast

from google.protobuf.empty_pb2 import Empty

from qm.exceptions import QmQuaException, QopResponseError
from qm.api.base_api import BaseApi, StubType, RequestMessageType, ResponseMessageType

SuccessType = TypeVar("SuccessType", covariant=True)


class ResponseMessageTypeV2(Protocol[SuccessType]):
    def HasField(self, name: str) -> bool:
        ...

    @property
    def success(self) -> SuccessType:
        ...


class BaseApiV2(BaseApi[StubType], metaclass=ABCMeta):
    def _run(
        self,
        grpc_method: Callable[..., ResponseMessageType],
        request: Union[RequestMessageType, Empty],
        timeout: Optional[float] = None,
    ) -> SuccessType:  # type: ignore[type-var]

        response = super()._run(grpc_method, request, timeout)
        resp = cast(ResponseMessageTypeV2[SuccessType], response)
        return self._handle_reponse(resp)

    def _handle_reponse(self, response: ResponseMessageTypeV2[SuccessType]) -> SuccessType:
        if response.HasField("success"):
            return response.success
        elif response.HasField("error"):
            raise QopResponseError(error=response.error)  # type: ignore[attr-defined]
        else:
            raise QmQuaException("got response without success or error")
