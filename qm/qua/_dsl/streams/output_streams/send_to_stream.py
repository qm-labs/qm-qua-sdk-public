from typing import Union, cast, overload

from qm.qua._dsl.variable_handling import save
from qm.exceptions import QmQuaException, SaveToAdcTraceException
from qm.qua._dsl.streams.external_streams import _send_to_opnic_stream
from qm.qua._dsl.stream_processing.stream_processing import ResultStreamSource
from qm.qua._expressions import (
    StructT,
    ScalarOfAnyType,
    OutputStreamInterface,
    QuaExternalOutgoingStream,
    validate_scalar_of_any_type,
)


@overload
def send_to_stream(stream: ResultStreamSource, data: ScalarOfAnyType) -> None:
    """
    Send a scalar value to a client output stream.

    This is equivalent to [qm.qua.save][] with a declared client output stream:
    ``send_to_stream(stream, value)`` and ``save(value, stream)`` produce the same stream items.

    Args:
        stream (ResultStreamSource): The client output stream to write to.
        data (ScalarOfAnyType): The scalar value to send.
    """
    ...


@overload
def send_to_stream(stream: QuaExternalOutgoingStream[StructT], data: StructT) -> None:
    """
    Send one packet to an outgoing OPNIC stream.

    Args:
        stream (QuaExternalOutgoingStream[StructT]): The outgoing OPNIC stream to write to.
        data (StructT): The struct instance to send. It must match the packet type declared for the stream.
    """
    ...


def send_to_stream(stream: OutputStreamInterface, data: Union[StructT, ScalarOfAnyType]) -> None:
    """
    Send one item to an output stream.

    For client output streams declared with [qm.qua.declare_output_stream][], this is equivalent to
    [qm.qua.save][] with a declared stream:
    ``send_to_stream(stream, value)`` and ``save(value, stream)`` produce the same client-stream items.
    If the stream was declared with ``dtype``, the value is cast to that type before it is saved.

    Writing to a declared client output stream does not by itself create a client-visible result handle.
    The stream items become input to [qm.qua.stream_processing][], and to retrieve them on the client
    you must terminate the pipeline in a ``with stream_processing():`` block, for example with
    ``my_stream.save_all("results")``.

    This function does not replace the legacy tag-based form ``save(value, "tag")``, which still writes
    directly to a result tag without requiring a declared client output stream.

    For OPNIC output streams, this sends one packet represented by a struct instance to the OPNIC endpoint.

    Args:
        stream: The outgoing stream to send data to.
        data: The data to send. Client streams accept only scalar values. OPNIC streams require a struct
            instance that matches the packet type declared for the stream.

    Note:
        ``send_to_stream()`` cannot be used with ADC-trace streams. Streams used with
        ``measure(..., adc_stream=...)`` should not be used with ``send_to_stream()``.

    Example:
        ```python
        # Client usage example
        result_stream = declare_output_stream("client", dtype=int)
        send_to_stream(result_stream, 3.14)

        # OPNIC usage example
        packet_stream = declare_output_stream("opnic", 2, Packet)
        packet = declare_struct(Packet)
        send_to_stream(packet_stream, packet)
        ```
    """
    if isinstance(stream, QuaExternalOutgoingStream):
        # Validation of data type is done inside _send_to_opnic_stream
        _send_to_opnic_stream(stream, data)

    elif isinstance(stream, ResultStreamSource):
        validate_scalar_of_any_type(data)
        try:
            if stream.dtype is not None:
                data = stream.dtype(data)  # Casting to the data type that was configured for the stream
            save(cast(ScalarOfAnyType, data), stream)
        except SaveToAdcTraceException:
            raise SaveToAdcTraceException("`send` cannot be used to for adc_trace streams.")
    else:
        raise QmQuaException(f"Unsupported stream type: {type(stream).__name__}.")
