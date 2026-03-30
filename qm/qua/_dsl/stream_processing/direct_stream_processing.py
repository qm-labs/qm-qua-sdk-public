from collections import Counter
from typing import Dict, Type, Optional, cast

from qm.type_hinting import NumberT
from qm.grpc.qm.pb import inc_qua_pb2
from qm.exceptions import QmQuaException
from qm.qua._dsl.scope_functions import stream_processing
from qm.qua._scope_management.scopes_manager import scopes_manager
from qm.qua._dsl.variable_handling import save, declare, _get_save_statement
from qm.qua._scope_management._core_scopes import _LoopScope, _PythonNativeScope
from qm.qua._dsl.streams.output_streams.declare_output_stream import declare_output_stream
from qm.qua._dsl.stream_processing.stream_processing import ResultStream, ResultStreamSource
from qm.qua._dsl.stream_processing.direct_stream_processing_interface import DirectStreamSourceInterface

STREAM_NAME_SEPARATOR = "__"


class DirectStreamSource(DirectStreamSourceInterface[NumberT]):
    @classmethod
    def get_existing_direct_streams(
        cls,
        stream_name: str,
        var_type: Type[NumberT],
        init_value: Optional[NumberT],
        auto_buffer: bool = False,
        average_axes: Optional[list[str]] = None,
    ) -> "DirectStreamSource[NumberT]":
        """Get existing streams associated with this DirectStreamSource."""
        matching_stream = [
            stream
            for stream in scopes_manager.program_scope.auto_processing_streams
            if stream.stream_name == stream_name
        ]

        # add axis to average stream if exist
        # doing it here as native context is duplicating the get call but not the init call
        if average_axes:
            for scope in scopes_manager.scope_stack:
                if isinstance(scope, _LoopScope):
                    if scope.name in average_axes:
                        scope.add_averaged_stream(stream_name)

        if len(matching_stream) == 1:
            return cast("DirectStreamSource[NumberT]", matching_stream[0])
        elif len(matching_stream) > 1:
            raise QmQuaException(f"Multiple DirectStreamSource found with the same stream name '{stream_name}'.")
        else:
            stream = cls(
                stream_name=stream_name,
                var_type=var_type,
                init_value=init_value,
                auto_buffer=auto_buffer,
                average_axes=average_axes,
            )

            # add to auto stream processing
            scopes_manager.program_scope.add_auto_processing_stream(stream)
            return stream

    def __init__(
        self,
        stream_name: str,
        var_type: Type[NumberT],
        init_value: Optional[NumberT],
        auto_buffer: bool = False,
        average_axes: Optional[list[str]] = None,
    ) -> None:

        # declare the variable
        if init_value is not None:
            qua_var = declare(var_type, init_value)
        else:
            qua_var = declare(var_type)

        super().__init__(qua_var.unwrapped_scalar.name, var_type, init_value=init_value)  # type: ignore[arg-type]
        self._streams: Dict[str, ResultStreamSource] = {}
        self._stream_name = stream_name

        self._auto_buffer = auto_buffer
        self._average_axes = average_axes if average_axes is not None else []
        self._save_calls: Counter[str] = Counter()
        self._calculate_buffers()

    @property
    def stream_name(self) -> str:
        return self._stream_name

    @property
    def stream_full_name(self) -> str:
        """Get the stream name, potentially modified by native loop contexts."""
        stream_full_name = self.stream_name
        # Append native loop contexts to the stream name
        native_contexts_values = [
            scope.current_value_name
            for scope in scopes_manager.scope_stack
            if isinstance(scope, _PythonNativeScope) and scope.name not in self._average_axes
        ]
        if len(native_contexts_values) > 0:
            stream_full_name = STREAM_NAME_SEPARATOR.join([stream_full_name] + native_contexts_values)
        return stream_full_name

    def get_stream(self) -> ResultStreamSource:
        """
        Get or create the stream associated with DirectStreamSource for current scope.
        """
        stream_full_name = self.stream_full_name
        if stream_full_name not in self._streams:
            self._streams[stream_full_name] = declare_output_stream()
        return self._streams[stream_full_name]

    def stream_processing(self, current_processed_streams: set[str]) -> None:
        """
        Process and save the stream associated with DirectStreamSource.

        Mutates current_processed_streams in place, adding the names of streams processed.

        Args:
            current_processed_streams: Set of stream names already processed in the current context.
        """
        with stream_processing():
            for stream_full_name, stream in self._streams.items():
                if stream_full_name not in current_processed_streams:
                    # Mark the stream as processed
                    current_processed_streams.add(stream_full_name)
                    save_object: ResultStream = stream
                    # Apply buffering and averaging if auto_buffer is enabled
                    if self._auto_buffer:
                        if self._buffers:
                            buffers = list(self._buffers)
                            buffers[-1] *= self._save_calls[stream_full_name]

                            if self.skip_first_buffer:
                                buffers = buffers[1:]

                            if len(buffers) > 0:
                                save_object = save_object.buffer(*buffers)

                        # Apply averaging if average_axes is specified
                        if len(self._average_axes) > 0:
                            save_object = save_object.average()

                    if self._use_save_all:
                        save_object.save_all(stream_full_name)
                    else:
                        save_object.save(stream_full_name)

    def save(self) -> None:
        """Save the variable to its associated stream."""
        self._save_calls[self.stream_full_name] += 1
        save(self, self.get_stream())

    def get_save_statement(self) -> inc_qua_pb2.QuaProgram.AnyStatement:
        """Get the save statement for saving the variable to its associated stream."""
        self._save_calls[self.stream_full_name] += 1
        return _get_save_statement(self, self.get_stream())

    def _calculate_buffers(self) -> None:
        """
        Calculate buffer sizes and average dimensions based on the current scope stack.
        """
        buffers: list[int] = []
        if self._auto_buffer:
            axes_to_average = self._average_axes
            for scope in scopes_manager.scope_stack:
                if isinstance(scope, _PythonNativeScope):
                    # skip native scopes for buffering as they are handled in the stream name
                    if scope.name in axes_to_average:
                        raise QmQuaException(f"Auto buffering cannot average over native iterator '{scope.name}'.")
                    continue

                elif isinstance(scope, _LoopScope):
                    scope_name = scope.name
                    scope_size = scope.size
                    if scope_name is None or scope_size is None:
                        raise QmQuaException(
                            "Auto buffering requires all enclosing loops to have a name and size defined."
                        )
                    # determine if we need to average over this axis
                    if scope_name not in axes_to_average:
                        buffers.append(scope_size)
                    elif buffers:
                        raise QmQuaException(
                            f"Cannot average over '{scope_name}' because non-averaged loop scopes "
                            f"exist before it. All qua iterables averaged axes must be outermost in the loop nesting."
                        )

        self.skip_first_buffer = len(buffers) > 0 and len(self._average_axes) == 0
        self._use_save_all = len(self._average_axes) == 0
        self._buffers = buffers


def declare_with_stream(
    t: type[NumberT],
    stream_name: str,
    value: Optional[NumberT] = None,
    auto_buffer: bool = True,
    average_axes: Optional[list[str]] = None,
) -> DirectStreamSource[NumberT]:
    """
    Declare a QUA variable that is automatically saved to a result stream.

    The returned object can be used anywhere the declared QUA variable can be
    used, including assignments and measurement processes. During
    [stream_processing][qm.qua.stream_processing], the saved values are emitted
    to ``stream_name``.

    When ``auto_buffer=True``, buffering is derived from the enclosing named
    QUA loops. Native iterables are not buffered; their current values are
    appended to the saved stream name instead. When no averaging is requested,
    the outermost buffered QUA axis is left unbuffered so live plotting can
    consume the stream progressively, and the generated stream-processing step
    stores the result with ``save_all()``. When ``average_axes`` is provided,
    the named axes are reduced during generated stream processing and the final
    averaged result is stored with ``save()``.

    Args:
        t: Type of the declared variable, for example ``fixed``, ``int``, or
            ``bool``.
        stream_name: Base name of the result stream.
        value: Optional initial value for the declared variable.
        auto_buffer: If ``True``, derive buffering from the enclosing named
            QUA loops. When no averaging is requested, the first buffered QUA
            axis is left unbuffered for live plotting. Defaults to ``True``.
        average_axes: Names of QUA loop axes to average when
            ``auto_buffer=True``. When provided, the generated stream
            processing stores the reduced result with ``save()``; otherwise it
            stores the stream with ``save_all()``. Defaults to ``None``.

    Returns:
        A stream-backed QUA variable.

    Raises:
        QmQuaException: If ``average_axes`` is provided while
            ``auto_buffer`` is ``False``, if ``average_axes`` refers to a
            native iterator, if non-averaged QUA loop scopes appear before an
            averaged axis, or if auto-buffering is used inside loops without
            names or known sizes.

    Example:
        ```python
        shots = QuaIterableRange("shots", 100)

        with program() as prog:
            for shot in shots:
                I = declare_with_stream(fixed, "I", auto_buffer=True)
                Q = declare_with_stream(fixed, "Q", auto_buffer=True)
                measure(
                    "readout",
                    "rr",
                    demod.full("cos", I),
                    demod.full("sin", Q),
                )
        ```
    """
    if average_axes is not None and not auto_buffer:
        raise QmQuaException("average_axes can only be used when auto_buffer is set to True.")

    combined_stream = DirectStreamSource.get_existing_direct_streams(
        stream_name=stream_name,
        var_type=t,
        init_value=value,
        auto_buffer=auto_buffer,
        average_axes=average_axes,
    )

    return combined_stream
