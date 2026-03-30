import json
import logging
from typing import Any, Dict, Tuple, Union, TypeVar, Callable, Optional, cast

import grpc
from multidict import MultiDict
from google.protobuf.message import Message
from google.protobuf.json_format import MessageToJson

from qm.exceptions import QmQuaException
from qm.api.models.debug_data import DebugData

# gRPC typing helpers
ClientCallDetails = grpc.ClientCallDetails
ReqT = TypeVar("ReqT")
RespT = TypeVar("RespT")


# Runtime-safe fallback — no subscripting
UnaryUnaryResult = grpc.Future
UnaryStreamResult = grpc.Call

# Important
# due to mypy-runtime grpc discrepancies I place some mypy ignores in this file after seeing it will be very hard to support both mypy and runtime
UnaryUnaryContinuation = Callable[..., UnaryUnaryResult]  # type: ignore[type-arg]
UnaryStreamContinuation = Callable[..., UnaryStreamResult]

logger = logging.getLogger(__name__)

MetadataItem = Tuple[str, Union[str, bytes]]
Metadata = Optional[Tuple[MetadataItem, ...]]


class _ClientCallDetails(grpc.ClientCallDetails):
    def __init__(
        self,
        method: str,
        timeout: Optional[float],
        metadata: Metadata,
        credentials: Optional[Any] = None,
        wait_for_ready: Optional[bool] = None,
        compression: Optional[Any] = None,
    ):
        self.method = method
        self.timeout = timeout
        self.metadata = metadata
        self.credentials = credentials
        self.wait_for_ready = wait_for_ready
        self.compression = compression


class DebugInterceptor(
    grpc.UnaryUnaryClientInterceptor,
    grpc.UnaryStreamClientInterceptor,
):
    def __init__(self, debug_data: DebugData) -> None:
        self.debug_data = debug_data

    def intercept_unary_unary(  # type: ignore[override]
        self,
        continuation: UnaryUnaryContinuation,
        client_call_details: ClientCallDetails,
        request: ReqT,
    ) -> UnaryUnaryResult:  # type: ignore[type-arg]
        self._log_request(client_call_details, request)
        future = continuation(client_call_details, request)
        self._log_response_metadata(future, False)
        return future

    def intercept_unary_stream(  # type: ignore[override]
        self,
        continuation: UnaryStreamContinuation,
        client_call_details: ClientCallDetails,
        request: ReqT,
    ) -> UnaryStreamResult:
        self._log_request(client_call_details, request)
        response = continuation(client_call_details, request)
        self._log_response_metadata(response, True)
        return response

    def _log_request(
        self,
        client_call_details: ClientCallDetails,
        request: ReqT,
    ) -> None:
        logger.debug("-----------request start-----------")
        logger.debug("   ---    request headers    ---   ")
        logger.debug(f"method:        {client_call_details.method}")

        if client_call_details.metadata:
            metadata_dict = dict(client_call_details.metadata)
            logger.debug(f"metadata:     {json.dumps(metadata_dict, indent=4)}")
        else:
            logger.debug("metadata:     None")

        if client_call_details.timeout is not None:
            logger.debug(f"timeout:      {client_call_details.timeout}")
        else:
            logger.debug("timeout:      None")

        if isinstance(request, Message):
            logger.debug("   ---    request message    ---   ")
            try:
                message_json = MessageToJson(request, indent=4)
                logger.debug(f"message:      {message_json}")
            except Exception as e:
                logger.debug(f"message:      [Could not serialize: {e}]")

            logger.debug("------------end request------------")
        else:
            raise QmQuaException(f"got request of type {type(request)} instead of protobuf Message")

    def _log_response_metadata(
        self,
        response: Union[UnaryUnaryResult, UnaryStreamResult],  # type: ignore[type-arg]
        is_stream: bool,
    ) -> None:
        try:
            initial_metadata = response.initial_metadata()  # type: ignore[union-attr]
            metadata_dict = dict(initial_metadata)
            logger.debug(f"Collected response metadata: {json.dumps(metadata_dict, indent=4)}")
            self.debug_data.append(cast(MultiDict[Union[str, bytes]], metadata_dict))
        except Exception as e:
            logger.debug(f"Could not extract response metadata: {e}")


class AddHeadersInterceptor(
    grpc.UnaryUnaryClientInterceptor,
    grpc.UnaryStreamClientInterceptor,
):
    def __init__(self, headers: Dict[str, str]):
        self.headers = headers

    def intercept_unary_unary(  # type: ignore[override]
        self,
        continuation: UnaryUnaryContinuation,
        client_call_details: ClientCallDetails,
        request: ReqT,
    ) -> UnaryUnaryResult:  # type: ignore[type-arg]
        new_details = self._add_headers_to_call_details(client_call_details)
        return continuation(new_details, request)

    def intercept_unary_stream(  # type: ignore[override]
        self,
        continuation: UnaryStreamContinuation,
        client_call_details: ClientCallDetails,
        request: ReqT,
    ) -> UnaryStreamResult:
        new_details = self._add_headers_to_call_details(client_call_details)
        return continuation(new_details, request)

    def _add_headers_to_call_details(self, client_call_details: ClientCallDetails) -> ClientCallDetails:
        new_metadata = list(self.headers.items())

        if client_call_details.metadata:
            new_metadata.extend((k, v.decode() if isinstance(v, bytes) else v) for k, v in client_call_details.metadata)

        return _ClientCallDetails(
            method=client_call_details.method,
            timeout=client_call_details.timeout,
            metadata=tuple(new_metadata),
            credentials=getattr(client_call_details, "credentials", None),
            wait_for_ready=getattr(client_call_details, "wait_for_ready", None),
            compression=getattr(client_call_details, "compression", None),
        )
