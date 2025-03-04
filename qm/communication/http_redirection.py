import re
import logging
from typing import Dict, Tuple

import httpx
from httpx import Response
from betterproto.lib.google.protobuf import Empty

from qm.utils.async_utils import run_async
from qm.api.models.server_details import ResponseConnectionDetails
from qm.exceptions import QmRedirectionError, QmLocationParsingError

logger = logging.getLogger(__name__)


def _parse_location(location_header: str) -> Tuple[str, int]:
    match = re.match("(?P<host>[^:]*):(?P<port>[0-9]*)(/(?P<url>.*))?", location_header)
    if match is None:
        raise QmLocationParsingError(f"Could not parse new host and port (location header: {location_header})")
    host, port, _, __ = match.groups()
    if not port.isdigit() or not host:
        raise QmLocationParsingError(f"Could not parse new port (location header: {location_header})")
    return str(host), int(port)


def parse_octaves(raw_response: str) -> Dict[str, Tuple[str, int]]:
    octaves = {}
    for octave_details in raw_response.split(";"):
        if octave_details:
            name_and_location = octave_details.split(",")
            if len(name_and_location) != 2:
                raise QmLocationParsingError(
                    f"Could not parse octave name and location from '{octave_details}' (raw response: {raw_response})"
                )
            octaves[name_and_location[0]] = _parse_location(name_and_location[1])
    return octaves


def send_redirection_check(
    host: str, port: int, headers: Dict[str, str], timeout: float, async_follow_redirects: bool, async_trust_env: bool
) -> ResponseConnectionDetails:
    extended_headers = {"content-type": "application/grpc", "te": "trailers", **headers}
    response = run_async(
        _get_httpx_response(f"http://{host}:{port}", extended_headers, timeout, async_follow_redirects, async_trust_env)
    )
    if response.status_code == 400:
        if headers.get("any_cluster", "false") == "false":
            cluster_name = f"cluster '{headers['cluster_name']}'"
        else:
            cluster_name = "any cluster"
        raise QmRedirectionError(f"Connected to server at in {host}:{port}. Could not find {cluster_name}.")
    if response.status_code != 302:
        return ResponseConnectionDetails(host, port, {})

    new_host, new_port = _parse_location(response.headers["location"])
    octaves = parse_octaves(response.headers.get("octaves", ""))

    return ResponseConnectionDetails(new_host, new_port, octaves)


async def _get_httpx_response(
    url: str, headers: Dict[str, str], timeout: float, follow_redirects: bool, trust_env: bool
) -> Response:
    async with httpx.AsyncClient(
        http2=True, follow_redirects=follow_redirects, http1=False, timeout=timeout, trust_env=trust_env
    ) as client:
        response = await client.post(url, headers=headers, content=bytes(Empty()))
    return response
