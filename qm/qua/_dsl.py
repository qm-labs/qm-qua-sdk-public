import abc
import logging
import warnings
import dataclasses
from enum import Enum
from types import TracebackType
from dataclasses import dataclass
from typing_extensions import Literal
from collections.abc import Collection
from collections.abc import Iterable as IterableClass
from typing import Any, Set, Dict, List, Type, Tuple, Union, Generic, Mapping, Optional, Sequence, cast, overload

import betterproto
import numpy as np
from betterproto.lib.google.protobuf import Value, ListValue

from qm._loc import _get_loc
from qm.program import Program
from qm.exceptions import QmQuaException
from qm.utils import deprecation_message
from qm.type_hinting import Number, NumberT
from qm.api.models.capabilities import QopCaps
from qm.program._ResultAnalysis import _ResultAnalysis
from qm.qua._stream_processing_map_functions import MapFunctions
from qm.qua._stream_processing_utils import _ARRAY_SYMBOL, create_array
from qm.qua.AnalogMeasureProcess import RawTimeTagging as AnalogRawTimeTagging
from qm.program.StatementsCollection import PortConditionedStatementsCollection
from qm.qua.DigitalMeasureProcess import RawTimeTagging as DigitalRawTimeTagging
from qm.qua.DigitalMeasureProcess import Counting as DigitalMeasureProcessCounting
from qm.program.StatementsCollection import StatementsCollection as _StatementsCollection
from qm.utils.types_utils import collection_has_type_int, collection_has_type_bool, collection_has_type_float
from qm.qua._dsl_specific_type_hints import (
    ChirpType,
    OneOrMore,
    ChirpUnits,
    AmpValuesType,
    PlayPulseType,
    ConvolutionMode,
    MeasurePulseType,
    MessageExpressionType,
)
from qm.qua._stream_processing_function_classes import (
    FFT,
    DotProduct,
    Convolution,
    BooleanToInt,
    FunctionBase,
    TupleMultiply,
    TupleDotProduct,
    MultiplyByScalar,
    MultiplyByVector,
    TupleConvolution,
)
from qm.qua.AnalogMeasureProcess import (
    BareIntegration,
    BasicIntegration,
    DemodIntegration,
    DualMeasureProcess,
    HighResTimeTagging,
    DualBareIntegration,
    ScalarProcessTarget,
    VectorProcessTarget,
    DualDemodIntegration,
    MeasureProcessAbstract,
    SlicedAnalogTimeDivision,
    AccumulatedAnalogTimeDivision,
    MovingWindowAnalogTimeDivision,
)
from qm.qua._expressions import (
    QuaIO,
    Scalar,
    Vector,
    QuaScalar,
    QuaVariable,
    QuaArrayCell,
    QuaBroadcast,
    QuaExpression,
    ScalarOfAnyType,
    QuaArrayVariable,
    QuaFunctionOutput,
    QuaArrayInputStream,
    QuaVariableInputStream,
    fixed,
    literal_int,
    literal_bool,
    literal_real,
    to_scalar_pb_expression,
    create_qua_scalar_expression,
)
from qm.grpc.qua import (
    QuaProgramChirp,
    QuaProgramElseIf,
    QuaProgramRampPulse,
    QuaProgramChirpUnits,
    QuaProgramIfStatement,
    QuaProgramAnyStatement,
    QuaProgramForStatement,
    QuaProgramVarRefExpression,
    QuaProgramFunctionExpression,
    QuaProgramAnyScalarExpression,
    QuaProgramAssignmentStatement,
    QuaProgramStatementsCollection,
    QuaProgramArrayVarRefExpression,
    QuaProgramFunctionExpressionOrFunction,
    QuaProgramFunctionExpressionAndFunction,
    QuaProgramFunctionExpressionXorFunction,
    QuaProgramFunctionExpressionScalarOrVectorArgument,
)

_Variable = QuaVariable  # This alias is for supporting an import that appears in QUA-lang tools

_TIMESTAMPS_LEGACY_SUFFIX = "_timestamps"

_block_stack: List["_BaseScope"] = []

logger = logging.getLogger(__name__)

StreamType = Union[str, "_ResultSource"]
"""A type for a stream object in QUA."""

_RESULT_SYMBOL = "@re"

DEFAULT_OUT1 = "out1"
DEFAULT_OUT2 = "out2"


def program() -> "_ProgramScope":
    """Create a QUA program.

    Used within a context manager, the program is defined in the code block
    below ``with`` statement.

    Statements in the code block below are played as soon as possible, meaning that an instruction
    will be played immediately unless it is dependent on a previous instruction.
    Additionally, commands output to the same elements will be played sequentially,
    and to different elements will be played in parallel.
    An exception is that pulses will be implicitly aligned at the end of each [`for_`][qm.qua._dsl.for_] loop iteration.

    The generated ``program_name`` object is used as an input to the execution or compilation functions.

    Example:
        ```python
        with program() as program_name:
            play('pulse1', 'element1')
            wait('element1')

        qmm = QuantumMachinesManager(...)
        qm = qmm.open_qm(...)
        qm.execute(program_name)
        ```
    """
    return _ProgramScope(Program())


def play(
    pulse: PlayPulseType,
    element: str,
    duration: Optional[Scalar[int]] = None,
    condition: Optional[Scalar[bool]] = None,
    chirp: Optional[ChirpType] = None,
    truncate: Optional[Scalar[int]] = None,
    timestamp_stream: Optional[StreamType] = None,
    continue_chirp: bool = False,
    target: str = "",
) -> None:
    r"""Play a `pulse` based on an 'operation' defined in `element`.

    The pulse will be modified according to the properties of the element
    (see detailed explanation about pulse modifications below),
    and then played to the OPX output(s) defined to be connected
    to the input(s) of the element in the configuration.

    Args:
        pulse (str): The name of an `operation` to be performed, as
            defined in the element in the quantum machine configuration.
            Can also be a [ramp][qm.qua._dsl.ramp] function or be multiplied by an
            [ramp][qm.qua._dsl.ramp].
        element (str): The name of the element, as defined in the
            quantum machine configuration.
        duration (Union[int,QUA variable of type int]): The time to play
            this pulse in units of the clock cycle (4ns). If not
            provided, the default pulse duration will be used. It is
            possible to dynamically change the duration of both constant
            and arbitrary pulses. Arbitrary pulses can only be stretched,
            not compressed.
        chirp (ChirpType): Allows to perform piecewise linear sweep
            of the element’s intermediate frequency in time. Input
            should be a tuple, with the 1st element being a list of
            rates and the second should be a string with the units.
            The units can be either: ‘Hz/nsec’, ’mHz/nsec’, ’uHz/nsec’,
            ’pHz/nsec’ or ‘GHz/sec’, ’MHz/sec’, ’KHz/sec’, ’Hz/sec’, ’mHz/sec’.
        truncate (Union[int, QUA variable of type int]): Allows playing
            only part of the pulse, truncating the end. If provided,
            will play only up to the given time in units of the clock
            cycle (4ns).
        condition (A logical expression to evaluate.): Will play the operation only if the condition is true.
            The play command will take the same amount of time regardless of the condition (If false, would wait instead).
            Prior to QOP 2.2, only the analog part was conditioned, i.e., any digital pulses associated
            with the operation would always play.
        timestamp_stream (Union[str, _ResultSource]): (Supported from
            QOP 2.2) Adding a `timestamp_stream` argument will save the
            time at which the operation occurred to a stream. If the
            `timestamp_stream` is a string ``label``, then the timestamp
            handle can be retrieved with
            [`JobResults.get`][qm.results.streaming_result_fetcher.StreamingResultFetcher.get] with the same
            ``label``.
        continue_chirp (bool): When performing a chirp, passing `True` will make the chirp continue until a new chirp command is given. Defaults to `False`. Not available in OPX1.0.
        target (str): Allows to select a specific input of the element to play the pulse on. Only allowed (and required) when the element is defined with `singleInputCollection`.

    Note:
        Arbitrary waveforms cannot be compressed and can only be expanded up to
        $2^{24}-1$ clock cycles (67ms). Unexpected output will occur if a duration
        outside the range is given.
        See [Dynamic pulse duration](../../Guides/features.md#dynamic-pulse-duration)
        in the documentation for further information.

    Note:
        When using chirp, it is possible to add a flag "continue_chirp=True" to the play command.
        When this flag is set, the internal oscillator will continue the chirp even after the play command had ended.
        See the `chirp documentation [chirp documentation](../../Guides/features.md#frequency-chirp)
        for more information.

    Example:
        ```python
        with program() as prog:
            v1 = declare(fixed)
            assign(v1, 0.3)
            play('pulse1', 'element1')
            play('pulse1' * amp(0.5), 'element1')
            play('pulse1' * amp(v1), 'element1')
            play('pulse1' * amp(0.9, v1, -v1, 0.9), 'element_iq_pair')
            time_stream = declare_stream()
            # Supported on QOP2.2+
            play('pulse1', 'element1', duration=16, timestamp_stream='t1')
            play('pulse1', 'element1', duration=16, timestamp_stream=time_stream)
            with stream_processing():
                stream.buffer(10).save_all('t2')
        ```
    """
    body = _get_scope_as_blocks_body()

    body.play(
        pulse,
        element,
        duration=to_scalar_pb_expression(duration) if duration is not None else None,
        condition=to_scalar_pb_expression(condition) if condition is not None else None,
        target=target,
        chirp=_standardize_chirp(chirp, continue_chirp),
        truncate=to_scalar_pb_expression(truncate) if truncate is not None else None,
        timestamp_label=_standardize_timestamp_label(timestamp_stream),
    )


def _standardize_chirp(chirp: Optional[ChirpType], continue_chirp: bool) -> Optional[QuaProgramChirp]:
    if chirp is None:
        return None

    if len(chirp) == 2:
        chirp_var, chirp_units = chirp
        chirp_times = None
    elif len(chirp) == 3:
        chirp_var, chirp_times, chirp_units = chirp
    else:
        raise QmQuaException("chirp must be tuple of 2 or 3 values")
    chirp_times_list = [int(x) for x in chirp_times] if chirp_times is not None else None
    if isinstance(chirp_var, IterableClass):
        chirp_var = [int(x) for x in chirp_var]
        chirp_var = declare(int, value=chirp_var)

    chirp_obj = QuaProgramChirp()
    chirp_obj.continue_chirp = continue_chirp
    if chirp_times_list is not None:
        chirp_obj.times.extend(chirp_times_list)
    if isinstance(chirp_var, QuaArrayVariable):
        chirp_obj.array_rate = chirp_var.unwrapped
    else:
        chirp_obj.scalar_rate = to_scalar_pb_expression(chirp_var)

    units_mapping: Mapping[ChirpUnits, int] = {
        "Hz/nsec": QuaProgramChirpUnits.HzPerNanoSec,
        "GHz/sec": QuaProgramChirpUnits.HzPerNanoSec,
        "mHz/nsec": QuaProgramChirpUnits.mHzPerNanoSec,
        "MHz/sec": QuaProgramChirpUnits.mHzPerNanoSec,
        "uHz/nsec": QuaProgramChirpUnits.uHzPerNanoSec,
        "KHz/sec": QuaProgramChirpUnits.uHzPerNanoSec,
        "nHz/nsec": QuaProgramChirpUnits.nHzPerNanoSec,
        "Hz/sec": QuaProgramChirpUnits.nHzPerNanoSec,
        "pHz/nsec": QuaProgramChirpUnits.pHzPerNanoSec,
        "mHz/sec": QuaProgramChirpUnits.pHzPerNanoSec,
    }

    if chirp_units in units_mapping:
        chirp_obj.units = units_mapping[chirp_units]  # type: ignore[assignment]
    else:
        raise QmQuaException(f'unknown units "{chirp_units}"')
    return chirp_obj


def _standardize_timestamp_label(timestamp_stream: Optional[StreamType]) -> Optional[str]:
    timestamp_label = None
    if isinstance(timestamp_stream, str):
        scope = _get_root_program_scope()
        scope.program.add_used_capability(QopCaps.command_timestamps)
        timestamp_label = scope.declare_save(timestamp_stream).get_var_name()
    elif isinstance(timestamp_stream, _ResultSource):
        _get_root_program_scope().program.add_used_capability(QopCaps.command_timestamps)
        timestamp_label = timestamp_stream.get_var_name()
    return timestamp_label


def pause() -> None:
    """Pause the execution of the job until [qm.jobs.running_qm_job.RunningQmJob.resume][] is called.

    The quantum machines freezes on its current output state.
    """
    body = _get_scope_as_blocks_body()
    body.pause()


def update_frequency(
    element: str,
    new_frequency: Scalar[int],
    units: str = "Hz",
    keep_phase: bool = False,
) -> None:
    """Dynamically update the frequency of the oscillator associated with a given `element`.

    This changes the frequency from the value defined in the quantum machine configuration.

    The behavior of the phase (continuous vs. coherent) is controlled by the ``keep_phase`` parameter and
    is discussed in [the documentation](../../Introduction/qua_overview.md#frequency-and-phase-transformations).

    Args:
        element (str): The element associated with the oscillator whose
            frequency will be changed
        new_frequency (int): The new frequency value to set in units set
            by ``units`` parameter. In steps of 1.
        units (str): units of new frequency. Useful when sub-Hz
            precision is required. Allowed units are "Hz", "mHz", "uHz",
            "nHz", "pHz"
        keep_phase (bool): Determine whether phase will be continuous
            through the change (if `True`) or it will be coherent,
            only the frequency will change (if `False`).

    Example:
        ```python
        with program() as prog:
            update_frequency("q1", 4e6) # will set the frequency to 4 MHz

            ### Example for sub-Hz resolution
            update_frequency("q1", 100.7) # will set the frequency to 100 Hz (due to casting to int)
            update_frequency("q1", 100700, units='mHz') # will set the frequency to 100.7 Hz
        ```
    """
    body = _get_scope_as_blocks_body()
    body.update_frequency(element, to_scalar_pb_expression(new_frequency), units, keep_phase)


def update_correction(
    element: str,
    c00: Scalar[float],
    c01: Scalar[float],
    c10: Scalar[float],
    c11: Scalar[float],
) -> None:
    """Updates the correction matrix used to overcome IQ imbalances of the IQ mixer for the next pulses
    played on the element

    Note:

        Make sure to update the correction after you called [`update_frequency`][qm.qua._dsl.update_frequency]

    Note:

        Up to QOP 3.3, calling ``update_correction`` will also reset the frame of the oscillator associated with the element.

    Args:
        element (str): The element associated with the oscillator whose
            correction matrix will change
        c00 (Union[float,QUA variable of type real]): The top left
            matrix element
        c01 (Union[float,QUA variable of type real]): The top right
            matrix element
        c10 (Union[float,QUA variable of type real]): The bottom left
            matrix element
        c11 (Union[float,QUA variable of type real]): The bottom right
            matrix element

    Example:
        ```python
        with program() as prog:
            update_correction("q1", 1.0, 0.5, 0.5, 1.0)
        ```
    """
    body = _get_scope_as_blocks_body()
    body.update_correction(
        element,
        to_scalar_pb_expression(c00),
        to_scalar_pb_expression(c01),
        to_scalar_pb_expression(c10),
        to_scalar_pb_expression(c11),
    )


def set_dc_offset(element: str, element_input: str, offset: Scalar[float]) -> None:
    """Set the DC offset of an element's input to the given value. This value will remain the DC offset until changed or
    until the Quantum Machine is closed.
    The offset value remains until it is changed or the Quantum Machine is closed.

    -- Available from QOP 2.0 --

    Args:
        element: The element to update its DC offset
        element_input: The desired input of the element, can be 'single'
            for a 'singleInput' element or 'I' or 'Q' for a 'mixInputs'
            element
        offset: The offset to set
    """

    body = _get_scope_as_blocks_body()
    body.set_dc_offset(element, element_input, to_scalar_pb_expression(offset))


@overload
def measure(
    pulse: MeasurePulseType,
    element: str,
    *outputs: Union[Tuple[str, QuaVariable[float]], Tuple[str, str, QuaVariable[float]], MeasureProcessAbstract],
    timestamp_stream: Optional[StreamType] = None,
    adc_stream: Optional[StreamType] = None,
) -> None:
    pass


@overload
def measure(
    pulse: MeasurePulseType,
    element: str,
    stream: Optional[StreamType],
    *outputs: Union[Tuple[str, QuaVariable[float]], Tuple[str, str, QuaVariable[float]], MeasureProcessAbstract],
    timestamp_stream: Optional[StreamType] = None,
    adc_stream: Optional[StreamType] = None,
) -> None:
    pass


def measure(  # type: ignore[misc]
    pulse: MeasurePulseType,
    element: str,
    *outputs: Union[
        Tuple[str, QuaVariable[float]],
        Tuple[str, str, QuaVariable[float]],
        MeasureProcessAbstract,
        Optional[StreamType],
    ],
    stream: Optional[StreamType] = None,
    timestamp_stream: Optional[StreamType] = None,
    adc_stream: Optional[StreamType] = None,
) -> None:
    """Perform a measurement of `element` using `pulse` based on 'operation' as defined in the 'element'.

    An element for which a measurement is applied must have outputs defined in the configuration.

    A measurement consists of:

    1. playing an operation to the element (identical to a :func:`play` statement)

    2. waiting for a duration of time defined as the ``time_of_flight``
       in the configuration of the element, and then sampling
       the returning pulse.
       The OPX input to be sampled is defined in the configuration of the element.

    3. Processing the acquired data according to a parameter defined in the measure command,
        including Demodulation, Integration and Time Tagging.

    For a more detailed description of the measurement operation, see
    [Measure Statement Features](../../Guides/features.md#measure-statement-features)

    Args:
        pulse (str): The name of an `operation` to be performed, as defined in the element in the quantum machine configuration.
            Pulse must have a ``measurement`` operation. Can also be multiplied by an [amp][qm.qua._dsl.amp].
        element (str): name of the element, as defined in the quantum machine configuration. The element must have outputs.
        *outputs (tuple): A parameter specifying the processing to be done on the ADC data, there are multiple options available, including demod(), integration() & time_tagging().
        stream (Union[str, _ResultSource]): Deprecated and replaced by `adc_stream`.
        timestamp_stream (Union[str, _ResultSource]): (Supported from QOP 2.2) Adding a `timestamp_stream` argument will save the time at which the operation occurred to a stream.
            If the `timestamp_stream` is a string ``label``, then the timestamp handle can be retrieved with [qm.results.streaming_result_fetcher.StreamingResultFetcher][] with the same ``label``.
        adc_stream (Union[str, _ResultSource]): The stream variable into which the raw ADC data will be saved.
            You can receive the results with [qm.QmJob.result_handles.get("name")][qm.jobs.running_qm_job.RunningQmJob.result_handles].
            A string name can also be used. In this case, the name of the result
            handle should be suffixed by ``_input1`` for data from analog input 1 and ``_input2`` for data from analog input 2.

            If ``adc_stream`` is set to ``None``, nothing will not be saved.
            The raw results will be saved as long as the digital pulse that is played with pulse is high.

            !!! Warning:

                Streaming adc data without declaring the stream with `declare_stream(adc_trace=true)` might cause performance issues

    Example:
        ```python
        with program() as prog:
            I = declare(fixed)
            Q = declare(fixed)
            adc_st = declare_stream(adc_trace=True)

            # measure by playing 'meas_pulse' to element 'resonator', do not save raw results.
            # demodulate data from "out1" port of 'resonator' using 'cos_weights' and store result in I, and also
            # demodulate data from "out1" port of 'resonator' using 'sin_weights' and store result in Q
            measure('meas_pulse', 'resonator', demod.full("cos_weights", I, "out1"), demod.full("sin_weights", Q, "out1"))

            # measure by playing 'meas_pulse' to element 'resonator', save raw results to `adc_st`
            # demodulate data from 'out1' port of 'resonator' using 'optimized_weights' and store result in I
            measure('meas_pulse', 'resonator', adc_st, demod.full("optimized_weights", I, "out1"))
            with stream_processing():
                adc_st.input1().save_all("raw_adc_stream")

        from qm import QuantumMachinesManager
        qm = QuantumMachinesManager().open_qm(config)
        job = qm.execute(prog)
        # ... we wait for the results to be ready...
        job.result_handles.wait_for_all_values()
        # raw results can be retrieved as follows (here job is a QmJob object:
        raw_I_handle = job.result_handles.get("raw_adc_stream")
        ```

    """
    if stream is None:
        if len(outputs) > 0:
            if isinstance(outputs[0], (_ResultSource, str)):
                adc_stream = outputs[0]
                if isinstance(adc_stream, _ResultSource):
                    warnings.warn(
                        "Saving an adc stream now requires defining it at the end of the measure command with the `adc_stream` argument, e.g. `adc_stream=adc_st`. The current syntax is deprecated and will be removed in a 1.3.",
                        DeprecationWarning,
                        stacklevel=2,
                    )
                else:
                    warnings.warn(
                        f"Saving an adc stream now requires defining it at the end of the measure command with the `adc_stream` argument, e.g. `adc_stream='{adc_stream}'`. The current syntax is deprecated and will be removed in a 1.3.",
                        DeprecationWarning,
                        stacklevel=2,
                    )
                outputs = outputs[1:]
            elif outputs[0] is None:
                warnings.warn(
                    "Putting `None` to indicate no adc streaming is no longer required, please remove it from the measure call.",
                    DeprecationWarning,
                    stacklevel=2,
                )
                outputs = outputs[1:]
    else:
        warnings.warn(
            "The `stream` argument is deprecated and will be removed in a 1.3. Use the `adc_stream` argument instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        adc_stream = stream

    body = _get_scope_as_blocks_body()

    measure_process: List[MeasureProcessAbstract] = []
    for i, output in enumerate(outputs):
        if isinstance(output, tuple):
            if len(output) == 2:
                iw, target = output
                measure_process.append(demod.full(iw, target, ""))
            elif len(output) == 3:
                iw, element_output, target = output
                measure_process.append(demod.full(iw, target, element_output))
            else:
                raise QmQuaException(
                    "Each output must be a tuple of (integration weight, output name, variable name), but output "
                    + str(i + 1)
                    + " is invalid"
                )
        elif isinstance(output, MeasureProcessAbstract):
            measure_process.append(output)
        else:
            raise TypeError(f"Invalid output type: {type(output)}")

    _adc_stream: Optional[_ResultSource] = None
    if isinstance(adc_stream, str):
        _adc_stream = _get_root_program_scope().declare_legacy_adc(adc_stream)
    else:
        if adc_stream is not None and (not isinstance(adc_stream, _ResultSource)):
            raise QmQuaException("stream object is not of the right type")
        _adc_stream = adc_stream

    if _adc_stream and not _adc_stream.is_adc_trace:
        logger.warning(
            "Streaming adc data without declaring the stream with "
            "`declare_stream(adc_trace=true)` might cause performance issues"
        )
    timestamp_label = None
    if isinstance(timestamp_stream, str):
        scope = _get_root_program_scope()
        scope.program.add_used_capability(QopCaps.command_timestamps)
        timestamp_label = scope.declare_save(timestamp_stream).get_var_name()
    elif isinstance(timestamp_stream, _ResultSource):
        _get_root_program_scope().program.add_used_capability(QopCaps.command_timestamps)
        timestamp_label = timestamp_stream.get_var_name()
    body.measure(
        pulse,
        element,
        _adc_stream,
        timestamp_label=timestamp_label,
        *[x.unwrapped for x in measure_process],
    )


def align(*elements: str) -> None:
    """Align several elements together.

    All the elements referenced in `elements` will wait for all the others to
    finish their currently running statement.

    If no arguments are given, the statement will align all the elements used in the program.

    Args:
        *elements (str): a single element, multiple elements, or none
    """
    body = _get_scope_as_blocks_body()
    body.align(*elements)


def reset_phase(element: str) -> None:
    warnings.warn(
        deprecation_message(
            method="reset_phase",
            deprecated_in="1.2.2",
            removed_in="1.4.0",
            details="reset_if_phase instead.",
        ),
        DeprecationWarning,
        stacklevel=2,
    )
    reset_if_phase(element)


def reset_if_phase(element: str) -> None:
    r"""
    Resets the intermediate frequency phase of the oscillator associated with `element`,
    setting the phase of the next pulse to absolute zero.
    This sets the phase of the currently playing intermediate frequency
    to the value it had at the beginning of the program (t=0).

    Note:

        * The phase will only be set to zero when the next play or align command is executed on the element.
        * Reset phase will only reset the phase of the intermediate frequency (:math:`\\omega_{IF}`) currently in use.

    Args:
        element: an element
    """
    body = _get_scope_as_blocks_body()
    body.reset_if_phase(element)


def reset_global_phase() -> None:
    """
    Resets the global phase of all the elements in the program.
    This will reset both the intermediate frequency phase and the upconverters/downconverters in use.
    """
    body = _get_scope_as_blocks_body()
    body.reset_global_phase()


def ramp_to_zero(element: str, duration: Optional[int] = None) -> None:
    r"""Starting from the last DC value, gradually lowers the DC to zero for `duration` *4nsec

    If `duration` is None, the duration is taken from the element's config

    Warning:
        This feature does not protect from voltage jumps. Those can still occur, i.e. when the data sent to the
        analog output is outside the range -0.5 to $0.5 - 2^{16}$ and thus will have an overflow.

    Args:
        element (str): element for ramp to zero
        duration (Union[int,None]): time , `in multiples of 4nsec`.
            Range: [4, $2^{24}$] in steps of 1, or `None` to take
            value from config
    """
    body = _get_scope_as_blocks_body()
    duration = duration if duration is None else int(duration)
    body.ramp_to_zero(element, duration)


def wait(duration: Scalar[int], *elements: str) -> None:
    r"""Wait for the given duration on all provided elements without outputting anything.
    Duration is in units of the clock cycle (4ns)

    Args:
        duration (Union[int,QUA variable of type int]): time to wait in
            units of the clock cycle (4ns). Range: [4, $2^{31}-1$]
            in steps of 1.
        *elements (Union[str,sequence of str]): elements to wait on

    Warning:

        In case the value of this is outside the range above, unexpected results may occur.

    Note:

        The purpose of the `wait` operation is to add latency. In most cases, the
        latency added will be exactly the same as that specified by the QUA variable or
        the literal used. However, in some cases an additional computational latency may
        be added. If the actual wait time has significance, such as in characterization
        experiments, the actual wait time should always be verified with a simulator.
    """
    body = _get_scope_as_blocks_body()
    body.wait(to_scalar_pb_expression(duration), *elements)


def wait_for_trigger(
    element: str,
    pulse_to_play: Optional[str] = None,
    trigger_element: Optional[Union[Tuple[str, str], str]] = None,
    time_tag_target: Optional[QuaVariable[int]] = None,
) -> None:
    """Wait for an external trigger on the provided element.

    During the command the OPX will play the pulse supplied by the ``pulse_to_play`` parameter

    Args:
        element (str): element to wait on
        pulse_to_play (str): the name of the pulse to play on the
            element while waiting for the external trigger. Must be a
            constant pulse. Default None, no pulse will be played.
        trigger_element (Union[str, tuple]): Available only with the
            OPD. The triggered element. See further details in the note.
        time_tag_target (QUA variable of type int): Available only with
            the OPD. The time at which the trigger arrived relative to
            the waiting start time. In ns.

    Warning:
        In the OPX - The maximum allowed voltage value for the digital trigger is 1.8V. A voltage higher than this can damage the
        controller.

        In the OPX+ and with the OPD - The maximum allowed voltage is 3.3V.

    Note:
        Read more about triggering with the OPD [here](../../Hardware/dib.md#wait-for-trigger)
    """
    body = _get_scope_as_blocks_body()
    time_tag_target_pb = None if time_tag_target is None else time_tag_target.unwrapped.variable
    body.wait_for_trigger(pulse_to_play, trigger_element, time_tag_target_pb, element)


def save(var: ScalarOfAnyType, stream_or_tag: Union[str, "_ResultSource"]) -> None:
    """Stream a QUA variable, a QUA array cell, or a constant scalar.
    the variable is streamed and not immediately saved (see [Stream processing](../../Guides/stream_proc.md#stream-processing)).
    In case ``result_or_tag`` is a string, the data will be immediately saved to a result handle under the same name.

    If result variable is used, it can be used in results analysis scope see [stream_processing][qm.qua._dsl.stream_processing]
    if string tag is used, it will let you receive result with [qm.QmJob.result_handles][qm.jobs.running_qm_job.RunningQmJob.result_handles].
    The type of the variable determines the stream datatype, according to the following rule:

    - int -> int64
    - fixed -> float64
    - bool -> bool

    Note:

        Saving arrays as arrays is not currently supported. Please use a QUA for loop to save an array.

    Example:
        ```python
        # basic save
        a = declare(int, value=2)
        save(a, "a")

        # fetching the results from python (job is a QmJob object):
        a_handle = job.result_handles.get("a")
        a_data = a_handle.fetch_all()

        # save the third array cell
        vec = declare(fixed, value=[0.2, 0.3, 0.4, 0.5])
        save(vec[2], "ArrayCellSave")

        # array iteration
        i = declare(int)
        array = declare(fixed, value=[x / 10 for x in range(30)])
        with for_(i, 0, i < 30, i + 1):
            save(array[i], "array")

        # save a constant
        save(3, "a")
        ```

    Args:
        var (Union[QUA variable, a QUA array cell]): A QUA variable or a
            QUA array cell to save
        stream_or_tag (Union[str, stream variable]): A stream variable
            or string tag name to save the value under
    """
    if isinstance(stream_or_tag, str):
        result_obj = _get_root_program_scope().declare_legacy_save(stream_or_tag)
    else:
        result_obj = stream_or_tag

    if result_obj.is_adc_trace:
        raise QmQuaException("adc_trace can't be used in save")

    body = _get_scope_as_blocks_body()
    body.save(create_qua_scalar_expression(var).save_statement, result_obj)


def frame_rotation(angle: Union[Scalar[float]], *elements: str) -> None:
    r"""Shift the phase of the oscillator associated with an element by the given angle.

    This is typically used for virtual z-rotations.

    Note:
        The fixed point format of QUA variables of type fixed is 4.28, meaning the phase
        must be between $-8$ and $8-2^{28}$. Otherwise the phase value will be invalid.
        It is therefore better to use `frame_rotation_2pi()` which avoids this issue.

    Note:
        The phase is accumulated with a resolution of 16 bit.
        Therefore, *N* changes to the phase can result in a phase (and amplitude) inaccuracy of about :math:`N \cdot 2^{-16}`.
        To null out this accumulated error, it is recommended to use `reset_frame(el)` from time to time.

    Args:
        angle (Union[float, QUA variable of type fixed]): The angle to
            add to the current phase (in radians)
        *elements (str): a single element whose oscillator's phase will
            be shifted. multiple elements can be given, in which case
            all of their oscillators' phases will be shifted

    """
    if isinstance(angle, (QuaProgramArrayVarRefExpression, QuaProgramVarRefExpression)):
        raise TypeError(f"angle cannot be of type {type(angle)}")
    frame_rotation_2pi(angle * 0.15915494309189535, *elements)


def frame_rotation_2pi(angle: Scalar[float], *elements: str) -> None:
    r"""Shift the phase of the oscillator associated with an element by the given angle in units of 2pi radians.

    This is typically used for virtual z-rotations.

    Note:
        Unlike the case of frame_rotation(), this method performs the 2-pi radian wrap around of the angle automatically.

    Note:
        The phase is accumulated with a resolution of 16 bit.
        Therefore, *N* changes to the phase can result in a phase inaccuracy of about :math:`N \cdot 2^{-16}`.
        To null out this accumulated error, it is recommended to use `reset_frame(el)` from time to time.

    Args:
        angle (Union[float,QUA variable of type real]): The angle to add
            to the current phase (in $2\pi$ radians)
        *elements (str): a single element whose oscillator's phase will
            be shifted. multiple elements can be given, in which case
            all of their oscillators' phases will be shifted

    """
    body = _get_scope_as_blocks_body()
    body.z_rotation(to_scalar_pb_expression(angle), *elements)


def reset_frame(*elements: str) -> None:
    """Resets the frame of the oscillator associated with an element to 0.

    Used to reset all the frame updated made up to this statement.

    Args:
        *elements (str): a single element whose oscillator's phase will
            be reset. multiple elements can be given, in which case all
            of their oscillators' phases will be reset

    """
    body = _get_scope_as_blocks_body()
    body.reset_frame(*elements)


def fast_frame_rotation(cosine: Scalar[float], sine: Scalar[float], *elements: str) -> None:
    r"""Shift the phase of the oscillator associated with an element by applying the
    rotation matrix [[cosine, -sine],[sin, cosine]].

    This is typically used for virtual z-rotations.

    -- Available from QOP 2.2 --

    Note:
        The phase is accumulated with a resolution of 16 bit.
        Therefore, *N* changes to the phase can result in a phase (and amplitude) inaccuracy of about :math:`N \cdot 2^{-16}`.
        To null out this accumulated error, it is recommended to use `reset_frame(el)` from time to time.

    Args:
        cosine (Union[float,QUA variable of type real]): The main
            diagonal values of the rotation matrix
        sine (Union[float,QUA variable of type real]): The bottom left
            rotation matrix element and minus the top right rotation
            matrix element value
        *elements (str): A single element whose oscillator's phase will
            be shifted. multiple elements can be given, in which case
            all of their oscillators' phases will be shifted
    """
    _get_root_program_scope().program.add_used_capability(QopCaps.fast_frame_rotation)
    body = _get_scope_as_blocks_body()
    body.fast_frame_rotation(to_scalar_pb_expression(cosine), to_scalar_pb_expression(sine), *elements)


def assign(var: Union[QuaArrayCell[NumberT], QuaVariable[NumberT], QuaIO], _exp: Union[Scalar[NumberT], QuaIO]) -> None:
    """Set the value of a given QUA variable, a QUA array cell or an IO to the value of a given expression.

    Args:
        var (QUA variable): A QUA variable, a QUA array cell or an IO for which to assign.
        _exp (QUA expression): An expression for which to set the variable

    Example:
        ```python
        with program() as prog:
            v1 = declare(fixed)
            assign(v1, 1.3)
            play('pulse1' * amp(v1), 'element1')
        ```
    """
    body = _get_scope_as_blocks_body()
    body.assign(var.assignment_statement, to_scalar_pb_expression(_exp))


def switch_(expression: QuaScalar[NumberT], unsafe: bool = False) -> "_SwitchScope[NumberT]":
    """Part of the switch-case flow control statement in QUA.

    To be used with a context manager.

    The code block inside should be composed of only ``case_()`` and ``default_()``
    statements, and there should be at least one of them.

    The expression given in the ``switch_()`` statement will be evaluated and compared
    to each of the values in the ``case_()`` statements. The QUA code block following
    the ``case_()`` statement which evaluated to true will be executed. If none of the
    statements evaluated to true, the QUA code block following the ``default_()``
    statement (if given) will be executed.

    Args:
        expression: An expression to evaluate
        unsafe: If set to True, then switch-case would be more efficient
            and would produce fewer gaps. However, if an input which does
            not match a case is given, unexpected behavior will occur.
            Cannot be used with the ``default_()`` statement. Default is
            false, use with care.

    Example:
        ```python
        x=declare(int)
        with switch_(x):
            with case_(1):
                play('first_pulse', 'element')
            with case_(2):
                play('second_pulse', 'element')
            with case_(3):
                play('third_pulse', 'element')
            with default_():
                play('other_pulse', 'element')
        ```
    """
    body = _get_scope_as_blocks_body()
    return _SwitchScope(expression, body, unsafe)


def case_(case_exp: Scalar[NumberT]) -> "_BodyScope":
    """Part of the switch-case flow control statement in QUA.

    To be used with a context manager.

    Must be inside a ``switch_()`` statement.

    The expression given in the ``switch_()`` statement will be evaluated and compared
    to each of the values in the ``case_()`` statements. The QUA code block following
    the ``case_()`` statement which evaluated to true will be executed. If none of the
    statements evaluated to true, the QUA code block following the ``default_()``
    statement (if given) will be executed.

    Args:
        case_exp: A value (or expression) to compare to the expression
            in the ``switch_()`` statement

    Example:
        ```python
        x=declare(int)
        with switch_(x):
            with case_(1):
                play('first_pulse', 'element')
            with case_(2):
                play('second_pulse', 'element')
            with case_(3):
                play('third_pulse', 'element')
            with default_():
                play('other_pulse', 'element')
        ```
    """
    switch = _get_scope_as_switch_scope()
    condition = (cast(QuaScalar[NumberT], switch.expression).__eq__(case_exp)).unwrapped  # type: ignore[redundant-cast]
    if switch.if_statement is None:
        body = switch.container.if_block(condition, switch.unsafe)
        switch.if_statement = switch.container.get_last_statement()
        return _BodyScope(body)
    else:
        else_if_statement = QuaProgramElseIf(
            loc=switch.if_statement.if_.loc,
            condition=condition,
            body=QuaProgramStatementsCollection(statements=[]),
        )
        switch.if_statement.if_.elseifs.append(else_if_statement)
        return _BodyScope(_StatementsCollection(else_if_statement.body))


def default_() -> "_BaseScope":
    """Part of the switch-case flow control statement in QUA.

    To be used with a context manager.

    Must be inside a ``switch_()`` statement, and there can only be one ``default_()``
    statement.

    The expression given in the ``switch_()`` statement will be evaluated and compared
    to each of the values in the ``case_()`` statements. The QUA code block following
    the ``case_()`` statement which evaluated to true will be executed. If none of the
    statements evaluated to true, the QUA code block following the ``default_()``
    statement (if given) will be executed.

    Example:
        ```python
        x=declare(int)
        with switch_(x):
            with case_(1):
                play('first_pulse', 'element')
            with case_(2):
                play('second_pulse', 'element')
            with case_(3):
                play('third_pulse', 'element')
            with default_():
                play('other_pulse', 'element')
        ```
    """
    switch = _get_scope_as_switch_scope()
    if switch.if_statement is None:
        raise QmQuaException("must specify at least one case before 'default'.")

    if betterproto.serialized_on_wire(switch.if_statement.if_.else_):
        raise QmQuaException("only a single 'default' statement can follow a 'switch' statement")

    else_statement = QuaProgramStatementsCollection(statements=[])
    switch.if_statement.if_.else_ = else_statement
    return _BodyScope(_StatementsCollection(else_statement))


def if_(expression: Scalar[bool], unsafe: bool = False) -> "_BodyScope":
    """If flow control statement in QUA.

    To be used with a context manager.

    The QUA code block following the statement will be
    executed only if the expression given evaluates to true.

    Args:
        expression: A boolean expression to evaluate

    Example:
        ```python
        x=declare(int)
        with if_(x>0):
            play('pulse', 'element')
        ```
    """
    body = _get_scope_as_blocks_body()
    if_body = body.if_block(to_scalar_pb_expression(expression), unsafe)
    return _BodyScope(if_body)


def elif_(expression: Scalar[bool]) -> "_BodyScope":
    """Else-If flow control statement in QUA.

    To be used with a context manager.

    Must appear after an ``if_()`` statement.

    The QUA code block following the statement will be executed only if the expressions
    in the preceding ``if_()`` and ``elif_()`` statements evaluates to false and if the
    expression given in this ``elif_()`` evaluates to true.

    Args:
        expression: A boolean expression to evaluate

    Example:
        ```python
        x=declare(int)
        with if_(x>2):
            play('pulse', 'element')
        with elif_(x>-2):
            play('other_pulse', 'element')
        with else_():
            play('third_pulse', 'element')
        ```
    """
    body = _get_scope_as_blocks_body()
    last_statement = body.get_last_statement()
    if last_statement is None:
        raise QmQuaException(
            "'elif' statement must directly follow 'if' statement - Please make sure it is aligned with the corresponding if statement."
        )
    _, statement_if_inst = betterproto.which_one_of(last_statement, "statement_oneof")
    if not isinstance(statement_if_inst, QuaProgramIfStatement):
        raise QmQuaException(
            "'elif' statement must directly follow 'if' statement - Please make sure it is aligned with the corresponding if statement."
        )

    if betterproto.serialized_on_wire(statement_if_inst.else_):
        raise QmQuaException("'elif' must come before 'else' statement")

    elseif = QuaProgramElseIf(
        loc=last_statement.if_.loc,
        condition=to_scalar_pb_expression(expression),
        body=QuaProgramStatementsCollection(statements=[]),
    )
    last_statement.if_.elseifs.append(elseif)
    return _BodyScope(_StatementsCollection(elseif.body))


def else_() -> "_BodyScope":
    """Else flow control statement in QUA.

    To be used with a context manager.

    Must appear after an ``if_()`` statement.

    The QUA code block following the statement will be executed only if the expressions
    in the preceding ``if_()`` and ``elif_()`` statements evaluates to false.

    Example:
        ```python
        x=declare(int)
        with if_(x>0):
            play('pulse', 'element')
        with else_():
            play('other_pulse', 'element')
        ```
    """
    body = _get_scope_as_blocks_body()
    last_statement = body.get_last_statement()
    if last_statement is None:
        raise QmQuaException(
            "'else' statement must directly follow 'if' statement - "
            "Please make sure it is aligned with the corresponding if statement."
        )
    _, statement_if = betterproto.which_one_of(last_statement, "statement_oneof")
    if not isinstance(statement_if, QuaProgramIfStatement):
        raise QmQuaException(
            "'else' statement must directly follow 'if' statement - "
            "Please make sure it is aligned with the corresponding if statement."
        )

    if betterproto.serialized_on_wire(last_statement.if_.else_):
        raise QmQuaException("only a single 'else' statement can follow an 'if' statement")

    else_statement = QuaProgramStatementsCollection(statements=[])
    last_statement.if_.else_ = else_statement
    return _BodyScope(_StatementsCollection(else_statement))


def for_each_(var: OneOrMore[QuaVariable[NumberT]], values: OneOrMore[Vector[NumberT]]) -> "_BodyScope":
    """Flow control: Iterate over array elements in QUA.

    It is possible to either loop over one variable, or over a tuple of variables,
    similar to the `zip` style iteration in python.

    To be used with a context manager.

    Args:
        var (Union[QUA variable, tuple of QUA variables]): The iteration
            variable
        values (Union[list of literals, tuple of lists of literals, QUA array, tuple of QUA arrays]):
            A list of values to iterate over or a QUA array.

    Example:
        ```python
        x=declare(fixed)
        y=declare(fixed)
        with for_each_(x, [0.1, 0.4, 0.6]):
            play('pulse' * amp(x), 'element')
        with for_each_((x, y), ([0.1, 0.4, 0.6], [0.3, -0.2, 0.1])):
            play('pulse1' * amp(x), 'element')
            play('pulse2' * amp(y), 'element')
        ```

    Warning:

        This behavior is not exactly consistent with python `zip`.
        Instead of sending a list of tuple as values, the function expects a tuple of
        lists.
        The first list containing the values for the first variable, and so on.
    """
    body = _get_scope_as_blocks_body()
    if not isinstance(var, IterableClass):
        var = (var,)

    for i, v in enumerate(var):
        if not isinstance(v, QuaVariable):
            raise QmQuaException(f"for_each_ var {i} must be a variable")

    qua_expression_cond = isinstance(values, QuaExpression)
    not_iterable_cond = not isinstance(values, (IterableClass, QuaArrayVariable))
    tuple_of_non_iterables_cond = not isinstance(values[0], (IterableClass, QuaArrayVariable))
    if qua_expression_cond or not_iterable_cond or tuple_of_non_iterables_cond:
        values = (cast(QuaArrayVariable[NumberT], values),)
    values = cast(Tuple[QuaArrayVariable[NumberT], ...], values)

    if isinstance(values, Collection) and len(values) < 1:
        raise QmQuaException("values cannot be empty")

    if len(var) != len(values):
        raise QmQuaException("number of variables does not match number of array values")

    arrays: List[Union[QuaArrayVariable[bool], QuaArrayVariable[int], QuaArrayVariable[float]]] = []
    for value in values:
        if isinstance(value, QuaArrayVariable):
            arrays.append(value)
        elif isinstance(value, Collection):
            has_bool = collection_has_type_bool(value)
            has_int = collection_has_type_int(value)
            has_float = collection_has_type_float(value)

            if has_bool:
                if has_int or has_float:
                    raise QmQuaException("values can not contain both bool and number values")
                # Only booleans
                arrays.append(declare(bool, value=[bool(x) for x in value]))
            else:
                if has_float:
                    # All will be considered as fixed
                    arrays.append(declare(fixed, value=[float(x) for x in value]))
                else:
                    # Only ints
                    arrays.append(declare(int, value=[int(x) for x in value]))
        else:
            raise QmQuaException("value is not a QUA array neither iterable")

    unwrapped_vars = [v.unwrapped.variable for v in var]
    unwrapped_arrays = [a.unwrapped for a in arrays]

    iterators = [(unwrapped_vars[i], ar) for i, ar in enumerate(unwrapped_arrays)]

    foreach = body.for_each(iterators)
    return _BodyScope(foreach)


def while_(cond: Optional[QuaScalar[bool]] = None) -> "_BodyScope":
    """While loop flow control statement in QUA.

    To be used with a context manager.

    Args:
        cond (QUA expression): an expression which evaluates to a
            boolean variable, determines if to continue to next loop
            iteration

    Example:
        ```python
        x = declare(int)
        assign(x, 0)
        with while_(x<=30):
            play('pulse', 'element')
            assign(x, x+1)
        ```
    """
    return for_(None, None, cond, None)


def for_(
    var: Optional[QuaVariable[NumberT]] = None,
    init: Optional[Scalar[NumberT]] = None,
    cond: Optional[QuaScalar[bool]] = None,
    update: Optional[QuaScalar[NumberT]] = None,
) -> Union["_BodyScope", "_ForScope"]:
    """For loop flow control statement in QUA.

    To be used with a context manager.

    Args:
        var (QUA variable): QUA variable used as iteration variable
        init (QUA expression): an expression which sets the initial
            value of the iteration variable
        cond (QUA expression): an expression which evaluates to a
            boolean variable, determines if to continue to next loop
            iteration
        update (QUA expression): an expression to add to ``var`` with
            each loop iteration

    Example:
        ```python
        x = declare(fixed)
        with for_(var=x, init=0, cond=x<=1, update=x+0.1):
            play('pulse', 'element')
        ```
    """
    if var is None and init is None and cond is None and update is None:
        body = _get_scope_as_blocks_body()
        for_statement = body.for_block()
        return _ForScope(for_statement)
    else:
        body = _get_scope_as_blocks_body()
        for_statement = body.for_block()
        if var is not None and init is not None:
            for_statement.init = QuaProgramStatementsCollection(
                statements=[
                    QuaProgramAnyStatement(
                        assign=QuaProgramAssignmentStatement(
                            target=var.assignment_statement,
                            expression=to_scalar_pb_expression(init),
                            loc=_get_loc(),
                        )
                    )
                ]
            )
        if var is not None and update is not None:
            for_statement.update = QuaProgramStatementsCollection(
                statements=[
                    QuaProgramAnyStatement(
                        assign=QuaProgramAssignmentStatement(
                            target=var.assignment_statement,
                            expression=to_scalar_pb_expression(update),
                            loc=_get_loc(),
                        )
                    )
                ]
            )
        if cond is not None:
            for_statement.condition = to_scalar_pb_expression(cond)
        return _BodyScope(_StatementsCollection(for_statement.body))


def infinite_loop_() -> "_BodyScope":
    """Infinite loop flow control statement in QUA.

    To be used with a context manager.

    Optimized for zero latency between iterations,
    provided that no more than a single element appears in the loop.

    Note:
        In case multiple elements need to be used in an infinite loop, it is possible to add several loops
        in parallel (see example).
        Two infinite loops cannot share an element nor can they share variables.

    Example:
        ```python
        with infinite_loop_():
            play('pulse1', 'element1')
        with infinite_loop_():
            play('pulse2', 'element2')
        ```
    """
    body = _get_scope_as_blocks_body()
    for_statement = body.for_block()
    for_statement.condition = literal_bool(True)
    return _BodyScope(_StatementsCollection(for_statement.body))


def port_condition(condition: Scalar[bool]) -> "_BodyScope":
    """
    A context manager for a faster conditional play mechanism. Will operate on all the elements inside the context manager.
    Note that elements sharing a port with an element inside the context manager cannot be played in parallel to the context manager.

    -- Available for MW-FEM Only --

    Args:
        condition (A logical expression to evaluate): Will play the operation only if the condition is true.
            The play command will take the same amount of time regardless of the condition (If false, would wait instead).

    Example:
        ```python
        with port_condition(x > 0):
            play('pulse', 'element')
        ```
    """
    body = _get_scope_as_blocks_body()
    return _BodyScope(PortConditionedStatementsCollection(body._body, condition=to_scalar_pb_expression(condition)))


def L(value: Union[bool, int, float]) -> MessageExpressionType:
    """Creates an expression with a literal value

    Args:
        value: int, float or bool to wrap in a literal expression
    """
    if isinstance(value, bool):
        return literal_bool(value)
    if isinstance(value, int):
        return literal_int(value)
    if isinstance(value, float):
        return literal_real(value)
    raise QmQuaException("literal can be bool, int or float")


class DeclarationType(Enum):
    EmptyScalar = 0
    InitScalar = 1
    EmptyArray = 2
    InitArray = 3


class _DeclarationParams(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def create_variable(
        self, var_name: str, t: Type[NumberT]
    ) -> Union[QuaArrayVariable[NumberT], QuaVariable[NumberT]]:
        pass

    @abc.abstractmethod
    def create_input_stream(
        self, var_name: str, t: Type[NumberT]
    ) -> Union[QuaArrayInputStream[NumberT], QuaVariableInputStream[NumberT]]:
        pass


@dataclass
class _ArrayDeclarationParams(_DeclarationParams):
    size: int
    values: Sequence[Union[bool, int, float]]

    def create_variable(self, var_name: str, t: Type[NumberT]) -> QuaArrayVariable[NumberT]:
        return QuaArrayVariable(var_name, t, size=self.size, init_value=self.values)

    def create_input_stream(self, var_name: str, t: Type[NumberT]) -> QuaArrayInputStream[NumberT]:
        return QuaArrayInputStream(var_name, t, size=self.size, init_value=self.values)


@dataclass
class _ScalarDeclarationParams(_DeclarationParams):
    value: Optional[Union[bool, int, float]]

    def create_variable(self, var_name: str, t: Type[NumberT]) -> QuaVariable[NumberT]:
        return QuaVariable(var_name, t, init_value=self.value)

    def create_input_stream(self, var_name: str, t: Type[NumberT]) -> QuaVariableInputStream[NumberT]:
        return QuaVariableInputStream(var_name, t, init_value=self.value)


def _standardize_value_and_size(
    value: Optional[OneOrMore[Union[bool, int, float]]] = None, size: Optional[int] = None
) -> _DeclarationParams:

    if size is not None:
        size = size.item() if isinstance(size, np.integer) else size  # type: ignore[attr-defined]
        if not (isinstance(size, int) and size > 0):
            raise QmQuaException("size must be a positive integer")
        if value is not None:
            raise QmQuaException("size declaration cannot be made if value is declared")
        return _ArrayDeclarationParams(size=size, values=[])

    if isinstance(value, Collection):
        size = len(value)
        return _ArrayDeclarationParams(size=size, values=list(value))

    return _ScalarDeclarationParams(value=value)


@overload
def declare(t: Type[NumberT]) -> QuaVariable[NumberT]:
    ...


@overload
def declare(t: Type[NumberT], value: Literal[None], size: int) -> QuaArrayVariable[NumberT]:
    ...


@overload
def declare(t: Type[NumberT], *, size: int) -> QuaArrayVariable[NumberT]:
    ...


@overload
def declare(t: Type[NumberT], value: Union[int, bool, float]) -> QuaVariable[NumberT]:
    ...


@overload
def declare(t: Type[NumberT], value: Sequence[Union[int, bool, float]]) -> QuaArrayVariable[NumberT]:
    ...


def declare(
    t: Type[NumberT],
    value: Optional[OneOrMore[Union[int, bool, float]]] = None,
    size: Optional[int] = None,
) -> Union[QuaVariable[NumberT], QuaArrayVariable[NumberT]]:
    r"""Declare a single QUA variable or QUA vector to be used in subsequent expressions and assignments.

    Declaration is performed by declaring a python variable with the return value of this function.

    Args:
        t: The type of QUA variable. Possible values: ``int``,
            ``fixed``, ``bool``, where:

            ``int``
                a signed 32-bit number
            ``fixed``
                a signed 4.28 fixed point number
            ``bool``
                either `True` or `False`
        value: An initial value for the variable or a list of initial
            values for a vector
        size: If declaring a vector without explicitly specifying a
            value, this parameter is used to specify the length of the
            array

    Returns:
        The variable or vector

    Warning:

        some QUA statements accept a variable with a valid range smaller than the full size of the generic
        QUA variable. For example, ``amp()`` accepts numbers between -2 and 2.
        In case the value stored in the variable is larger than the valid input range, unexpected results
        may occur.

    Example:
        ```python
        a = declare(fixed, value=0.3)
        play('pulse' * amp(a), 'element')

        array1 = declare(int, value=[1, 2, 3])
        array2 = declare(fixed, size=5)
        ```
    """
    params = _standardize_value_and_size(value, size)

    scope = _get_root_program_scope()
    # We could move the following logic inside the classes, but then we would have to deal with the scope there.
    #  Additionally, we want to separate the concern of choosing the variable name from the declaration logic,
    if isinstance(params, _ArrayDeclarationParams):
        scope.array_index += 1
        var = f"a{scope.array_index}"
    else:
        scope.var_index += 1
        var = f"v{scope.var_index}"

    result = params.create_variable(var, t)
    scope.program.add_declaration(result.declaration_statement)

    return result


@overload
def declare_input_stream(t: Type[NumberT], name: str) -> QuaVariableInputStream[NumberT]:
    ...


@overload
def declare_input_stream(t: Type[NumberT], name: str, value: Literal[None], size: int) -> QuaArrayInputStream[NumberT]:
    ...


@overload
def declare_input_stream(t: Type[NumberT], name: str, *, size: int) -> QuaArrayInputStream[NumberT]:
    ...


@overload
def declare_input_stream(
    t: Type[NumberT], name: str, value: Union[int, bool, float]
) -> QuaVariableInputStream[NumberT]:
    ...


@overload
def declare_input_stream(
    t: Type[NumberT], name: str, value: Sequence[Union[int, bool, float]]
) -> QuaArrayInputStream[NumberT]:
    ...


def declare_input_stream(
    t: Type[NumberT],
    name: str,
    value: Optional[Optional[OneOrMore[Union[int, bool, float]]]] = None,
    size: Optional[int] = None,
) -> Union[QuaVariableInputStream[NumberT], QuaArrayInputStream[NumberT]]:
    """Declare a QUA variable or a QUA vector to be used as an input stream from the job to the QUA program.

    Declaration is performed by declaring a python variable with the return value of this function.

    Declaration is similar to the normal QUA variable declaration. See [qm.qua._dsl.declare][] for available
    parameters.

    See [Input streams](../../Guides/features.md#input-streams) for more information.

    -- Available from QOP 2.0 --

    Example:
        ```python
        tau = declare_input_stream(int)
        ...
        advance_input_stream(tau)
        play('operation', 'element', duration=tau)
        ```
    """
    if name is None:
        raise QmQuaException("input stream declared without a name")

    scope = _get_root_program_scope()
    var = f"input_stream_{name}"

    if var in scope.declared_input_streams:
        raise QmQuaException("input stream already declared")

    params = _standardize_value_and_size(value, size)

    scope.declared_input_streams.add(var)
    result = params.create_input_stream(var, t)

    scope.program.add_declaration(result.declaration_statement)

    return result


def advance_input_stream(
    input_stream: Union[
        QuaVariableInputStream[bool],
        QuaVariableInputStream[int],
        QuaVariableInputStream[float],
        QuaArrayInputStream[bool],
        QuaArrayInputStream[int],
        QuaArrayInputStream[float],
    ]
) -> None:
    """Advances the input stream pointer to the next available variable/vector.

    If there is no new data waiting in the stream, this command will wait until it is available.

    The variable/vector can then be used as a normal QUA variable.

    See [Input streams](../../Guides/features.md#input-streams) for more information.

    -- Available from QOP 2.0 --
    """

    body = _get_scope_as_blocks_body()
    body.advance_input_stream(input_stream.advance())


def declare_stream(adc_trace: bool = False) -> "_ResultSource":
    """Declare a QUA output stream to be used in subsequent statements
    To retrieve the result - it must be saved in the stream processing block.

    Declaration is performed by declaring a python variable with the return value of this function.

    Note:
        if the stream is an ADC trace, declaring it with the syntax ``declare_stream(adc_trace=True)``
        will add a buffer of length corresponding to the pulse length.

    Returns:
        A :class:`_ResultSource` object to be used in
        [`stream_processing`][qm.qua._dsl.stream_processing]

    Example:
        ```python
        a = declare_stream()
        measure('pulse', 'element', a)

        with stream_processing():
            a.save("tag")
            a.save_all("another tag")
        ```
    """

    scope = _get_root_program_scope()
    scope.result_index += 1
    var = f"r{scope.result_index}"
    if adc_trace:
        var = "atr_" + var

    return _ResultSource(
        _ResultSourceConfiguration(
            var_name=var,
            timestamp_mode=_ResultSourceTimestampMode.Values,
            is_adc_trace=adc_trace,
            input=-1,
            auto_reshape=False,
        )
    )


# Although _PulseAmp is a protected class, it is used by QUAM.
# Therefore, any breaking changes should be communicated to the QUAM authors.
class _PulseAmp:
    def __init__(
        self,
        v1: Optional[MessageExpressionType],
        v2: Optional[MessageExpressionType],
        v3: Optional[MessageExpressionType],
        v4: Optional[MessageExpressionType],
    ):
        if v1 is None:
            raise QmQuaException("amp can be one value or a matrix of 4")
        if v2 is None and v3 is None and v4 is None:
            pass
        elif v2 is not None and v3 is not None and v4 is not None:
            pass
        else:
            raise QmQuaException("amp can be one value or a matrix of 4.")

        self.v1 = v1
        self.v2 = v2
        self.v3 = v3
        self.v4 = v4

    def value(self) -> AmpValuesType:
        return self.v1, self.v2, self.v3, self.v4

    def __rmul__(self, other: str) -> Tuple[str, AmpValuesType]:
        return self * other

    def __mul__(self, other: str) -> Tuple[str, AmpValuesType]:
        if not isinstance(other, str):
            raise QmQuaException("you can multiply only a pulse")
        return other, self.value()


@overload
def amp(v1: Scalar[float]) -> _PulseAmp:
    ...


@overload
def amp(v1: Scalar[float], v2: Scalar[float], v3: Scalar[float], v4: Scalar[float]) -> _PulseAmp:
    ...


def amp(
    v1: Scalar[float],
    v2: Optional[Scalar[float]] = None,
    v3: Optional[Scalar[float]] = None,
    v4: Optional[Scalar[float]] = None,
) -> _PulseAmp:
    """To be used only within a [play][qm.qua._dsl.play] or [measure][qm.qua._dsl.measure] command, as a multiplication to
    the `operation`.

    It is possible to scale the pulse's amplitude dynamically by using the following syntax:

    ``play('pulse_name' * amp(v), 'element')``

    where ``v`` is QUA variable of type fixed. Range of v: -2 to $2 - 2^{-16}$ in steps of $2^{-16}$.

    Moreover, if the pulse is intended to a mixedInputs element and thus is defined with two waveforms,
    the two waveforms, described as a column vector, can be multiplied by a matrix:

    ``play('pulse_name' * amp(v_00, v_01, v_10, v_11), 'element'),``

    where ``v_ij``, i,j={0,1}, are QUA variables of type fixed.
    Note that ``v_ij`` should satisfy -2 <= ``v_ij`` <= $2 - 2{-16}$.

    Note that scaling in this manner, rather than in the configuration, might result
    in a computational overhead.
    See [QUA Best Practice Guide](../../Guides/best_practices.md#general) for more information.

    Args:
        v1: If only this variable is given, it is the scaler amplitude
            factor which multiples the `pulse` associated with the
            `operation`. If all variables are given, then it is the
            first element in the amplitude matrix which multiples the
            `pulse` associated with the `operation`.
        v2: The second element in the amplitude matrix which multiples
            the `pulse` associated with the `operation`.
        v3: The third element in the amplitude matrix which multiples
            the `pulse` associated with the `operation`.
        v4: The forth element in the amplitude matrix which multiples
            the `pulse` associated with the `operation`.
    """

    def _cast_number(v: Optional[Scalar[float]]) -> Optional[QuaProgramAnyScalarExpression]:
        if v is None:
            return None
        return to_scalar_pb_expression(v)

    return _PulseAmp(_cast_number(v1), _cast_number(v2), _cast_number(v3), _cast_number(v4))


def ramp(v: Scalar[NumberT]) -> QuaProgramRampPulse:
    """To be used only within a [`play`][qm.qua._dsl.play] command, instead of the `operation`.

    It’s possible to generate a voltage ramp by using the `ramp(slope)` command.
    The slope argument is specified in units of `V/ns`. Usage of this feature is as follows:

    ``play(ramp(0.0001),'qe1',duration=1000)``

    .. note:
        The pulse duration must be specified if the ramp feature is used.

    Args:
        v: The slope in units of `V/ns`
    """
    value = create_qua_scalar_expression(v)
    result = QuaProgramRampPulse(value=value.unwrapped)
    return result


class _BaseScope:
    def __enter__(self) -> None:
        global _block_stack
        _block_stack.append(self)
        return None

    def __exit__(
        self, exc_type: Optional[Type[BaseException]], exc_val: Optional[BaseException], exc_tb: Optional[TracebackType]
    ) -> Literal[False]:
        global _block_stack
        if _block_stack[-1] != self:
            raise QmQuaException("Unexpected stack structure")
        _block_stack.remove(self)
        return False


class _BodyScope(_BaseScope):
    def __init__(self, body: Optional[_StatementsCollection]):
        super().__init__()
        self._body = body

    def body(self) -> _StatementsCollection:
        return cast(_StatementsCollection, self._body)


class _ProgramScope(_BodyScope):
    def __init__(self, _program: "Program"):
        super().__init__(_program.body)
        self._program = _program
        self.var_index = 0
        self.array_index = 0
        self.result_index = 0
        self.declared_input_streams: Set[str] = set()
        self._declared_streams: Dict[str, _ResultSource] = {}

    def __enter__(self) -> "Program":  # type: ignore[override]
        # TODO (YR) - split the contexts so we won't need to override
        super().__enter__()
        self._program.set_in_scope()
        return self._program

    def __exit__(
        self, exc_type: Optional[Type[BaseException]], exc_val: Optional[BaseException], exc_tb: Optional[TracebackType]
    ) -> Literal[False]:
        self._program.result_analysis.generate_proto()
        self._program.set_exit_scope()
        return super().__exit__(exc_type, exc_val, exc_tb)

    @property
    def program(self) -> "Program":
        return self._program

    def declare_legacy_adc(self, tag: str) -> "_ResultSource":
        result_object = self._declared_streams.get(tag, None)
        if result_object is None:
            result_object = declare_stream(adc_trace=True)
            self._declared_streams[tag] = result_object

            ra = _get_scope_as_result_analysis()
            ra.auto_save_all(tag + "_input1", result_object.input1())
            ra.auto_save_all(
                tag + "_input1" + _TIMESTAMPS_LEGACY_SUFFIX,
                result_object.input1().timestamps(),
            )
            ra.auto_save_all(tag + "_input2", result_object.input2())
            ra.auto_save_all(
                tag + "_input2" + _TIMESTAMPS_LEGACY_SUFFIX,
                result_object.input2().timestamps(),
            )

        return result_object

    def declare_legacy_save(self, tag: str) -> "_ResultSource":
        result_object = self.declare_save(tag, add_legacy_timestamp=True)
        return result_object

    def declare_save(self, tag: str, add_legacy_timestamp: bool = False) -> "_ResultSource":
        result_object = self._declared_streams.get(tag, None)
        if result_object is None:
            result_object = declare_stream()
            self._declared_streams[tag] = result_object

            ra = _get_scope_as_result_analysis()
            ra.auto_save_all(tag, result_object)
            if add_legacy_timestamp:
                ra.auto_save_all(tag + _TIMESTAMPS_LEGACY_SUFFIX, result_object.timestamps())
        return result_object


class _ForScope(_BodyScope):
    def __init__(self, for_statement: QuaProgramForStatement):
        super().__init__(None)
        self._for_statement = for_statement

    def body(self) -> _StatementsCollection:
        raise QmQuaException("for must be used with for_init, for_update, for_body and for_cond")

    def for_statement(self) -> QuaProgramForStatement:
        return self._for_statement


class _SwitchScope(Generic[NumberT], _BaseScope):
    def __init__(self, expression: QuaScalar[NumberT], container: _StatementsCollection, unsafe: bool):
        super().__init__()
        self.expression: QuaScalar[NumberT] = expression
        self.if_statement: Optional[QuaProgramAnyStatement] = None
        self.container = container
        self.unsafe = unsafe


def strict_timing_() -> _BodyScope:
    """Any QUA command written within the strict timing block will be required to play without gaps.

    See [the documentation](../../Guides/timing_in_qua.md#strict-timing) for further information and examples.

    To be used with a context manager.

    -- Available from QOP 2.0 --
    """

    body = _get_scope_as_blocks_body()
    strict_timing_statement = body.strict_timing_block()
    return _BodyScope(_StatementsCollection(strict_timing_statement.body))


class _RAScope(_BaseScope):
    def __init__(self, ra: _ResultAnalysis):
        super().__init__()
        self._ra = ra

    def __enter__(self) -> _ResultAnalysis:  # type: ignore[override]
        # TODO (YR) - split the contexts so we won't need to override
        super().__enter__()
        return self._ra

    def result_analysis(self) -> _ResultAnalysis:
        return self._ra


def _get_root_program_scope() -> _ProgramScope:
    global _block_stack
    first_block = _block_stack[0]
    if not isinstance(first_block, _ProgramScope):
        raise QmQuaException("Expecting program scope")
    return first_block


def _get_scope_as_program() -> "Program":
    global _block_stack
    last_block = _block_stack[-1]
    if not isinstance(last_block, _ProgramScope):
        raise QmQuaException("Expecting program scope")
    return last_block.program


def _get_scope_as_for() -> QuaProgramForStatement:
    global _block_stack
    last_block = _block_stack[-1]
    if not isinstance(last_block, _ForScope):
        raise QmQuaException("Expecting for scope")
    return last_block.for_statement()


def _get_scope_as_blocks_body() -> _StatementsCollection:
    global _block_stack
    last_block = _block_stack[-1]
    if not isinstance(last_block, _BodyScope):
        raise QmQuaException("Expecting scope with body.")
    return last_block.body()


def _get_scope_as_switch_scope() -> _SwitchScope[NumberT]:
    global _block_stack
    last_block = _block_stack[-1]
    if not isinstance(last_block, _SwitchScope):
        raise QmQuaException("Expecting switch scope")
    return last_block


def _get_scope_as_result_analysis() -> _ResultAnalysis:
    global _block_stack
    return _get_root_program_scope().program.result_analysis


class AccumulationMethod(metaclass=abc.ABCMeta):
    def __init__(self) -> None:
        self.loc = ""

    def _full_target(self, target: Union[QuaVariable[float], QuaArrayCell[float]]) -> ScalarProcessTarget:
        return ScalarProcessTarget(self.loc, target)

    def _sliced_target(self, target: QuaArrayVariable[float], samples_per_chunk: int) -> VectorProcessTarget:
        analog_time_division = SlicedAnalogTimeDivision(self.loc, samples_per_chunk)
        return VectorProcessTarget(self.loc, target, analog_time_division)

    def _accumulated_target(self, target: QuaArrayVariable[float], samples_per_chunk: int) -> VectorProcessTarget:
        analog_time_division = AccumulatedAnalogTimeDivision(self.loc, samples_per_chunk)
        return VectorProcessTarget(self.loc, target, analog_time_division)

    def _moving_window_target(
        self, target: QuaArrayVariable[float], samples_per_chunk: int, chunks_per_window: int
    ) -> VectorProcessTarget:
        analog_time_division = MovingWindowAnalogTimeDivision(self.loc, samples_per_chunk, chunks_per_window)
        return VectorProcessTarget(self.loc, target, analog_time_division)


class RealAccumulationMethod(AccumulationMethod):
    """A base class for specifying the integration and demodulation processes in the [measure][qm.qua._dsl.measure]
    statement.
    These are the options which can be used inside the measure command as part of the ``demod`` and ``integration``
    processes.
    """

    def __init__(self, _return_func: Type[BasicIntegration]) -> None:
        super().__init__()
        self._return_func = _return_func

    @property
    def return_func(self) -> Type[BasicIntegration]:
        return self._return_func

    def full(
        self, iw: str, target: Union[QuaVariable[float], QuaArrayCell[float]], element_output: str = ""
    ) -> BasicIntegration:
        """Perform an ordinary demodulation/integration. See [Full demodulation](../../Guides/features.md#full-demodulation).

        Args:
            iw (str): integration weights
            target (QUA variable): variable to which demod result is
                saved
            element_output (str): The output of an element from which to get the ADC data.
                Required for elements with `MWOutput` or with multiple `outputs`. Optional otherwise.
        """
        return self.return_func(element_output, iw, self._full_target(target))

    def sliced(
        self,
        iw: str,
        target: QuaArrayVariable[float],
        samples_per_chunk: int,
        element_output: str = "",
    ) -> BasicIntegration:
        """Perform a demodulation/integration in which the demodulation/integration process is split into chunks
        and the value of each chunk is saved in an array cell. See [Sliced demodulation](../../Guides/features.md#sliced-demodulation).

        Args:
            iw (str): integration weights
            target (QUA array): variable to which demod result is saved
            samples_per_chunk (int): The number of ADC samples to be
                used for each chunk is this number times 4.
            element_output (str): The output of an element from which to get the ADC data.
                Required for elements with `MWOutput` or with multiple `outputs`. Optional otherwise.
        """
        return self.return_func(element_output, iw, self._sliced_target(target, samples_per_chunk))

    def accumulated(
        self,
        iw: str,
        target: QuaArrayVariable[float],
        samples_per_chunk: int,
        element_output: str = "",
    ) -> BasicIntegration:
        """Same as ``sliced()``, however the accumulated result of the demodulation/integration
        is saved in each array cell. See [Accumulated demodulation](../../Guides/features.md#accumulated-demodulation).

        Args:
            iw (str): integration weights
            target (QUA array): variable to which demod result is saved
            samples_per_chunk (int): The number of ADC samples to be
                used for each chunk is this number times 4.
            element_output (str): The output of an element from which to get the ADC data.
                Required for elements with `MWOutput` or with multiple `outputs`. Optional otherwise.
        """
        return self.return_func(element_output, iw, self._accumulated_target(target, samples_per_chunk))

    def moving_window(
        self,
        iw: str,
        target: QuaArrayVariable[float],
        samples_per_chunk: int,
        chunks_per_window: int,
        element_output: str = "",
    ) -> BasicIntegration:
        """Same as ``sliced()``, however the several chunks are accumulated and saved to each array cell.
        See [Moving window demodulation](../../Guides/features.md#moving-window-demodulation).

        Args:
            iw (str): integration weights
            target (QUA array): variable to which demod result is saved
            samples_per_chunk (int): The number of ADC samples to be
                used for each chunk is this number times 4.
            chunks_per_window (int): The number of chunks to use in the
                moving window
            element_output (str): The output of an element from which to get the ADC data.
                Required for elements with `MWOutput` or with multiple `outputs`. Optional otherwise.
        """
        return self.return_func(
            element_output,
            iw,
            self._moving_window_target(target, samples_per_chunk, chunks_per_window),
        )


class DualAccumulationMethod(AccumulationMethod):
    """A base class for specifying the dual integration and demodulation processes in the :func:`measure`
    statement.
    These are the options which can be used inside the measure command as part of the ``dual_demod`` and
    ``dual_integration`` processes.
    """

    def __init__(self, return_func: Type[DualMeasureProcess]):
        super().__init__()
        self._return_func = return_func

    @property
    def return_func(self) -> Type[DualMeasureProcess]:
        return self._return_func

    @overload
    def full(
        self,
        iw1: str,
        iw2: str,
        target: Union[QuaVariable[float], QuaArrayCell[float]],
    ) -> DualMeasureProcess:
        """Perform an ordinary dual demodulation/integration. See [Dual demodulation](../../Guides/demod.md#dual-demodulation).

        Args:
            iw1 (str): integration weights to be applied to
                the I quadrature (or 'out1')
            iw2 (str): integration weights to be applied to
                the Q quadrature (or 'out2')
            target (QUA variable): variable to which demod result is
                saved
        """
        pass

    @overload
    def full(
        self,
        iw1: str,
        element_output1: str,
        iw2: str,
        element_output2: str,
        target: Union[QuaVariable[float], QuaArrayCell[float]],
    ) -> DualMeasureProcess:
        """Perform an ordinary dual demodulation/integration. See [Dual demodulation](../../Guides/demod.md#dual-demodulation).

        Args:
            iw1 (str): integration weights to be applied to
                element_output1
            element_output1 (str): the output of an element from which
                to get ADC results
            iw2 (str): integration weights to be applied to
                element_output2
            element_output2 (str): the output of an element from which
                to get ADC results
            target (QUA variable): variable to which demod result is
                saved
        """
        pass

    def full(self, *args: Any, **kwargs: Any) -> DualMeasureProcess:
        """Perform an ordinary dual demodulation/integration. See [Dual demodulation](../../Guides/demod.md#dual-demodulation).

        Args:
            iw1 (str): integration weights to be applied to
                the I quadrature (or 'out1')
            iw2 (str): integration weights to be applied to
                the Q quadrature (or 'out2')
            target (QUA variable): variable to which demod result is
                saved
        """
        if len(args) + len(kwargs) == 3:
            kwargs.update(_make_dict_from_args(args, ["iw1", "iw2", "target"]))
            kwargs["element_output1"] = DEFAULT_OUT1
            kwargs["element_output2"] = DEFAULT_OUT2
            return self.full(**kwargs)
        elif len(args) + len(kwargs) == 5:
            kwargs.update(_make_dict_from_args(args, ["iw1", "element_output1", "iw2", "element_output2", "target"]))
        else:
            raise QmQuaException("Invalid number of arguments")

        return self.return_func(
            kwargs["element_output1"],
            kwargs["element_output2"],
            kwargs["iw1"],
            kwargs["iw2"],
            self._full_target(kwargs["target"]),
        )

    @overload
    def sliced(
        self,
        iw1: str,
        iw2: str,
        samples_per_chunk: int,
        target: QuaArrayVariable[float],
    ) -> DualMeasureProcess:
        pass

    @overload
    def sliced(
        self,
        iw1: str,
        element_output1: str,
        iw2: str,
        element_output2: str,
        samples_per_chunk: int,
        target: QuaArrayVariable[float],
    ) -> DualMeasureProcess:
        pass

    def sliced(self, *args: Any, **kwargs: Any) -> DualMeasureProcess:
        """This feature is currently not supported in QUA"""
        if len(args) + len(kwargs) == 4:
            kwargs.update(_make_dict_from_args(args, ["iw1", "iw2", "samples_per_chunk", "target"]))
            kwargs["element_output1"] = DEFAULT_OUT1
            kwargs["element_output2"] = DEFAULT_OUT2
            return self.sliced(**kwargs)
        elif len(args) + len(kwargs) == 6:
            kwargs.update(
                _make_dict_from_args(
                    args,
                    ["iw1", "element_output1", "iw2", "element_output2", "samples_per_chunk", "target"],
                )
            )
        else:
            raise QmQuaException("Invalid number of arguments")

        return self.return_func(
            kwargs["element_output1"],
            kwargs["element_output2"],
            kwargs["iw1"],
            kwargs["iw2"],
            self._sliced_target(kwargs["target"], kwargs["samples_per_chunk"]),
        )

    @overload
    def accumulated(
        self,
        iw1: str,
        iw2: str,
        samples_per_chunk: int,
        target: QuaArrayVariable[float],
    ) -> DualMeasureProcess:
        pass

    @overload
    def accumulated(
        self,
        iw1: str,
        element_output1: str,
        iw2: str,
        element_output2: str,
        samples_per_chunk: int,
        target: QuaArrayVariable[float],
    ) -> DualMeasureProcess:
        pass

    def accumulated(self, *args: Any, **kwargs: Any) -> DualMeasureProcess:
        """This feature is currently not supported in QUA"""
        if len(args) + len(kwargs) == 4:
            kwargs.update(_make_dict_from_args(args, ["iw1", "iw2", "samples_per_chunk", "target"]))
            kwargs["element_output1"] = DEFAULT_OUT1
            kwargs["element_output2"] = DEFAULT_OUT2
            return self.accumulated(**kwargs)
        elif len(args) + len(kwargs) == 6:
            kwargs.update(
                _make_dict_from_args(
                    args,
                    ["iw1", "element_output1", "iw2", "element_output2", "samples_per_chunk", "target"],
                )
            )
        else:
            raise QmQuaException("Invalid number of arguments")

        return self.return_func(
            kwargs["element_output1"],
            kwargs["element_output2"],
            kwargs["iw1"],
            kwargs["iw2"],
            self._accumulated_target(kwargs["target"], kwargs["samples_per_chunk"]),
        )

    @overload
    def moving_window(
        self,
        iw1: str,
        iw2: str,
        samples_per_chunk: int,
        chunks_per_window: int,
        target: QuaArrayVariable[float],
    ) -> DualMeasureProcess:
        pass

    @overload
    def moving_window(
        self,
        iw1: str,
        element_output1: str,
        iw2: str,
        element_output2: str,
        samples_per_chunk: int,
        chunks_per_window: int,
        target: QuaArrayVariable[float],
    ) -> DualMeasureProcess:
        pass

    def moving_window(self, *args: Any, **kwargs: Any) -> DualMeasureProcess:
        """This feature is currently not supported in QUA"""
        if len(args) + len(kwargs) == 5:
            kwargs.update(
                _make_dict_from_args(args, ["iw1", "iw2", "samples_per_chunk", "chunks_per_window", "target"])
            )
            kwargs["element_output1"] = DEFAULT_OUT1
            kwargs["element_output2"] = DEFAULT_OUT2
            return self.moving_window(**kwargs)
        elif len(args) + len(kwargs) == 7:
            kwargs.update(
                _make_dict_from_args(
                    args,
                    [
                        "iw1",
                        "element_output1",
                        "iw2",
                        "element_output2",
                        "samples_per_chunk",
                        "chunks_per_window",
                        "target",
                    ],
                )
            )
        else:
            raise QmQuaException("Invalid number of arguments")

        return self.return_func(
            kwargs["element_output1"],
            kwargs["element_output2"],
            kwargs["iw1"],
            kwargs["iw2"],
            self._moving_window_target(kwargs["target"], kwargs["samples_per_chunk"], kwargs["chunks_per_window"]),
        )


class TimeTagging:
    """A base class for specifying the time tagging process in the [measure][qm.qua._dsl.measure] statement.
    These are the options which can be used inside the measure command as part of the ``time_tagging`` process.
    """

    def __init__(self) -> None:
        self.loc = ""

    def analog(
        self,
        target: QuaArrayVariable[int],
        max_time: int,
        targetLen: Optional[QuaVariable[int]] = None,
        element_output: str = "",
    ) -> AnalogRawTimeTagging:
        """Performs time tagging. See [Time tagging](../../Guides/features.md#time-tagging).

        Args:
            target (QUA array of type int): The QUA array into which the
                times of the detected pulses are saved (in ns)
            max_time (int): The time in which pulses are detected
                (Must be larger than the pulse duration)
            targetLen (QUA int): A QUA int which will get the number of
                pulses detected
            element_output (str): The output of an element from which to get the pulses.
                Required when there are multiple outputs in the element. Optional otherwise.
        """
        return AnalogRawTimeTagging(element_output, target, targetLen, max_time)

    def digital(
        self,
        target: QuaArrayVariable[int],
        max_time: int,
        targetLen: Optional[QuaVariable[int]] = None,
        element_output: str = "",
    ) -> DigitalRawTimeTagging:
        """Performs time tagging from the attached OPD.
         See [Time tagging](../../Guides/features.md#time-tagging).

        -- Available with the OPD addon --

        Args:
            target (QUA array of type int): The QUA array into which the
                times of the detected pulses are saved (in ns)
            max_time (int): The time in which pulses are detected
                (Must be larger than the pulse duration)
            targetLen (QUA int): A QUA int which will get the number of
                pulses detected
            element_output (str): The output of an element from which to get the pulses.
                Required when there are multiple outputs in the element. Optional otherwise.
        """
        return DigitalRawTimeTagging(element_output, target, targetLen, max_time)

    def high_res(
        self,
        target: QuaArrayVariable[int],
        max_time: int,
        targetLen: Optional[QuaVariable[int]] = None,
        element_output: str = "",
    ) -> HighResTimeTagging:
        """Performs high resolution time tagging. See [Time tagging](../../Guides/features.md#time-tagging).

        -- Available from QOP 2.0 --

        Args:
            target (QUA array of type int): The QUA array into which the
                times of the detected pulses are saved (in ps)
            max_time (int): The time in which pulses are detected
                (Must be larger than the pulse duration)
            targetLen (QUA int): A QUA int which will get the number of
                pulses detected
            element_output (str): The output of an element from which to get the pulses.
                Required when there are multiple outputs in the element. Optional otherwise.
        """
        return HighResTimeTagging(element_output, target, targetLen, max_time)


class Counting:
    """A base class for specifying the counting process in the [measure][qm.qua._dsl.measure] statement.
    These are the options which can be used inside the measure command as part of the ``counting`` process.

    -- Available with the OPD addon --
    """

    def __init__(self) -> None:
        self.loc = ""

    def digital(
        self,
        target: QuaVariable[int],
        max_time: int,
        element_outputs: str = "",
    ) -> DigitalMeasureProcessCounting:
        """Performs counting from the attached OPD. See [Time tagging](../../Guides/features.md#time-tagging).

        -- Available with the OPD addon --

        Args:
            target (QUA int): A QUA int which will get the number of
                pulses detected
            max_time (int): The time in which pulses are detected
                (Must be larger than the pulse duration)
            element_outputs (str): the outputs of an element from which
                to get ADC results
        """
        return DigitalMeasureProcessCounting(element_outputs, target, max_time)


class _FunctionExpressions:
    """A class that provides functionality for creating function expressions, a specific type of AnyScalarExpression.
    Currently, this class is private, as all function expressions are exclusively accessible to users through the
    broadcast object.
    This approach is a newer and improved alternative to the functionality provided by LibFunctions, and it works in
    much the same way. However, unlike LibFunctions, each function in this class has its own dedicated Proto message for
    its description. This results in a significantly clearer API, as opposed to LibFunctions, where all functions share
    the same Proto message, making it more challenging to understand the purpose of individual functions.
    """

    @staticmethod
    def _standardize_args(
        *args: Union[Scalar[NumberT], QuaArrayVariable[NumberT]]
    ) -> List[QuaProgramFunctionExpressionScalarOrVectorArgument]:
        standardized_args = []

        for arg in args:
            if isinstance(arg, QuaArrayVariable):
                standardized_args.append(QuaProgramFunctionExpressionScalarOrVectorArgument(array=arg.unwrapped))
            else:
                arg = create_qua_scalar_expression(arg)
                standardized_args.append(QuaProgramFunctionExpressionScalarOrVectorArgument(scalar=arg.unwrapped))

        return standardized_args

    @staticmethod
    def and_(*values: Union[Scalar[bool], QuaArrayVariable[bool]]) -> QuaFunctionOutput[bool]:
        """Performs a logical AND operation on the input values.

        Args:
            *values (boolean, QUA boolean, Qua array of type boolean): The input values to be combined using a
            logical AND operation. Each input can be a single boolean, a QUA boolean or a QUA array of booleans.
        """
        function_expression = QuaProgramFunctionExpression(
            and_=QuaProgramFunctionExpressionAndFunction(_FunctionExpressions._standardize_args(*values)),
            loc=_get_loc(),
        )
        return QuaFunctionOutput(function_expression, bool)

    @staticmethod
    def or_(*values: Union[Scalar[bool], QuaArrayVariable[bool]]) -> QuaFunctionOutput[bool]:
        """Performs a logical OR operation on the input values.

        Args:
            *values (boolean, QUA boolean, Qua array of type boolean): The input values to be combined using a
            logical OR operation. Each input can be a single boolean, a QUA boolean or a QUA array of booleans.
        """
        function_expression = QuaProgramFunctionExpression(
            or_=QuaProgramFunctionExpressionOrFunction(_FunctionExpressions._standardize_args(*values)),
            loc=_get_loc(),
        )
        return QuaFunctionOutput(function_expression, bool)

    @staticmethod
    def xor_(*values: Union[Scalar[bool], QuaArrayVariable[bool]]) -> QuaFunctionOutput[bool]:
        """Performs a logical XOR (exclusive OR) operation on the input values.

        Args:
            *values (boolean, QUA boolean, Qua array of type boolean): The input values to be combined using a
            logical XOR operation. Each input can be a single boolean, a QUA boolean, or a QUA array of booleans.
        """
        function_expression = QuaProgramFunctionExpression(
            xor=QuaProgramFunctionExpressionXorFunction(_FunctionExpressions._standardize_args(*values)),
            loc=_get_loc(),
        )
        return QuaFunctionOutput(function_expression, bool)


class Broadcast:
    """A class that provides functionality for creating broadcast expressions.
    Broadcasting allows more control over making a locally measured variable available to all elements in the QUA program.
    """

    @staticmethod
    def _create_broadcast_expression(value: QuaFunctionOutput[bool]) -> QuaBroadcast[bool]:
        _get_root_program_scope().program.add_used_capability(QopCaps.broadcast)
        return QuaBroadcast(bool, value.unwrapped)

    @staticmethod
    def and_(*values: Union[Scalar[bool], QuaArrayVariable[bool]]) -> QuaBroadcast[bool]:
        """
        Preforms a logical AND operation on the input values and broadcasts the result to all elements in the QUA program.

        Args:
            *values (boolean, QUA boolean, Qua array of type boolean): The input values to be combined using a
                logical AND operation. Each input can be a single boolean, a QUA boolean or a QUA array of booleans.

        Returns:
            A boolean broadcast object, that can be used as input for any QUA command requiring a QUA boolean.
        """
        return Broadcast._create_broadcast_expression(_FunctionExpressions.and_(*values))

    @staticmethod
    def or_(*values: Union[Scalar[bool], QuaArrayVariable[bool]]) -> QuaBroadcast[bool]:
        """
        Preforms a logical OR operation on the input values and broadcasts the result to all elements in the QUA program.

        Args:
            *values (boolean, QUA boolean, Qua array of type boolean): The input values to be combined using a
                logical OR operation. Each input can be a single boolean, a QUA boolean or a QUA array of booleans.

        Returns:
            A boolean broadcast object, that can be used as input for any QUA command requiring a QUA boolean.
        """
        return Broadcast._create_broadcast_expression(_FunctionExpressions.or_(*values))

    @staticmethod
    def xor_(*values: Union[Scalar[bool], QuaArrayVariable[bool]]) -> QuaBroadcast[bool]:
        """
        Preforms a logical XOR (exclusive OR) operation on the input values and broadcasts the result to all elements in
        the QUA program.

        Args:
            *values (boolean, QUA boolean, Qua array of type boolean): The input values to be combined using a
                logical XOR operation. Each input can be a single boolean, a QUA boolean or a QUA array of booleans.

        Returns:
            A boolean broadcast object, that can be used as input for any QUA command requiring a QUA boolean.
        """
        return Broadcast._create_broadcast_expression(_FunctionExpressions.xor_(*values))


demod = RealAccumulationMethod(DemodIntegration)
dual_demod = DualAccumulationMethod(DualDemodIntegration)
integration = RealAccumulationMethod(BareIntegration)
dual_integration = DualAccumulationMethod(DualBareIntegration)
time_tagging = TimeTagging()
counting = Counting()
broadcast = Broadcast()


def stream_processing() -> _RAScope:
    """A context manager for the creation of [Stream processing pipelines](../../Guides/stream_proc.md#overview)

    Each pipeline defines an analysis process that is applied to every stream item.
    A pipeline must be terminated with a save/save_all terminal, and then can be retrieved with
    [QmJob.result_handles][qm.jobs.running_qm_job.RunningQmJob.result_handles].

    There are two save options: ``save_all`` will save every stream item, ``save`` will save only last item.

    A pipeline can be assigned to python variable, and then reused on other pipelines. It is ensured that the
    common part of the pipeline is processed only once.

    ??? example "Creating a result analysis object"
        ```python
        with stream_processing():
            a.save("tag")
            a.save_all("another tag")
        ```

    ??? example "Retrieving saved result"
        ```python
        QmJob.result_handles.get("tag")
        ```

    """
    prog = _get_scope_as_program()
    return _RAScope(prog.result_analysis)


FUNCTIONS = MapFunctions()


class _ResultStream(metaclass=abc.ABCMeta):
    def average(self) -> "UnaryMathOperation":
        """
        Perform a running average on a stream item. The Output of this operation is the running average
        of the values in the stream starting from the beginning of the QUA program.
        """
        return UnaryMathOperation(self, "average")

    def real(self) -> "UnaryMathOperation":
        return UnaryMathOperation(self, "real")

    def image(self) -> "UnaryMathOperation":
        return UnaryMathOperation(self, "image")

    def buffer(self, *args: int) -> "BufferOfStream":
        """Gather items into vectors - creates an array of input stream items and outputs the array as one item.
        only outputs full buffers.

        Note:
            The order of resulting dimensions is different when using a buffer with multiple inputs compared to using
            multiple buffers. The following two lines are equivalent:
            ```python
            stream.buffer(n, l, k)
            stream.buffer(k).buffer(l).buffer(n)
            ```

        Args:
            *args: number of items to gather, can either be a single
                number, which gives the results as a 1d array or
                multiple numbers for a multidimensional array.
        """
        return BufferOfStream(self, *args)

    def buffer_and_skip(self, length: Number, skip: Number) -> "SkippedBufferOfStream":
        """Gather items into vectors - creates an array of input stream items and outputs
        the array as one item.
        Skips the number of given elements. Note that length and skip start from the
        same index, so the `buffer(n)` command is equivalent to `buffer_and_skip(n, n)`.

        Only outputs full buffers.

        Example:
            ```python
            # The stream input is [1, 2, 3, 4, 5, 6, 7, 8, 9, 0]
            with stream_processing():
                stream.buffer(3).save_all("example1")
                stream.buffer_and_skip(3, 3).save_all("example2")
                stream.buffer_and_skip(3, 2).save_all("example3")
                stream.buffer_and_skip(3, 5).save_all("example4")
            # example1 -> [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
            # example2 -> [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
            # example3 -> [[1, 2, 3], [3, 4, 5], [5, 6, 7], [7, 8, 9]]
            # example4 -> [[1, 2, 3], [6, 7, 8]]
            ```
        Args:
            length: number of items to gather
            skip: number of items to skip for each buffer, starting from
                the same index as length
        """
        return SkippedBufferOfStream(self, int(length), int(skip))

    def map(self, function: FunctionBase) -> "MapOfStream":
        """Transform the item by applying a
        [function][qm.qua._stream_processing_map_functions.MapFunctions] to it

        Args:
            function: a function to transform each item to a different
                item. For example, to compute an average between
                elements in a buffer you should write
                ".buffer(len).map(FUNCTIONS.average())"
        """
        return MapOfStream(self, function)

    def flatten(self) -> "UnaryMathOperation":
        """
        Deconstruct an array item - and send its elements one by one as items
        """
        return UnaryMathOperation(self, "flatten")

    def skip(self, length: Number) -> "DiscardedStream":
        """Suppress the first n items of the stream

        Args:
            length: number of items to skip
        """
        return DiscardedStream(self, int(length), "skip")

    def skip_last(self, length: Number) -> "DiscardedStream":
        """Suppress the last n items of the stream

        Args:
            length: number of items to skip
        """
        return DiscardedStream(self, int(length), "skipLast")

    def take(self, length: Number) -> "DiscardedStream":
        """Outputs only the first n items of the stream

        Args:
            length: number of items to take
        """
        return DiscardedStream(self, int(length), "take")

    def histogram(self, bins: List[List[Number]]) -> "HistogramStream":
        """Compute the histogram of all items in stream

        Args:
            bins: vector or pairs. each pair indicates the edge of each
                bin. example: [[1,10],[11,20]] - two bins, one between 1
                and 10, second between 11 and 20
        """
        standardized_bins = [(_bin[0], _bin[1]) for _bin in bins]
        return HistogramStream(self, standardized_bins)

    def zip(self, other: "_ResultStream") -> "BinaryOperation":
        """Combine the emissions of two streams to one item that is a tuple of items of input streams

        Args:
            other: second stream to combine with self
        """
        return BinaryOperation(other, self, "zip")

    def save_all(self, tag: str) -> None:
        """Save all items received in stream.

        Args:
            tag: result name
        """
        ra = _get_scope_as_result_analysis()
        ra.save_all(tag, self)

    def save(self, tag: str) -> None:
        """Save only the last item received in stream

        Args:
            tag: result name
        """
        ra = _get_scope_as_result_analysis()
        ra.save(tag, self)

    def dot_product(self, vector: Sequence[Number]) -> "MapOfStream":
        """Computes dot product of the given vector and each item of the input stream

        Args:
            vector: constant vector of numbers
        """
        return self.map(DotProduct(vector))

    def tuple_dot_product(self) -> "MapOfStream":
        """
        Computes dot product of the given item of the input stream - that should include two vectors
        """
        return self.map(TupleDotProduct())

    def multiply_by(self, scalar_or_vector: OneOrMore[Number]) -> "MapOfStream":
        """Multiply the input stream item by a constant scalar or vector.
        The input item can be either scalar or vector.

        Args:
            scalar_or_vector: either a scalar number, or a vector of
                scalars.
        """
        if isinstance(scalar_or_vector, IterableClass):
            return self.map(MultiplyByVector(scalar_or_vector))
        else:
            return self.map(MultiplyByScalar(scalar_or_vector))

    def tuple_multiply(self) -> "MapOfStream":
        """
        Computes multiplication of the given item of the input stream - that can be any
        combination of scalar and vectors.
        """
        return self.map(TupleMultiply())

    def convolution(self, constant_vector: Sequence[Number], mode: Optional[ConvolutionMode] = "") -> "MapOfStream":
        """Computes discrete, linear convolution of one-dimensional constant vector and one-dimensional vector
        item of the input stream.

        Args:
            constant_vector: vector of numbers
            mode: "full", "same" or "valid"
        """
        if mode is None:
            warnings.warn(
                "mode=None is deprecated, use empty-string or (recommended) don't write the mode at-all.",
                DeprecationWarning,
            )
            mode = ""
        return self.map(Convolution(constant_vector, mode))

    def tuple_convolution(self, mode: Optional[ConvolutionMode] = "") -> "MapOfStream":
        """Computes discrete, linear convolution of two one-dimensional vectors that received as the one item from the input stream

        Args:
            mode: "full", "same" or "valid"
        """
        if mode is None:
            warnings.warn(
                "mode=None is deprecated, use empty-string or (recommended) don't write the mode at-all.",
                DeprecationWarning,
            )
            mode = ""
        return self.map(TupleConvolution(mode))

    def fft(self, output: Optional[str] = None) -> "MapOfStream":
        """Computes one-dimensional discrete fourier transform for every item in the
        stream.
        Item can be a vector of numbers, in this case fft will assume all imaginary
        numbers are 0.
        Item can also be a vector of number pairs - in this case for each pair - the
        first will be real and second imaginary.

        Args:
            output: supported from QOP 1.30 and QOP 2.0, options are
                "normal", "abs" and "angle":

                *   "normal" - Same as default (none), returns a 2d array of
                    size Nx2, where N is the length of the original vector.
                    The first item in each pair is the real part, and the 2nd
                    is the imaginary part.
                *   "abs" - Returns a 1d array of size N with the abs of the fft.
                *   "angle" - Returns the angle between the imaginary and real
                    parts in radians.

        Returns:
            stream object
        """
        return self.map(FFT(output))

    def boolean_to_int(self) -> "MapOfStream":
        """
        converts boolean to an integer number - 1 for true and 0 for false
        """
        return self.map(BooleanToInt())

    def to_proto(self) -> Value:
        return Value(list_value=ListValue(values=list(self._to_list_of_values())))

    @abc.abstractmethod
    def _to_list_of_values(self) -> Sequence[Value]:
        pass

    def add(self, other: Union["_ResultStream", OneOrMore[Number]]) -> "BinaryOperation":
        """Allows addition between streams. The addition is done element-wise.
        Can also be performed on buffers and other operators, but they must have the
        same dimensions.

        Example:
            ```python
            i = declare(int)
            j = declare(int)
            k = declare(int, value=5)
            stream = declare_stream()
            stream2 = declare_stream()
            stream3 = declare_stream()
            with for_(j, 0, j < 30, j + 1):
                with for_(i, 0, i < 10, i + 1):
                    save(i, stream)
                    save(j, stream2)
                    save(k, stream3)

            with stream_processing():
                (stream1 + stream2 + stream3).save_all("example1")
                (stream1.buffer(10) + stream2.buffer(10) + stream3.buffer(10)).save_all("example2")
                (stream1 + stream2 + stream3).buffer(10).average().save("example3")
            ```
        """
        return self.__add__(other)

    def subtract(self, other: Union["_ResultStream", OneOrMore[Number]]) -> "BinaryOperation":
        """Allows subtraction between streams. The subtraction is done element-wise.
        Can also be performed on buffers and other operators, but they must have the
        same dimensions.

        Example:
            ```python
            i = declare(int)
            j = declare(int)
            k = declare(int, value=5)
            stream = declare_stream()
            stream2 = declare_stream()
            stream3 = declare_stream()
            with for_(j, 0, j < 30, j + 1):
                with for_(i, 0, i < 10, i + 1):
                    save(i, stream)
                    save(j, stream2)
                    save(k, stream3)

            with stream_processing():
                (stream1 - stream2 - stream3).save_all("example1")
                (stream1.buffer(10) - stream2.buffer(10) - stream3.buffer(10)).save_all("example2")
                (stream1 - stream2 - stream3).buffer(10).average().save("example3")
            ```
        """
        return self.__sub__(other)

    def multiply(self, other: Union["_ResultStream", OneOrMore[Number]]) -> "BinaryOperation":
        """Allows multiplication between streams. The multiplication is done element-wise.
        Can also be performed on buffers and other operators, but they must have the
        same dimensions.

        Example:
            ```python
            i = declare(int)
            j = declare(int)
            k = declare(int, value=5)
            stream = declare_stream()
            stream2 = declare_stream()
            stream3 = declare_stream()
            with for_(j, 0, j < 30, j + 1):
                with for_(i, 0, i < 10, i + 1):
                    save(i, stream)
                    save(j, stream2)
                    save(k, stream3)

            with stream_processing():
                (stream1 * stream2 * stream3).save_all("example1")
                (stream1.buffer(10) * stream2.buffer(10) * stream3.buffer(10)).save_all("example2")
                (stream1 * stream2 * stream3).buffer(10).average().save("example3")
            ```
        """
        return self.__mul__(other)

    def divide(self, other: Union["_ResultStream", OneOrMore[Number]]) -> "BinaryOperation":
        """Allows division between streams. The division is done element-wise.
        Can also be performed on buffers and other operators, but they must have the
        same dimensions.

        Example:
            ```python
            i = declare(int)
            j = declare(int)
            k = declare(int, value=5)
            stream = declare_stream()
            stream2 = declare_stream()
            stream3 = declare_stream()
            with for_(j, 0, j < 30, j + 1):
                with for_(i, 0, i < 10, i + 1):
                    save(i, stream)
                    save(j, stream2)
                    save(k, stream3)

            with stream_processing():
                (stream1 / stream2 / stream3).save_all("example1")
                (stream1.buffer(10) / stream2.buffer(10) / stream3.buffer(10)).save_all("example2")
                (stream1 / stream2 / stream3).buffer(10).average().save("example3")
            ```
        """
        return self.__truediv__(other)

    def __add__(self, other: Union["_ResultStream", OneOrMore[Number]]) -> "BinaryOperation":
        return BinaryOperation(self, other, "+")

    def __radd__(self, other: OneOrMore[Number]) -> "BinaryOperation":
        return BinaryOperation(other, self, "+")

    def __sub__(self, other: Union["_ResultStream", OneOrMore[Number]]) -> "BinaryOperation":
        return BinaryOperation(self, other, "-")

    def __rsub__(self, other: Union["_ResultStream", OneOrMore[Number]]) -> "BinaryOperation":
        return BinaryOperation(other, self, "-")

    def __gt__(self, other: object) -> bool:
        raise QmQuaException("Can't use > operator on results")

    def __ge__(self, other: object) -> bool:
        raise QmQuaException("Can't use >= operator on results")

    def __lt__(self, other: object) -> bool:
        raise QmQuaException("Can't use < operator on results")

    def __le__(self, other: object) -> bool:
        raise QmQuaException("Can't use <= operator on results")

    def __eq__(self, other: object) -> bool:
        raise QmQuaException("Can't use == operator on results")

    def __mul__(self, other: Union["_ResultStream", OneOrMore[Number]]) -> "BinaryOperation":
        return BinaryOperation(self, other, "*")

    def __rmul__(self, other: Union["_ResultStream", OneOrMore[Number]]) -> "BinaryOperation":
        return BinaryOperation(other, self, "*")

    def __div__(self, other: Union["_ResultStream", OneOrMore[Number]]) -> None:
        raise QmQuaException("Can't use / operator on results")

    def __truediv__(self, other: Union["_ResultStream", OneOrMore[Number]]) -> "BinaryOperation":
        return BinaryOperation(self, other, "/")

    def __rtruediv__(self, other: Union["_ResultStream", OneOrMore[Number]]) -> "BinaryOperation":
        return BinaryOperation(other, self, "/")

    def __lshift__(self, other: ScalarOfAnyType) -> None:
        raise TypeError("Can't use << operator on results of type '_ResultStream', only '_ResultSource'")

    def __rshift__(self, other: Union["_ResultStream", OneOrMore[Number]]) -> None:
        raise QmQuaException("Can't use >> operator on results")

    def __and__(self, other: Union["_ResultStream", OneOrMore[Number]]) -> None:
        raise QmQuaException("Can't use & operator on results")

    def __or__(self, other: Union["_ResultStream", OneOrMore[Number]]) -> None:
        raise QmQuaException("Can't use | operator on results")

    def __xor__(self, other: Union["_ResultStream", OneOrMore[Number]]) -> None:
        raise QmQuaException("Can't use ^ operator on results")


class _ResultSourceTimestampMode(Enum):
    Values = 0
    Timestamps = 1
    ValuesAndTimestamps = 2


@dataclass
class _ResultSourceConfiguration:
    var_name: str
    timestamp_mode: _ResultSourceTimestampMode
    is_adc_trace: bool
    input: int
    auto_reshape: bool


class _ResultSource(_ResultStream):
    """A python object representing a source of values that can be processed in a [`stream_processing()`][qm.qua._dsl.stream_processing] pipeline

    This interface is chainable, which means that calling most methods on this object will create a new streaming source

    See the base class [_ResultStream][qm.qua._dsl._ResultStream] for operations
    """

    def __init__(self, configuration: _ResultSourceConfiguration):
        self._configuration = configuration

    @property
    def is_adc_trace(self) -> bool:
        return self._configuration.is_adc_trace

    def _to_list_of_values(self) -> Sequence[Value]:
        result = [
            Value(string_value=_RESULT_SYMBOL),
            Value(string_value=str(self._configuration.timestamp_mode.value)),
            Value(string_value=self._configuration.var_name),
        ]
        tmp = [
            Value(string_value="@macro_input"),
            Value(string_value=str(self._configuration.input)),
            Value(list_value=ListValue(values=result)),
        ]
        inputs = result if self._configuration.input == -1 else tmp
        macro_auto_reshape = [Value(string_value="@macro_auto_reshape"), Value(list_value=ListValue(values=inputs))]
        auto_reshape = macro_auto_reshape if self._configuration.auto_reshape else inputs
        macro_adc_trace = [Value(string_value="@macro_adc_trace"), Value(list_value=ListValue(values=auto_reshape))]
        return macro_adc_trace if self._configuration.is_adc_trace else auto_reshape

    def get_var_name(self) -> str:
        return self._configuration.var_name

    def with_timestamps(self) -> "_ResultSource":
        """Get a stream with the relevant timestamp for each stream-item"""
        return _ResultSource(
            dataclasses.replace(
                self._configuration,
                timestamp_mode=_ResultSourceTimestampMode.ValuesAndTimestamps,
            )
        )

    def timestamps(self) -> "_ResultSource":
        """Get a stream with only the timestamps of the stream-items"""
        return _ResultSource(
            dataclasses.replace(
                self._configuration,
                timestamp_mode=_ResultSourceTimestampMode.Timestamps,
            )
        )

    def input1(self) -> "_ResultSource":
        """A stream of raw ADC data from input 1. Only relevant when saving data from measure statement."""
        return _ResultSource(dataclasses.replace(self._configuration, input=1))

    def input2(self) -> "_ResultSource":
        """A stream of raw ADC data from input 2. Only relevant when saving data from measure statement."""
        return _ResultSource(dataclasses.replace(self._configuration, input=2))

    def auto_reshape(self) -> "_ResultSource":
        """Creates a buffer with dimensions according to the program structure in QUA.

        For example, when running the following program the result "reshaped" will have
        shape of (30,10):

        Example:
            ```python
            i = declare(int)
            j = declare(int)
            stream = declare_stream()
            with for_(i, 0, i < 30, i + 1):
                with for_(j, 0, j < 10, j + 1):
                    save(i, stream)

            with stream_processing():
                stream.auto_reshape().save_all("reshaped")
            ```
        """
        return _ResultSource(dataclasses.replace(self._configuration, auto_reshape=True))

    def __lshift__(self, other: ScalarOfAnyType) -> None:
        save(other, self)


class _UnaryOperation(_ResultStream, metaclass=abc.ABCMeta):
    def __init__(self, input_stream: "_ResultStream"):
        self._input_stream = input_stream

    def _to_list_of_values(self) -> Sequence[Value]:
        return [Value(string_value=self._operator_name)] + list(self._args) + [self._input_stream.to_proto()]

    @property
    @abc.abstractmethod
    def _operator_name(self) -> str:
        pass

    @property
    @abc.abstractmethod
    def _args(self) -> Sequence[Value]:
        pass


class UnaryMathOperation(_UnaryOperation):
    def __init__(
        self, input_stream: "_ResultStream", operator_name: Literal["average", "real", "image", "flatten", "tmult"]
    ) -> None:
        super().__init__(input_stream)
        self._operator = operator_name

    @property
    def _operator_name(self) -> str:
        return self._operator

    @property
    def _args(self) -> Sequence[Value]:
        return []


class BufferOfStream(_UnaryOperation):
    def __init__(self, input_stream: "_ResultStream", *args: int):
        super().__init__(input_stream)
        self._args_input = args

    @property
    def _args(self) -> List[Value]:
        return [Value(string_value=str(int(arg))) for arg in self._args_input]

    @property
    def _operator_name(self) -> str:
        return "buffer"


class SkippedBufferOfStream(_UnaryOperation):
    def __init__(self, input_stream: "_ResultStream", length: int, skip: int):
        super().__init__(input_stream)
        self._length = length
        self._skip = skip

    @property
    def _args(self) -> List[Value]:
        return [Value(string_value=str(self._length)), Value(string_value=str(self._skip))]

    @property
    def _operator_name(self) -> str:
        return "bufferAndSkip"


class MapOfStream(_UnaryOperation):
    def __init__(self, input_stream: "_ResultStream", function: FunctionBase):
        super().__init__(input_stream)
        self._function = function

    @property
    def _operator_name(self) -> str:
        return "map"

    @property
    def _args(self) -> List[Value]:
        return [self._function.to_proto()]


class DiscardedStream(_UnaryOperation):
    def __init__(self, input_stream: "_ResultStream", length: int, operator_name: Literal["skip", "skipLast", "take"]):
        super().__init__(input_stream)
        self._length = length
        self._operator_input = operator_name

    @property
    def _operator_name(self) -> str:
        return self._operator_input

    @property
    def _args(self) -> List[Value]:
        return [Value(string_value=str(self._length))]


class HistogramStream(_UnaryOperation):
    def __init__(self, input_stream: "_ResultStream", bins_: Sequence[Tuple[Number, Number]]):
        super().__init__(input_stream)
        self._bins = bins_

    @property
    def _operator_name(self) -> str:
        return "histogram"

    @property
    def _args(self) -> List[Value]:
        tmp = [Value(string_value=_ARRAY_SYMBOL)]
        converted_bins = [create_array(sub_list) for sub_list in self._bins]
        _bins = Value(list_value=ListValue(values=tmp + converted_bins))
        return [_bins]


class BinaryOperation(_ResultStream):
    def __init__(
        self,
        lhs: Union["_ResultStream", OneOrMore[Number]],
        rhs: Union["_ResultStream", OneOrMore[Number]],
        operator_name: Literal["+", "-", "*", "/", "zip"],
    ):
        self._lhs = lhs
        self._rhs = rhs
        self._operator_name = operator_name

    def _standardize_output(self, other: Union["_ResultStream", OneOrMore[Number]]) -> Value:
        if isinstance(other, _ResultStream):
            return other.to_proto()
        elif isinstance(other, (int, float, np.integer, np.floating)) and not isinstance(other, (bool, np.bool_)):
            return Value(string_value=str(other))
        elif isinstance(other, IterableClass):
            return create_array(other)
        if self._operator_name == "zip":
            raise TypeError(f"Unsupported zip for '{type(self._lhs)} and {type(self._rhs)}.")
        else:
            raise TypeError(f"Unsupported operation - '{type(self._lhs)} {self._operator_name} {type(self._rhs)}.")

    def _to_list_of_values(self) -> Sequence[Value]:
        return [
            Value(string_value=self._operator_name),
            self._standardize_output(self._lhs),
            self._standardize_output(self._rhs),
        ]


def _make_dict_from_args(args: Sequence[object], names: Sequence[str]) -> Dict[str, object]:
    return {name: arg for name, arg in zip(names, args)}
