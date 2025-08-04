import logging
import warnings
from typing import List, Tuple, Union, Optional, overload

from qm._loc import _get_loc
from qm.exceptions import QmQuaException
from qm.qua._expressions import QuaVariable
from qm.qua._dsl.amplitude import AmpValuesType
from qm.qua._dsl.measure.measure_process_factories import demod
from qm.qua._scope_management.scopes_manager import scopes_manager
from qm.qua._dsl.measure.analog_measure_process import MeasureProcessAbstract
from qm.qua._dsl._utils import _TIMESTAMPS_LEGACY_SUFFIX, _standardize_timestamp_label
from qm.qua._dsl.stream_processing.stream_processing import StreamType, ResultStreamSource, declare_stream
from qm.grpc.qua import (
    QuaProgramAnyStatement,
    QuaProgramPulseReference,
    QuaProgramMeasureStatement,
    QuaProgramQuantumElementReference,
)

logger = logging.getLogger(__name__)

MeasurePulseType = Union[str, Tuple[str, AmpValuesType]]


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
            Pulse must have a ``measurement`` operation. Can also be multiplied by an [amp][qm.qua.amp].
        element (str): name of the element, as defined in the quantum machine configuration. The element must have outputs.
        *outputs (tuple): A parameter specifying the processing to be done on the ADC data, there are multiple options available, including demod(), integration() & time_tagging().
        stream (Union[str, ResultStreamSource]): Deprecated and replaced by `adc_stream`.
        timestamp_stream (Union[str, ResultStreamSource]): (Supported from QOP 2.2) Adding a `timestamp_stream` argument will save the time at which the operation occurred to a stream.
            If the `timestamp_stream` is a string ``label``, then the timestamp handle can be retrieved with [qm.results.StreamsManager][] with the same ``label``.
        adc_stream (Union[str, ResultStreamSource]): The stream variable into which the raw ADC data will be saved.
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
            if isinstance(outputs[0], (ResultStreamSource, str)):
                adc_stream = outputs[0]
                if isinstance(adc_stream, ResultStreamSource):
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

    _adc_stream: Optional[ResultStreamSource] = None
    if isinstance(adc_stream, str):
        _adc_stream = _declare_legacy_adc(adc_stream)
    else:
        if adc_stream is not None and (not isinstance(adc_stream, ResultStreamSource)):
            raise QmQuaException("stream object is not of the right type")
        _adc_stream = adc_stream

    if _adc_stream and not _adc_stream.is_adc_trace:
        logger.warning(
            "Streaming adc data without declaring the stream with "
            "`declare_stream(adc_trace=true)` might cause performance issues"
        )
    timestamp_label = _standardize_timestamp_label(timestamp_stream)
    processes = [x.unwrapped for x in measure_process]

    amp = None
    if isinstance(pulse, tuple):
        pulse, amp = pulse

    loc = _get_loc()
    statement = QuaProgramAnyStatement(
        measure=QuaProgramMeasureStatement(
            loc=loc,
            pulse=QuaProgramPulseReference(name=pulse, loc=loc),
            qe=QuaProgramQuantumElementReference(name=element, loc=loc),
        )
    )
    if _adc_stream is not None:
        statement.measure.stream_as = _adc_stream.get_var_name()

    for analog_process in processes:
        statement.measure.measure_processes.append(analog_process)

    if amp is not None:
        statement.measure.amp.loc = loc
        statement.measure.amp.v0 = amp[0]
        for i in range(1, 4, 1):
            if amp[i] is not None:
                setattr(statement.measure.amp, "v" + str(i), amp[i])

    if timestamp_label is not None:
        statement.measure.timestamp_label = timestamp_label

    scopes_manager.append_statement(statement)


def _declare_legacy_adc(tag: str) -> ResultStreamSource:
    program_scope = scopes_manager.program_scope
    result_object = program_scope.declared_streams.get(tag, None)
    if result_object is None:
        result_object = declare_stream(adc_trace=True)
        program_scope.add_stream_declaration(tag, result_object)
        result_object.input1()._auto_save_all(tag + "_input1")
        result_object.input1().timestamps()._auto_save_all(tag + "_input1" + _TIMESTAMPS_LEGACY_SUFFIX)
        result_object.input2()._auto_save_all(tag + "_input2")
        result_object.input2().timestamps()._auto_save_all(tag + "_input2" + _TIMESTAMPS_LEGACY_SUFFIX)

    return result_object
