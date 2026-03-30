import ssl
import atexit
import logging
from typing import Dict, Optional

import grpc

from qm.api.models.debug_data import DebugData
from qm.api.models.grpc_interceptors import DebugInterceptor, AddHeadersInterceptor

logger = logging.getLogger(__name__)


def _create_debug_data_event(debug_data: DebugData, channel: grpc.Channel) -> grpc.Channel:
    """Create debug interceptor for proto-generated gRPC client"""
    # Apply the interceptor to the channel
    intercepted_channel = grpc.intercept_channel(channel, DebugInterceptor(debug_data))
    return intercepted_channel


def _create_add_headers_event(headers: Dict[str, str], channel: grpc.Channel) -> grpc.Channel:
    """Create interceptor to add headers to all gRPC calls"""
    interceptor = AddHeadersInterceptor(headers)
    return grpc.intercept_channel(channel, interceptor)


def create_channel(
    host: str,
    port: int,
    ssl_context: Optional[ssl.SSLContext],
    max_message_size: int,
    headers: Dict[str, str],
    debug_data: Optional[DebugData] = None,
) -> grpc.Channel:
    """
    Create a gRPC channel equivalent to a grpc Channel configuration.

    Args:
        host: Server host
        port: Server port
        max_message_size: Max message size in bytes (used for flow control + message limits)
        ssl_context: Optional ssl.SSLContext. If provided, a secure channel is created.

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
        # grpc does NOT accept SSLContext directly.
        # We extract what grpc needs from it.

        # Root CAs
        root_certs = None
        if ssl_context.verify_mode != ssl.CERT_NONE:
            try:
                root_certs_list = ssl_context.get_ca_certs(binary_form=True)
                # get_ca_certs returns a list; grpc expects bytes
                root_certs = b"".join(root_certs_list) if root_certs_list else None
            except Exception:
                root_certs = None

        credentials = grpc.ssl_channel_credentials(
            root_certificates=root_certs,
            private_key=None,
            certificate_chain=None,
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
