import ssl
import json
import atexit
import logging
from typing import Dict, Optional

from grpclib.client import Channel
from grpclib.config import Configuration
from grpclib.events import SendMessage, SendRequest, RecvInitialMetadata, listen

from qm.api.models.debug_data import DebugData

logger = logging.getLogger(__name__)


def _create_debug_data_event(debug_data: DebugData, channel: Channel) -> None:
    async def intercept_response(event: RecvInitialMetadata) -> None:
        metadata = event.metadata
        logger.debug(f"Collected response metadata: {json.dumps(dict(metadata), indent=4)}")
        debug_data.append(metadata)

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

    listen(channel, RecvInitialMetadata, intercept_response)
    listen(channel, SendRequest, send_request_debug)
    listen(channel, SendMessage, send_message_debug)


def _create_add_headers_event(headers: Dict[str, str], channel: Channel) -> None:
    async def add_headers(event: SendRequest) -> None:
        event.metadata.update(headers)

    listen(channel, SendRequest, add_headers)


async def create_channel(
    host: str,
    port: int,
    ssl_context: Optional[ssl.SSLContext],
    max_message_size: int,
    headers: Dict[str, str],
    debug_data: Optional[DebugData] = None,
) -> Channel:

    channel = Channel(
        host=host,
        port=port,
        ssl=ssl_context,
        config=Configuration(
            http2_connection_window_size=max_message_size,
            http2_stream_window_size=max_message_size,
        ),
    )

    if debug_data:
        _create_debug_data_event(debug_data, channel)

    _create_add_headers_event(headers, channel)

    atexit.register(channel.close)

    return channel
