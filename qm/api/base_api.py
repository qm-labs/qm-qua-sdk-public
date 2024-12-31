import json
import asyncio
import logging
import functools
from typing_extensions import ParamSpec
from typing import Type, TypeVar, Callable, Optional

import grpclib.exceptions
from grpclib.client import Channel
from grpclib.config import Configuration
from grpclib.events import SendMessage, SendRequest, RecvInitialMetadata, listen

from qm.utils.general_utils import is_debug
from qm.api.models.server_details import ConnectionDetails
from qm.exceptions import QMTimeoutError, QMConnectionError
from qm.utils.async_utils import EventLoopThread, run_async

logger = logging.getLogger(__name__)

Ret = TypeVar("Ret")
P = ParamSpec("P")


def connection_error_handle_decorator(func: Callable[P, Ret]) -> Callable[P, Ret]:
    @functools.wraps(func)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> Ret:
        try:
            return func(*args, **kwargs)
        except grpclib.exceptions.GRPCError as e:
            if is_debug():
                logger.exception("Encountered connection error from QOP")
            raise QMConnectionError(
                f"Encountered connection error from QOP: details: {e.message}, status: {e.status}"
            ) from e
        except asyncio.TimeoutError as e:
            if is_debug():
                logger.exception(f"Timeout reached while running '{func.__name__}'")
            raise QMTimeoutError(f"Timeout reached while running '{func.__name__}'") from e

    return wrapped


T = TypeVar("T")


def connection_error_handle() -> Callable[[Type[T]], Type[T]]:
    def decorate(cls: Type[T]) -> Type[T]:
        for attr in cls.__dict__:
            if callable(getattr(cls, attr)):
                setattr(cls, attr, connection_error_handle_decorator(getattr(cls, attr)))
        return cls

    return decorate


async def create_channel(connection_details: ConnectionDetails) -> Channel:
    return Channel(
        host=connection_details.host,
        port=connection_details.port,
        ssl=connection_details.ssl_context,
        config=Configuration(
            http2_connection_window_size=connection_details.max_message_size,
            http2_stream_window_size=connection_details.max_message_size,
        ),
    )


class BaseApi:
    def __init__(self, connection_details: ConnectionDetails):
        self._connection_details = connection_details
        self._loop = EventLoopThread().loop

        self._channel = run_async(create_channel(self._connection_details))

        if self._connection_details.debug_data:
            self._create_debug_data_event()

        self._create_add_headers_event()
        self._timeout: Optional[float] = self._connection_details.timeout

    def _create_debug_data_event(self) -> None:
        async def intercept_response(event: RecvInitialMetadata) -> None:
            assert self._connection_details.debug_data is not None

            metadata = event.metadata
            logger.debug(f"Collected response metadata: {json.dumps(dict(metadata), indent=4)}")
            self._connection_details.debug_data.append(metadata)

        async def send_request_debug(event: SendRequest) -> None:
            logger.debug("-----------request start-----------")
            logger.debug("   ---    request headers    ---   ")
            logger.debug(f"method:       {event.method_name}")
            logger.debug(f"metadata:     {json.dumps(dict(event.metadata), indent=4)}")
            logger.debug(f"content type: {event.content_type}")
            if event.deadline:
                deadline = event.deadline.time_remaining()
            else:
                deadline = None
            logger.debug(f"deadline:     {deadline}")

        async def send_message_debug(event: SendMessage) -> None:
            logger.debug("   ---    request message    ---   ")
            try:
                logger.debug(f"message:      {event.message.to_json(4)}")
            except TypeError:
                pass
            logger.debug("------------end request------------")

        listen(self._channel, RecvInitialMetadata, intercept_response)
        listen(self._channel, SendRequest, send_request_debug)
        listen(self._channel, SendMessage, send_message_debug)

    def _create_add_headers_event(self) -> None:
        async def add_headers(event: SendRequest) -> None:
            event.metadata.update(self._connection_details.headers)

        listen(self._channel, SendRequest, add_headers)

    @property
    def channel(self) -> Channel:
        return self._channel

    R = TypeVar("R", bound="BaseApi")

    @classmethod
    def from_api(cls: Type[R], other: "BaseApi") -> R:
        return cls(other._connection_details)

    def __del__(self) -> None:
        self.channel.close()
