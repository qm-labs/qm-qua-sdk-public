import warnings
from collections.abc import Sequence
from typing import Any, Union, Literal, Optional, cast, get_args, overload

from qm.type_hinting import NumberT
from qm.exceptions import QmQuaException
from qm.qua._dsl._type_hints import OneOrMore
from qm.qua._dsl.streams.common import StreamEndpoints
from qm.qua._scope_management.scopes_manager import scopes_manager
from qm.qua._dsl.variable_handling import _standardize_value_and_size
from qm.qua._dsl.streams.external_streams import QuaStreamDirection, _declare_opnic_stream
from qm.qua._expressions import StructT, QuaArrayInputStream, QuaVariableInputStream, QuaExternalIncomingStream


def _declare_client_input_stream(
    t: type[NumberT],
    name: str,
    value: Optional[OneOrMore[Union[int, bool, float]]] = None,
    size: Optional[int] = None,
) -> Union[QuaVariableInputStream[NumberT], QuaArrayInputStream[NumberT]]:
    """Declare a QUA variable or a QUA vector to be used as an input stream from the job to the QUA program.

    Declaration is performed by declaring a python variable with the return value of this function.

    Declaration is similar to the normal QUA variable declaration. See [qm.qua.declare][] for available
    parameters.

    See [Input streams](../../Guides/features.md#input-streams) for more information.

    -- Available from QOP 2.0 --

    Example:
        ```python
        tau = declare_input_stream("client", "tau", int)
        ...
        receive_from_stream(tau)
        play('operation', 'element', duration=tau)
        ```
    """

    scope = scopes_manager.program_scope
    var = f"input_stream_{name}"

    if var in scope.declared_input_streams:
        raise QmQuaException(f"Input stream with name '{name}' already declared")

    params = _standardize_value_and_size(value, size)

    scope.add_input_stream_declaration(var)
    result = params.create_input_stream(var, t)

    scope.add_var_declaration(result.declaration_statement)

    return result


def _declare_any_input_stream(
    source: StreamEndpoints,
    stream_id: Union[int, str],
    dtype: Union[type[NumberT], type[StructT]],
    *,
    size: Optional[int] = None,
) -> Union[QuaExternalIncomingStream[StructT], QuaVariableInputStream[NumberT], QuaArrayInputStream[NumberT]]:
    if source == "client":
        # Dynamically extract valid NumberT types from TypeVar constraints
        number_types = NumberT.__constraints__  # type: ignore[misc]
        if not issubclass(dtype, tuple(number_types)):
            raise QmQuaException(
                f"Client input streams require a NumberT type (one of {', '.join(t.__name__ for t in number_types)}), "
                f"got {dtype.__name__}"
            )
        return _declare_client_input_stream(cast(type[NumberT], dtype), str(stream_id), size=size)

    elif source == "opnic":
        if size is not None and size != 1:
            raise QmQuaException("Opnic input streams currently do not support the 'size' parameter.")
        if not isinstance(stream_id, int):
            raise QmQuaException("stream_id must be an integer when declaring an opnic stream")
        return cast(
            QuaExternalIncomingStream[StructT],
            _declare_opnic_stream(cast(type[StructT], dtype), stream_id, QuaStreamDirection.INCOMING),
        )


@overload
def declare_input_stream(
    source: Literal["client"], stream_id: Union[int, str], dtype: type[NumberT]
) -> QuaVariableInputStream[NumberT]:
    """
    Declare a client input stream that carries scalar values.

    The client pushes values into the stream with [qm.jobs.base_job.QmBaseJob.push_to_input_stream][],
    and the QUA program consumes them with [qm.qua.receive_from_stream][] or
    [qm.qua.advance_input_stream][].

    Args:
        source (Literal["client"]): The endpoint type. Must be ``"client"``.
        stream_id (Union[int, str]): A unique identifier for the stream.
        dtype (type[NumberT]): The scalar type carried by the stream, such as ``int``, ``fixed``,
            ``float``, or ``bool``.
    """
    ...


@overload
def declare_input_stream(
    source: Literal["client"], stream_id: Union[int, str], dtype: type[NumberT], *, size: int
) -> QuaArrayInputStream[NumberT]:
    """
    Declare a client input stream that carries arrays.

    The client pushes arrays into the stream with [qm.jobs.base_job.QmBaseJob.push_to_input_stream][],
    and the QUA program consumes them with [qm.qua.receive_from_stream][] or
    [qm.qua.advance_input_stream][].

    Args:
        source (Literal["client"]): The endpoint type. Must be ``"client"``.
        stream_id (Union[int, str]): A unique identifier for the stream.
        dtype (type[NumberT]): The element type carried by the stream, such as ``int``, ``fixed``,
            ``float``, or ``bool``.
        size (int): The array length. Any positive integer, including ``1``, declares array data.
    """
    ...


@overload
def declare_input_stream(
    source: Literal["opnic"], stream_id: int, dtype: type[StructT]
) -> QuaExternalIncomingStream[StructT]:
    """
    Declare an incoming OPNIC packet stream.

    OPNIC streams carry packets defined by a type decorated with [qm.qua.qua_struct][].
    The QUA program receives packets with [qm.qua.receive_from_stream][] into a struct instance
    declared with [qm.qua.declare_struct][].

    Args:
        source (Literal["opnic"]): The endpoint type. Must be ``"opnic"``.
        stream_id (int): A unique integer stream ID.
        dtype (type[StructT]): The packet type carried by the stream. This must be a type decorated
            with [qm.qua.qua_struct][].
    """
    ...


# ======================================================
#  Regular input stream declaration, deprecated signature
# ======================================================


@overload
def declare_input_stream(t: type[NumberT], name: str) -> QuaVariableInputStream[NumberT]:
    ...


@overload
def declare_input_stream(t: type[NumberT], name: str, value: Literal[None], size: int) -> QuaArrayInputStream[NumberT]:
    ...


@overload
def declare_input_stream(t: type[NumberT], name: str, *, size: int) -> QuaArrayInputStream[NumberT]:
    ...


@overload
def declare_input_stream(
    t: type[NumberT], name: str, value: Union[int, bool, float]
) -> QuaVariableInputStream[NumberT]:
    ...


@overload
def declare_input_stream(
    t: type[NumberT], name: str, value: Sequence[Union[int, bool, float]]
) -> QuaArrayInputStream[NumberT]:
    ...


def declare_input_stream(
    *args: Any, **kwargs: Any
) -> Union[QuaExternalIncomingStream[StructT], QuaVariableInputStream[NumberT], QuaArrayInputStream[NumberT]]:
    """
    Declare an input stream.

    This function supports client input streams, incoming OPNIC packet streams, and a deprecated
    client-only signature.

    Args:
        args (Any): Accepts one of the following positional argument sets:
            * ``"client"``, ``stream_id``, ``dtype`` to declare a client input stream.
            * ``"client"``, ``stream_id``, ``dtype`` with ``size=...`` to declare a client input stream
              that carries arrays.
            * ``"opnic"``, ``stream_id``, ``PacketType`` to declare an incoming OPNIC packet stream.
            * ``dtype``, ``name`` for the deprecated client-only signature.

            Where:
            * ``stream_id``: A unique identifier for the stream. Client streams accept integers or strings.
              OPNIC streams require an integer stream ID.
            * ``dtype``: The scalar type carried by a client stream, such as ``int``, ``fixed``, ``float``,
              or ``bool``.
            * ``PacketType``: A type decorated with [qm.qua.qua_struct][] that defines the packet schema
              carried by an OPNIC stream.

        kwargs (Any): Supports the following keyword arguments:

            * ``size`` (int): Client streams only. If omitted, the stream carries scalar values.
              If provided, the stream carries arrays of that length. OPNIC streams do not support ``size``.
            * Deprecated client-only signature keyword arguments such as ``value`` and ``size``, with the
              same behavior as [qm.qua.declare][].

    Returns:
        The declared input stream.

    Examples:
        ```python
        tau = declare_input_stream("client", "tau_input", int)
        truth_table = declare_input_stream("client", "truth_table", bool, size=10)

        @qua_struct
        class Packet:
            data: QuaArray[int, 1]

        incoming_packet = declare_input_stream("opnic", 1, Packet)
        ```

    """
    if isinstance(args[0], str) and args[0] in get_args(StreamEndpoints):
        return _declare_any_input_stream(*args, **kwargs)
    else:
        warnings.warn(
            "The signature `declare_input_stream(t, name , ...)`, which implicitly treats the "
            "stream as a Client stream, is deprecated and will be removed in a future release. "
            'Please use `declare_input_stream("client", stream_id=name, dtype=t, ...) instead.',
            DeprecationWarning,
            stacklevel=2,
        )
        return _declare_client_input_stream(*args, **kwargs)
