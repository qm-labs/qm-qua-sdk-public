import ssl
import atexit
import dataclasses
from typing import Dict, Tuple, Optional

from grpc import Channel

from qm.exceptions import QMConnectionError
from qm.api.models.info import QuaMachineInfo
from qm.api.models.debug_data import DebugData
from qm.api.models.channel import create_channel
from qm.api.models.capabilities import ServerCapabilities

MAX_MESSAGE_SIZE = 1024 * 1024 * 100  # 100 mb in bytes
BASE_TIMEOUT = 120

CLOSED_CONNECTION_MESSAGE = "QuantumMachinesManager has been closed. Create a new instance to issue further calls."


@dataclasses.dataclass
class ConnectionDetails:
    host: str
    port: int
    user_token: Optional[str] = dataclasses.field(default=None)
    ssl_context: Optional[ssl.SSLContext] = dataclasses.field(default=None)
    max_message_size: int = dataclasses.field(default=MAX_MESSAGE_SIZE)
    headers: Dict[str, str] = dataclasses.field(default_factory=dict)
    timeout: float = dataclasses.field(default=BASE_TIMEOUT)
    debug_data: Optional[DebugData] = dataclasses.field(default=None)
    _channel: Optional[Channel] = dataclasses.field(repr=False, default=None)
    _closed: bool = dataclasses.field(repr=False, default=False)

    @property
    def is_closed(self) -> bool:
        """Whether ``close()`` has been called on this connection."""
        return self._closed

    def raise_if_closed(self) -> None:
        """Raise ``QMConnectionError`` if this connection has been closed."""
        if self._closed:
            raise QMConnectionError(CLOSED_CONNECTION_MESSAGE)

    @property
    def channel(self) -> Channel:
        """Lazily create (and cache) the gRPC channel for this connection.

        Raises:
            QMConnectionError: if the connection has been closed
        """
        self.raise_if_closed()
        if self._channel is None:
            self._channel = create_channel(
                self.host, self.port, self.ssl_context, self.max_message_size, self.headers, self.debug_data
            )

        return self._channel

    def close(self) -> None:
        """Tear down the underlying gRPC channel and mark this connection unusable.

        Drops the ``atexit`` registration done in ``create_channel`` so the
        channel object can be garbage-collected within the lifetime of the
        process. Idempotent.
        """
        if self._closed:
            return
        self._closed = True
        if self._channel is not None:
            # Without unregister, atexit keeps a strong reference to
            # `channel.close` which transitively pins the channel and prevents GC.
            atexit.unregister(self._channel.close)
            self._channel.close()
            self._channel = None

    def __hash__(self) -> int:
        return hash(
            (
                self.host,
                self.port,
                self.user_token,
                self.ssl_context,
                self.max_message_size,
                tuple(sorted(self.headers.items())),
                self.timeout,
                self.debug_data,
            )
        )


@dataclasses.dataclass
class ResponseConnectionDetails:
    host: str
    port: int
    octaves: Dict[str, Tuple[str, int]]


@dataclasses.dataclass
class ServerDetails:
    port: int
    host: str
    server_version: str
    proto_version: Optional[str]
    connection_details: ConnectionDetails
    octaves: Dict[str, ConnectionDetails]

    # does it implement the QUA service
    qua_implementation: Optional[QuaMachineInfo]
    capabilities: ServerCapabilities = dataclasses.field(default_factory=ServerCapabilities.build)

    def __post_init__(self) -> None:
        self.capabilities = ServerCapabilities.build(qua_implementation=self.qua_implementation)
