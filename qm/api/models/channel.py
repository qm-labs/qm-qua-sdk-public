import ssl
import atexit
import logging
from dataclasses import dataclass
from typing import Dict, Optional

import grpc

from qm.type_hinting.general import PathLike
from qm.api.models.debug_data import DebugData
from qm.simulate.credentials import validate_client_cert_pair
from qm.api.models.grpc_interceptors import DebugInterceptor, AddHeadersInterceptor

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TlsFilePaths:
    """PEM file paths that gRPC needs to build channel credentials.

    grpcio cannot consume an ``ssl.SSLContext`` (it requires raw PEM bytes) and an SSLContext
    does not expose its loaded private key / client certificate, so these paths travel
    alongside the SSLContext down to ``create_channel`` to support a custom root CA and mTLS.
    """

    ca_cert_path: Optional[PathLike] = None
    client_cert_path: Optional[PathLike] = None
    client_key_path: Optional[PathLike] = None


def _create_debug_data_event(debug_data: DebugData, channel: grpc.Channel) -> grpc.Channel:
    """Create debug interceptor for proto-generated gRPC client"""
    # Apply the interceptor to the channel
    intercepted_channel = grpc.intercept_channel(channel, DebugInterceptor(debug_data))
    return intercepted_channel


def _create_add_headers_event(headers: Dict[str, str], channel: grpc.Channel) -> grpc.Channel:
    """Create interceptor to add headers to all gRPC calls"""
    interceptor = AddHeadersInterceptor(headers)
    return grpc.intercept_channel(channel, interceptor)


def _read_pem(path: Optional[PathLike]) -> Optional[bytes]:
    """Read PEM bytes from ``path``; return ``None`` if no path is given."""
    if not path:
        return None
    with open(path, "rb") as pem_file:
        return pem_file.read()


def create_channel(
    host: str,
    port: int,
    ssl_context: Optional[ssl.SSLContext],
    max_message_size: int,
    headers: Dict[str, str],
    debug_data: Optional[DebugData] = None,
    tls_paths: Optional[TlsFilePaths] = None,
) -> grpc.Channel:
    """
    Create a gRPC channel equivalent to a grpc Channel configuration.

    Args:
        host: Server host
        port: Server port
        max_message_size: Max message size in bytes (used for flow control + message limits)
        ssl_context: Optional ssl.SSLContext. If provided, a secure channel is created.
        tls_paths: Optional PEM file paths for a custom root CA and/or mTLS. When a field is
            omitted, gRPC's default trust roots are used and/or no client certificate is sent.

    Returns:
        grpc.Channel
    """

    address = f"{host}:{port}"

    options = [
        ("grpc.http2.initial_connection_window_size", max_message_size),
        ("grpc.http2.initial_stream_window_size", max_message_size),
        ("grpc.max_receive_message_length", max_message_size),
        ("grpc.max_send_message_length", max_message_size),
    ]

    # ---- TLS channel ----
    if ssl_context is not None:
        tls_paths = tls_paths or TlsFilePaths()
        validate_client_cert_pair(tls_paths.client_cert_path, tls_paths.client_key_path)
        credentials = grpc.ssl_channel_credentials(
            root_certificates=_read_pem(tls_paths.ca_cert_path),
            private_key=_read_pem(tls_paths.client_key_path),
            certificate_chain=_read_pem(tls_paths.client_cert_path),
        )

        channel = grpc.secure_channel(
            address,
            credentials,
            options=options,
        )
    else:
        # ---- Insecure channel ----
        channel = grpc.insecure_channel(
            address,
            options=options,
        )

    if debug_data:
        channel = _create_debug_data_event(debug_data, channel)

    channel = _create_add_headers_event(headers, channel)

    atexit.register(channel.close)

    return channel
