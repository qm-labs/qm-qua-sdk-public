import math
import time
import asyncio
import logging
import contextlib
from abc import ABCMeta, abstractmethod
from typing import Any, Type, Generic, TypeVar, Callable, Optional, Coroutine, Generator, AsyncIterator

import betterproto
import grpclib.exceptions
from grpclib import Status
from grpclib.client import Channel
from grpclib.metadata import Deadline
from grpclib.exceptions import StreamTerminatedError
from betterproto.grpc.grpclib_client import ServiceStub, MetadataLike

from qm.utils.async_utils import run_async
from qm.utils.general_utils import is_debug
from qm.api.models.server_details import ConnectionDetails
from qm.exceptions import QMTimeoutError, QMConnectionError

logger = logging.getLogger(__name__)


class GatewayNotImplementedError(NotImplementedError):
    pass


def _check_stream_terminated_is_timeout(func_start_time: float, func_timeout: float) -> bool:
    """
    When the function's timeout is reached, grpclib cancels the internally created future (distinct from the one created
    in the SDK). This cancellation prompts the server to reset the stream, triggering a "Stream reset by remote party"
    event and resulting in a StreamTerminatedError.
    This function verifies that the StreamTerminatedError is due to a timeout by ensuring that the function's
    runtime is approximately equal to the specified timeout.
    """
    func_end_time = time.time()
    func_runtime = func_end_time - func_start_time
    # Check if the function's runtime is within 10% of the specified timeout
    return math.isclose(func_runtime, func_timeout, rel_tol=0.1)


@contextlib.contextmanager
def _handle_connection_error(timeout: Optional[float] = None) -> Generator[None, None, None]:
    func_start_time = time.time()
    try:
        yield
    except grpclib.exceptions.GRPCError as e:
        if is_debug():
            logger.exception("Encountered connection error from QOP")
        if e.status == Status.UNIMPLEMENTED:
            raise GatewayNotImplementedError(
                f"Encountered connection error from QOP: details: {e.message}, status: {e.status}"
            ) from e
        raise QMConnectionError(
            f"Encountered connection error from QOP: details: {e.message}, status: {e.status}"
        ) from e
    except asyncio.TimeoutError as e:
        if is_debug():
            logger.exception("Timeout reached")
        raise QMTimeoutError("Timeout reached") from e
    except StreamTerminatedError as e:
        if is_debug():
            logger.exception("Stream terminated")

        if timeout is not None:
            if _check_stream_terminated_is_timeout(func_start_time, timeout):
                raise QMTimeoutError("Stream terminated, most likely due to a timeout") from e
        raise e


T = TypeVar("T")
StubType = TypeVar("StubType", bound=ServiceStub)
RequestMessageType = TypeVar("RequestMessageType", bound=betterproto.Message)
ResponseMessageType = TypeVar("ResponseMessageType", bound=betterproto.Message)


class BaseApi(Generic[StubType], metaclass=ABCMeta):
    def __init__(self, connection_details: ConnectionDetails):
        self._connection_details = connection_details

        self._channel = self._connection_details.channel
        self._stub: StubType = self._stub_class(self._channel)

        self._timeout: Optional[float] = self._connection_details.timeout

    def _run(
        self, coroutine: Coroutine[Any, Any, ResponseMessageType], timeout: Optional[float] = None
    ) -> ResponseMessageType:
        """
        Run a coroutine (primarily from the self._stub functions) and handle connection errors.

        Args:
            coroutine: Any coroutine function from the `self._stub` class
            timeout: A duplicate of the timeout parameter provided to the `self._stub` function. If the default
            `self._timeout` is used, this parameter can be left empty.

        Returns:
            The response message from the coroutine
        """
        if timeout is None:
            timeout = self._timeout

        with _handle_connection_error(timeout):
            return run_async(coroutine)

    async def _run_async_iterator(
        self,
        stub_func: Callable[[Any], AsyncIterator[ResponseMessageType]],
        # The parameters are typed as 'Any' because MyPy encounters issues when attempting to declare more specific types.
        request: RequestMessageType,
        *,
        timeout: Optional[float] = None,
        deadline: Optional["Deadline"] = None,
        metadata: Optional["MetadataLike"] = None,
    ) -> AsyncIterator[ResponseMessageType]:
        """
        Run a function that returns an AsyncIterator (primarily from the self._stub functions), and handle connection errors.

        Args:
            stub_func: A function from the `self._stub` class that returns an AsyncIterator
            request: The request message to be sent to the function
            func_kwargs: Any additional keyword arguments to be passed to the function

        Returns:
            The AsyncIterator of response messages from the function
        """

        with _handle_connection_error(timeout):
            async for response in stub_func(request, timeout=timeout, deadline=deadline, metadata=metadata):  # type: ignore[call-arg]
                yield response

    @property
    def connection_details(self) -> ConnectionDetails:
        return self._connection_details

    @property
    @abstractmethod
    def _stub_class(self) -> Type[StubType]:
        pass

    @property
    def channel(self) -> Channel:
        return self._channel
