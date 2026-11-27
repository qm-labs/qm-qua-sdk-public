from typing import Optional, overload

from qm.type_hinting import NumberT
from qm.exceptions import QmQuaException
from qm.qua._dsl.variable_handling import advance_input_stream
from qm.qua._dsl.streams.external_streams import _receive_from_opnic_stream
from qm.qua._expressions import (
    StructT,
    QuaVariable,
    QuaArrayInputStream,
    InputStreamInterface,
    QuaVariableInputStream,
    QuaExternalIncomingStream,
)


@overload
def receive_from_stream(stream: QuaVariableInputStream[NumberT]) -> None:
    """
    Receive the next scalar value from a client input stream.

    This is equivalent to [qm.qua.advance_input_stream][].

    Args:
        stream (QuaVariableInputStream[NumberT]): The client input stream to advance.
    """
    ...


@overload
def receive_from_stream(stream: QuaArrayInputStream[NumberT]) -> None:
    """
    Receive the next array from a client input stream.

    This is equivalent to [qm.qua.advance_input_stream][].

    Args:
        stream (QuaArrayInputStream[NumberT]): The client input stream to advance.
    """
    ...


@overload
def receive_from_stream(
    stream: QuaExternalIncomingStream[StructT],
    *,
    target_variable: StructT,
) -> None:
    """
    Receive the next packet from an incoming OPNIC stream (blocking).

    Args:
        stream (QuaExternalIncomingStream[StructT]): The incoming OPNIC stream to receive from.
        target_variable (StructT): The struct instance that will hold the received packet.
            This must be declared with [qm.qua.declare_struct][].
    """
    ...


@overload
def receive_from_stream(
    stream: QuaExternalIncomingStream[StructT],
    *,
    target_variable: StructT,
    is_valid: QuaVariable[bool],
    duration: int,
) -> None:
    """
    Receive the next packet from an incoming OPNIC stream (non-blocking).

    Args:
        stream (QuaExternalIncomingStream[StructT]): The incoming OPNIC stream to receive from.
        target_variable (StructT): The struct instance that will hold the received packet.
            This must be declared with [qm.qua.declare_struct][].
        is_valid (QuaVariable[bool]): A boolean variable, declared with [qm.qua.declare][] ``(bool)``,
            that will hold whether a packet actually arrived within ``duration``. Must be provided
            together with ``duration``.
        duration (int): The fixed number of clock cycles (4ns) this non-blocking receive is bounded
            to, regardless of whether a packet actually arrived. Must be provided together with
            ``is_valid``.
    """
    ...


def receive_from_stream(
    stream: InputStreamInterface,
    *,
    target_variable: Optional[StructT] = None,
    is_valid: Optional[QuaVariable[bool]] = None,
    duration: Optional[int] = None,
) -> None:
    """
    Receive the next item from an input stream.

    This is a blocking operation for client input streams, and for OPNIC input streams unless
    both ``is_valid`` and ``duration`` are provided. If no data is available yet, the OPX waits
    until the next value or packet arrives.

    For client input streams, this is equivalent to [qm.qua.advance_input_stream][]:
    it advances the stream so the declared QUA variable or array now holds the next queued value.

    For OPNIC input streams, this receives the next packet and copies it into ``target_variable``.
    Providing ``is_valid`` and ``duration`` together switches to a non-blocking receive: the
    operation always takes exactly ``duration`` clock cycles, and ``is_valid`` is set to whether
    a packet actually arrived within that window.

    Args:
        stream: The incoming stream to receive data from.
        target_variable: A struct instance declared with [qm.qua.declare_struct][] that will hold
            the received packet. This argument is required for OPNIC streams and must not be passed
            for client streams.
        is_valid: A QUA boolean variable that will hold whether a packet arrived. Only supported
            for OPNIC streams, and only together with ``duration``.
        duration: The fixed number of clock cycles (4ns) a non-blocking receive is bounded to.
            Only supported for OPNIC streams, and only together with ``is_valid``.

    Example:
        ```python
        tau = declare_input_stream("client", "tau", int)
        receive_from_stream(tau)  # This advances tau to the next queued value.

        # OPNIC usage example (blocking)
        packet_stream = declare_input_stream("opnic", 1, Packet)
        packet = declare_struct(Packet)
        receive_from_stream(packet_stream, target_variable=packet)  # This updates packet in place.

        # OPNIC usage example (non-blocking)
        arrived = declare(bool)
        receive_from_stream(packet_stream, target_variable=packet, is_valid=arrived, duration=10000)
        with if_(arrived):
            ...
        ```
    """
    if isinstance(stream, QuaVariableInputStream) or isinstance(stream, QuaArrayInputStream):
        if target_variable is not None:
            raise QmQuaException("Client input streams can not receive data into a target variable.")
        if is_valid is not None or duration is not None:
            raise QmQuaException("'is_valid' and 'duration' are only supported for opnic streams.")
        advance_input_stream(stream)

    elif isinstance(stream, QuaExternalIncomingStream):
        if target_variable is None:
            raise QmQuaException("'target_variable' must be provided when receiving data from an opnic stream.")
        _receive_from_opnic_stream(stream, target_variable, is_valid=is_valid, duration=duration)

    else:
        raise QmQuaException(f"Unsupported stream type: {type(stream).__name__}.")
