import logging
import threading
from typing import Callable, Optional

import grpc

from qm.grpc.octave.v1 import api_pb2
from qm.octave_sdk._octave_client import OctaveClient, ExploreResult, MonitorResult

logger = logging.getLogger("qm")


NUM_CONNECTION_RETRIES = 3


class HealthClient:
    # Creates a constant gRPC stream to the Server, will call the "health_update_callback" on new health result
    # health_update_callback args should be (ExploreResult, MonitorResult)
    def __init__(
        self,
        interval: int,
        client: OctaveClient,
        health_update_callback: Callable[[ExploreResult, MonitorResult], None],
    ):
        self._interval = interval
        self._client = client
        self._callback = health_update_callback
        self._stream_running = False
        self._grace_stop = False
        self._connection_lost = 0

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        self._stop_event.clear()
        self._grace_stop = False
        self._thread = threading.Thread(target=self._health_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._grace_stop = True
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)

    def _health_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._health_monitor()
            except (TimeoutError, ConnectionRefusedError):
                pass
            except grpc.RpcError as e:
                # Get status code from gRPC exception
                status_code = e.code() if hasattr(e, "code") else None

                if status_code == grpc.StatusCode.UNIMPLEMENTED:
                    # In case of health monitor not implemented, we do not want to print messages of disconnection
                    logger.warning(f'Octave "{self._client.octave_name}" does not support live monitoring')
                    self._stream_running = False
                    return
                # all other gRPC errors are ignored (mirrors old async logic)
            finally:
                if not self._grace_stop and self._stream_running:
                    self._connection_lost += 1
                    logger.error(f'Octave "{self._client.octave_name}" lost monitor connection')
                    if self._connection_lost == NUM_CONNECTION_RETRIES:
                        logger.error(f"Failed {NUM_CONNECTION_RETRIES} times to connect Octave aborting")

    def _health_monitor(self) -> None:
        self._stream_running = False
        try:
            self._client._service.GetVersion(api_pb2.GetVersionRequest())
            self._health_answers = self._client._service.Health(
                iter([api_pb2.HealthRequest(monitor_interval_seconds=self._interval, stop_stream=False)])
            )
            self._stream_running = True
            if self._connection_lost:
                self._connection_lost = 0
                logger.info(f'Octave "{self._client.octave_name}" restored monitor connection')

            # FYI infinite loop here until server stream ends or task cancel
            for response in self._health_answers:
                self._callback(ExploreResult(response.explore), MonitorResult(response.monitor))

        except (TimeoutError, ConnectionRefusedError):
            pass
        except grpc.RpcError as e:
            # Get status code from gRPC exception
            status_code = e.code() if hasattr(e, "code") else None

            # cancelled exception is ignored
            if status_code != grpc.StatusCode.CANCELLED:
                raise

    def run_once(self) -> None:
        explore_result = self._client.explore()
        monitor_result = self._client.monitor()
        self._callback(explore_result, monitor_result)
