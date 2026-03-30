import warnings
from typing import Union, Literal, Optional, overload

from qm.type_hinting import NumberT
from qm.exceptions import QmQuaException
from qm.utils import deprecation_message
from qm.qua._dsl.streams.common import StreamEndpoints
from qm.qua._expressions import StructT, QuaExternalOutgoingStream
from qm.qua._scope_management.scopes_manager import scopes_manager
from qm.qua._dsl.streams.external_streams import QuaStreamDirection, _declare_opnic_stream
from qm.qua._dsl.stream_processing.stream_processing import ResultStreamSource, _Configuration, _TimestampMode


def _get_stream_name(stream_id: Optional[Union[int, str]], adc_trace: Optional[bool]) -> str:
    scope = scopes_manager.program_scope
    scope.result_index += 1

    if stream_id is None:
        var = f"r{scope.result_index}"
        if adc_trace:
            var = "atr_" + var
    elif isinstance(stream_id, int):
        var = f"r{stream_id}"
    else:
        return stream_id

    return var


def declare_stream(adc_trace: Optional[bool] = None) -> "ResultStreamSource":
    """
    The old deprecated function to declare a QUA client output stream. The new function is declare_output_stream().

    For further details about the behavior of this function, please refer to the documentation of [declare_output_stream][qm.qua.declare_output_stream].

    Client output streams declared here can be written with [qm.qua.save][] or [qm.qua.send_to_stream][].
    They can also be used with ``timestamp_stream=`` and ``measure(..., adc_stream=...)``.

    Note:
        If the stream is an ADC trace, declaring it with the syntax ``declare_stream(adc_trace=True)``
        will add a buffer of length corresponding to the pulse length.

    Args:
        adc_trace: An optional boolean to indicate if the stream is an ADC trace. If not provided, it will be inferred automatically.
    """
    deprecation_message_details = "Please use declare_output_stream() instead"
    if adc_trace is not None:
        deprecation_message_details += ", and do not use the adc_trace argument, as it is no longer needed."
    else:
        adc_trace = False  # Default value

    warnings.warn(
        deprecation_message(
            "declare_stream",
            deprecated_in="1.2.4",
            removed_in="2.0.0",
            details=deprecation_message_details,
        ),
        DeprecationWarning,
        stacklevel=2,
    )

    return _declare_client_output_stream(stream_id=None, dtype=None, adc_trace=adc_trace)


def _declare_client_output_stream(
    stream_id: Optional[Union[int, str]], dtype: Optional[type], *, adc_trace: Optional[bool] = None
) -> ResultStreamSource:
    # In contrast to the deprecated declare_stream function, here stream_id can be auto generated, and adc_trace is not required.
    # We keep the adc_trace for edge cases of backwards compatibility.

    stream_name = _get_stream_name(stream_id, adc_trace)
    stream = ResultStreamSource(
        _Configuration(
            var_name=stream_name,
            timestamp_mode=_TimestampMode.Values,
            is_adc_trace=adc_trace,
            input=-1,
            auto_reshape=False,
            dtype=dtype,
        )
    )
    if stream_id is not None:
        # Register the stream only when a custom stream_id is provided. Otherwise, it is implicitly registered by internal DSL functions.
        scopes_manager.program_scope.add_stream_declaration(stream_name, stream)

    return stream


@overload
def declare_output_stream(
    target: Literal["client"] = "client",
    stream_id: Optional[Union[int, str]] = None,
    dtype: Optional[type] = None,
    *,
    adc_trace: Optional[bool] = None,
) -> ResultStreamSource:
    """
    Declare a client output stream.

    Client output streams are written with [qm.qua.save][] and [qm.qua.send_to_stream][].
    They can also be used with ``timestamp_stream=`` and ``measure(..., adc_stream=...)``.

    Args:
        target (Literal["client"]): The endpoint type. Must be ``"client"``. Defaults to ``"client"``.
        stream_id (Optional[Union[int, str]]): A unique identifier for the stream. If omitted, a name is
            generated automatically.
        dtype (Optional[type]): If provided, values sent with [qm.qua.send_to_stream][] are cast to this type
            before they are saved.
        adc_trace (Optional[bool]): If provided, marks the stream explicitly as an ADC trace. If omitted,
            ADC-trace behavior is inferred automatically when the stream is passed to ``measure(..., adc_stream=...)``.
    """
    ...


@overload
def declare_output_stream(
    target: Literal["opnic"], stream_id: int, dtype: type[StructT]
) -> QuaExternalOutgoingStream[StructT]:
    """
    Declare an outgoing OPNIC packet stream.

    OPNIC output streams carry packets defined by a type decorated with [qm.qua.qua_struct][].
    Send packets with [qm.qua.send_to_stream][].

    Args:
        target (Literal["opnic"]): The endpoint type. Must be ``"opnic"``.
        stream_id (int): A unique integer stream ID.
        dtype (type[StructT]): The packet type carried by the stream. This must be a type decorated with
            [qm.qua.qua_struct][].
    """
    ...


def declare_output_stream(
    target: StreamEndpoints = "client",
    stream_id: Optional[Union[int, str]] = None,
    dtype: Union[Optional[type[NumberT]], type[StructT]] = None,
    *,
    adc_trace: Optional[bool] = None,
) -> Union[QuaExternalOutgoingStream[StructT], ResultStreamSource]:
    """
    Declare an output stream.

    This function supports two endpoint types:

    - ``declare_output_stream("client", stream_id=None, dtype=None, adc_trace=None)`` declares a client output stream. Equivalent to the old ``declare_stream()``.
      Client output streams are written with [qm.qua.save][] and [qm.qua.send_to_stream][],
      and can also be used with ``timestamp_stream=`` and ``measure(..., adc_stream=...)``.
    - ``declare_output_stream("opnic", stream_id, PacketType)`` declares an outgoing OPNIC stream.
      OPNIC streams carry packets defined by a ``@qua_struct`` type and are written with
      [qm.qua.send_to_stream][].

    Args:
        target: The endpoint type that receives data from the stream, either ``"client"`` or ``"opnic"``.
            Defaults to ``"client"``.
        stream_id: A unique identifier for the stream. For client streams, this may be omitted, in which case a
            unique string is generated automatically. OPNIC streams require an integer stream ID.
        dtype: The data type carried by the stream. For client streams this can be used to cast values sent with
            [qm.qua.send_to_stream][]. If omitted for client streams, values are saved without additional casting.
            For OPNIC streams this must be a ``qua_struct`` type.
        adc_trace: Client streams only. If provided, marks the stream explicitly as an ADC trace. If omitted,
            ADC-trace behavior is inferred automatically when the stream is passed to
            ``measure(..., adc_stream=...)``. This argument is retained for backward compatibility.

    Returns:
        The declared output stream.

    Examples:
        ```python
        result_stream = declare_output_stream()
        timestamp_stream = declare_output_stream("client", "timestamps")

        @qua_struct
        class Packet:
            data: QuaArray[int, 1]

        outgoing_packet_stream = declare_output_stream("opnic", 2, Packet)
        ```

    """

    if target == "client":
        return _declare_client_output_stream(stream_id=stream_id, dtype=dtype, adc_trace=adc_trace)

    elif target == "opnic":
        # Validation of dtype is done inside declare_opnic_stream, therefore we ignore the mypy warning here.
        return _declare_opnic_stream(dtype, stream_id, QuaStreamDirection.OUTGOING)  # type: ignore[arg-type, return-value]

    else:
        raise QmQuaException(f"Unsupported target for output stream: {target!r}")
