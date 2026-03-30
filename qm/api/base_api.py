import logging
import contextlib
from abc import ABCMeta, abstractmethod
from typing import (
    Any,
    Type,
    Tuple,
    Union,
    Generic,
    TypeVar,
    Callable,
    Iterator,
    Optional,
    Protocol,
    Sequence,
    Generator,
    runtime_checkable,
)

import grpc
from grpc import Channel
from google.protobuf.empty_pb2 import Empty
from google.protobuf.message import Message

from qm.utils.general_utils import is_debug
from qm.api.models.server_details import ConnectionDetails
from qm.exceptions import QMTimeoutError, QMConnectionError

logger = logging.getLogger(__name__)

Metadata = Sequence[Tuple[str, str]]


class GatewayNotImplementedError(NotImplementedError):
    pass


def timeout_error_message(timeout: Optional[float]) -> str:
    return f"A timeout of {timeout} seconds was reached. The timeout value can be configured either in the relevant API call (if supported) or when creating the QuantumMachinesManager instance."


@contextlib.contextmanager
def _handle_connection_error(timeout: Optional[float]) -> Generator[None, None, None]:
    try:
        yield
    except grpc.RpcError as e:
        if is_debug():
            logger.exception("Encountered connection error from QOP")

        # Get status code from gRPC exception
        status_code = e.code() if hasattr(e, "code") else None
        details = e.details() if hasattr(e, "details") else str(e)

        if status_code == grpc.StatusCode.UNIMPLEMENTED:
            raise GatewayNotImplementedError(
                f"Encountered connection error from QOP:  details: {details}, status: {status_code}"
            ) from e

        # Handle timeout specifically
        if status_code == grpc.StatusCode.DEADLINE_EXCEEDED:
            error_message = timeout_error_message(timeout)
            if is_debug():
                logger.exception(error_message)
            raise QMTimeoutError(error_message) from e

        raise QMConnectionError(
            f"Encountered connection error from QOP: details: {details}, status:  {status_code}"
        ) from e

    except TimeoutError as e:
        if is_debug():
            logger.exception(timeout_error_message(timeout))
        raise QMTimeoutError(timeout_error_message(timeout)) from e


@runtime_checkable
class GrpcStub(Protocol):
    def __init__(self, channel: Channel) -> None:
        ...

    ...


T = TypeVar("T")
StubType = TypeVar("StubType", bound=GrpcStub)
RequestMessageType = TypeVar("RequestMessageType", bound=Message)
ResponseMessageType = TypeVar("ResponseMessageType", bound=Message)
MetadataLike = Sequence[Tuple[str, str]]


class BaseApi(Generic[StubType], metaclass=ABCMeta):
    def __init__(self, connection_details: ConnectionDetails):
        self._connection_details = connection_details

        self._channel = self._connection_details.channel

        self._stub: StubType = self._stub_class(self._channel)  # type: ignore[assignment]

        self._timeout: Optional[float] = self._connection_details.timeout

    def _run(
        self,
        grpc_method: Callable[..., ResponseMessageType],
        request: Union[RequestMessageType, Empty],
        timeout: Optional[float] = None,
    ) -> ResponseMessageType:
        """
        Run a gRPC call and handle connection errors.

        Args:
            grpc_method: A method from the `self._stub` class (e.g., self._stub.SomeMethod)
            request: The request message to send
            timeout:  A duplicate of the timeout parameter provided to the `self._stub` function. If the default
            `self._timeout` is used, this parameter can be left empty.

        Returns:
            The response message from the gRPC call
        """
        if timeout is None:
            timeout = self._timeout

        with _handle_connection_error(timeout):
            return grpc_method(request, timeout=timeout)

    def _run_iterator(
        self,
        stub_func: Callable[[Any], Iterator[ResponseMessageType]],
        # The parameters are typed as 'Any' because MyPy encounters issues when attempting to declare more specific types.
        request: RequestMessageType,
        *,
        timeout: Optional[float] = None,
        metadata: Optional[MetadataLike] = None,
    ) -> Iterator[ResponseMessageType]:
        """
        Run a function that returns an Iterator (primarily from the self._stub functions), and handle connection errors.

        Args:
            stub_func: A function from the `self._stub` class that returns an Iterator
            request:  The request message to be sent to the function
            timeout:  Timeout for the request in seconds
            metadata: Additional metadata to send with the request

        Returns:
            The Iterator of response messages from the function
        """

        with _handle_connection_error(timeout):
            for response in stub_func(request, timeout=timeout, metadata=metadata):  # type: ignore[call-arg]
                yield response

    @property
    def connection_details(self) -> ConnectionDetails:
        return self._connection_details

    @property
    @abstractmethod
    def _stub_class(self) -> Type[GrpcStub]:
        pass

    @property
    def channel(self) -> Channel:
        return self._channel
