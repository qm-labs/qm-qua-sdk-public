import logging
import warnings
from typing import List, Tuple, Union, TypeVar, Optional, overload

from qm._loc import _get_loc
from qm.grpc.qm.pb import inc_qua_pb2
from qm.exceptions import QmQuaException
from qm.qua._expressions import Scalar, QuaVariable
from qm.qua._dsl._utils import _standardize_timestamp_label
from qm.utils.deprecation_utils import QmQuaDeprecationWarning
from qm.qua._dsl.measure.measure_process_factories import demod
from qm.qua._scope_management.scopes_manager import scopes_manager
from qm.config._elements._analog_outputs import DEFAULT_OUT1, DEFAULT_OUT2
from qm.qua._dsl.measure.digital_measure_process import Counting as DigitalCounting
from qm.qua._dsl.stream_processing.stream_processing import StreamType, ResultStreamSource
from qm.qua._dsl.streams.output_streams.declare_output_stream import declare_output_stream
from qm.qua._dsl.measure.digital_measure_process import RawTimeTagging as DigitalRawTimeTagging
from qm.qua._dsl.amplitude import AmpValuesType, MeasurePulseType, AmplitudeScaleTypes, standardize_pulse_and_amplitude
from qm.qua._dsl.measure.analog_measure_process import (
    BasicIntegration,
    DualMeasureProcess,
    AnalogMeasureProcess,
    MeasureProcessAbstract,
    TimeTaggingMeasurementProcess,
)
from qm.config import (
    Pulse,
    Element,
    Operation,
    SingleInput,
    SinglePulse,
    ComplexInput,
    ComplexPulse,
    ElementInput,
    ComplexOutput,
    ElementOutput,
    SingleLfOutput,
    InputCollection,
)

logger = logging.getLogger(__name__)
MeasurableElement = Element[ElementInput, ElementOutput] | str
MeasureProcessT = TypeVar("MeasureProcessT", bound=MeasureProcessAbstract)


@overload
def measure(
    pulse: Tuple[str, AmpValuesType],
    element: str,
    *outputs: Union[Tuple[str, QuaVariable[float]], Tuple[str, str, QuaVariable[float]], MeasureProcessAbstract],
    timestamp_stream: Optional[StreamType] = None,
    adc_stream: Optional[StreamType] = None,
    amplitude_scale: None = None,
) -> None:
    pass


@overload
def measure(
    pulse: Tuple[str, AmpValuesType],
    element: str,
    stream: Optional[StreamType],
    *outputs: Union[Tuple[str, QuaVariable[float]], Tuple[str, str, QuaVariable[float]], MeasureProcessAbstract],
    timestamp_stream: Optional[StreamType] = None,
    adc_stream: Optional[StreamType] = None,
    amplitude_scale: None = None,
) -> None:
    pass


@overload
def measure(
    pulse: str,
    element: str,
    *outputs: Union[Tuple[str, QuaVariable[float]], Tuple[str, str, QuaVariable[float]], MeasureProcessAbstract],
    timestamp_stream: Optional[StreamType] = None,
    adc_stream: Optional[StreamType] = None,
    amplitude_scale: AmplitudeScaleTypes = None,
) -> None:
    pass


@overload
def measure(
    pulse: str,
    element: str,
    stream: Optional[StreamType],
    *outputs: Union[Tuple[str, QuaVariable[float]], Tuple[str, str, QuaVariable[float]], MeasureProcessAbstract],
    timestamp_stream: Optional[StreamType] = None,
    adc_stream: Optional[StreamType] = None,
    amplitude_scale: AmplitudeScaleTypes = None,
) -> None:
    pass


@overload
def measure(
    pulse: ComplexPulse,
    element: Element[ComplexInput, ElementOutput],
    *outputs: MeasureProcessAbstract,
    timestamp_stream: Optional[StreamType] = None,
    adc_stream: Optional[StreamType] = None,
    amplitude_scale: AmplitudeScaleTypes = None,
) -> None:
    pass


@overload
def measure(
    pulse: SinglePulse,
    element: Element[SingleInput, ElementOutput] | Element[InputCollection, ElementOutput],
    *outputs: MeasureProcessAbstract,
    timestamp_stream: Optional[StreamType] = None,
    adc_stream: Optional[StreamType] = None,
    amplitude_scale: Scalar[float] | None = None,
) -> None:
    pass


def measure(
    pulse: MeasurePulseType,
    element: MeasurableElement,
    *outputs: Union[
        Tuple[str, QuaVariable[float]],
        Tuple[str, str, QuaVariable[float]],
        MeasureProcessAbstract,
        Optional[StreamType],
    ],
    stream: Optional[StreamType] = None,
    timestamp_stream: Optional[StreamType] = None,
    adc_stream: Optional[StreamType] = None,
    amplitude_scale: AmplitudeScaleTypes = None,
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

                Using `measure` on a stream that was previously used with `save` or `send` may cause performance issues,
                 as the stream will no longer be treated as an ADC stream.
                If you are using the deprecated `declare_stream` function, note that streaming ADC data without specifying
                 `declare_stream(adc_trace=True)` may also cause performance issues.
        amplitude_scale (Union[float, Qua expression of type fixed, tuple of four float/Qua fixed expressions]): indicate the amplitude multiplier of the pulse.


    Example:
        ```python
        with program() as prog:
            I = declare(fixed)
            Q = declare(fixed)
            adc_st = declare_output_stream()

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
                        "Saving an adc stream now requires defining it at the end of the measure command with the `adc_stream` argument, e.g. `adc_stream=adc_st`. The current syntax is deprecated and will be removed in a 1.3",
                        QmQuaDeprecationWarning,
                        stacklevel=2,
                    )
                else:
                    warnings.warn(
                        f"Saving an adc stream now requires defining it at the end of the measure command with the `adc_stream` argument, e.g. `adc_stream='{adc_stream}'`. The current syntax is deprecated and will be removed in a 1.3",
                        QmQuaDeprecationWarning,
                        stacklevel=2,
                    )
                outputs = outputs[1:]
            elif outputs[0] is None:
                warnings.warn(
                    "Putting `None` to indicate no adc streaming is no longer required, please remove it from the measure call",
                    QmQuaDeprecationWarning,
                    stacklevel=2,
                )
                outputs = outputs[1:]
    else:
        warnings.warn(
            "The `stream` argument is deprecated and will be removed in a 1.3. Use the `adc_stream` argument instead",
            QmQuaDeprecationWarning,
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
            measure_process.append(_standardize_measure_process(output, element))
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
        if _adc_stream.is_adc_trace is False:
            # TODO: in the future (2.0.0), we will want to raise an error here instead of a warning.
            warnings.warn(
                "Using a single stream for both a `measure` command and a `save`/`send` statement may cause performance issues. "
                "This option is deprecated and will be removed in QUA 2.0.0. "
                "If you are using the deprecated `declare_stream` API, streaming ADC data without specifying `declare_stream(adc_trace=True)` may also cause performance issues",
                QmQuaDeprecationWarning,
                stacklevel=2,
            )
        elif _adc_stream.is_adc_trace is None:
            # In case the user declared the stream without explicitly specifying adc_trace, we automatically set it to True here.
            _adc_stream.is_adc_trace = True

    if isinstance(element, Element):
        if isinstance(pulse, Operation):
            pulse_name = pulse.name
            pulse_implementation = pulse[element]
        elif isinstance(pulse, Pulse):
            pulse_implementation = pulse
            pulse_name = pulse.name
        else:
            raise TypeError(f"Invalid pulse type: {type(pulse)}")

        scopes_manager.add_element(element)
        scope_element = scopes_manager.program_scope.get_element(element.name)
        element_name = element.name
        scope_element.add_pulse(pulse_implementation, pulse_name)
        scope_pulse = scope_element.get_pulse(pulse.name)
        for process in measure_process:
            if process.uses_string_api:
                scopes_manager.set_the_need_for_external_config()
            if isinstance(process, AnalogMeasureProcess):
                for iw_inst in process.integration_weights:
                    scope_pulse.add_integration_weights(iw_inst)
    else:
        element_name = element
        scopes_manager.set_the_need_for_external_config()

    timestamp_label = _standardize_timestamp_label(timestamp_stream)
    processes = [x.unwrapped for x in measure_process]

    pulse_name, amp = standardize_pulse_and_amplitude(pulse, amplitude_scale)

    loc = _get_loc()
    statement = inc_qua_pb2.QuaProgram.AnyStatement(
        measure=inc_qua_pb2.QuaProgram.MeasureStatement(
            loc=loc,
            pulse=inc_qua_pb2.QuaProgram.PulseReference(name=pulse_name, loc=loc),
            qe=inc_qua_pb2.QuaProgram.QuantumElementReference(name=element_name, loc=loc),
        )
    )
    if _adc_stream is not None:
        statement.measure.streamAs = _adc_stream.get_var_name()

    for analog_process in processes:
        statement.measure.measureProcesses.append(analog_process)

    if amp is not None:
        statement.measure.amp.loc = loc
        statement.measure.amp.v0.CopyFrom(amp[0])
        for i in range(1, 4, 1):
            if amp[i] is not None:
                getattr(statement.measure.amp, "v" + str(i)).CopyFrom(amp[i])

    if timestamp_label is not None:
        statement.measure.timestampLabel = timestamp_label

    scopes_manager.append_statement(statement)
    # add implicit save if needed
    for m in measure_process:
        m.save_stream_if_needed()


def _declare_legacy_adc(tag: str) -> ResultStreamSource:
    program_scope = scopes_manager.program_scope
    result_object = program_scope.declared_streams.get(tag, None)
    if result_object is None:
        result_object = declare_output_stream(adc_trace=True)
        program_scope.add_stream_declaration(tag, result_object)
        result_object.input1().with_timestamps()._auto_save_all(tag + "_input1")
        result_object.input2().with_timestamps()._auto_save_all(tag + "_input2")

    return result_object


class ElementOutputAmbiguity(QmQuaException):
    pass


class IncompatibleMeasurementProcess(QmQuaException):
    pass


def _standardize_measure_process(process: MeasureProcessT, element: MeasurableElement) -> MeasureProcessT:
    """
    This function sets the output name from the element output. The rule of the function is as follows:
    If the element has single output, and the process requires two element outputs (Dual measure process) - raise an error.
    If the element has single output, and the process requires a single name, fill it in from the element output
    when it is not set, otherwise make sure the given name is identical to the name in the element.
    If the element has a dual output, and the process requires two element outputs (Dual measure process), fill
    each in from the element output when not set, otherwise make sure the given names are identical, in order,
    to the element's out1/out2 names.
    If the element has a dual output, and the process requires a single name, make sure the name is set and that
    it matches one of the element's two output names, otherwise raise an error (not sure if the first output or
    second should be taken).
    """
    if isinstance(process, DualMeasureProcess):
        if isinstance(element, str):
            # No element config to consult - fall back to the legacy DEFAULT_OUT1/DEFAULT_OUT2 convention.
            if not process.element_output1:
                process.element_output1 = DEFAULT_OUT1
            if not process.element_output2:
                process.element_output2 = DEFAULT_OUT2
            return process
        output = element.output
        if not isinstance(output, ComplexOutput):
            raise IncompatibleMeasurementProcess(f"Element '{element.name}' does not support dual_demod")
        if not process.element_output1:
            process.element_output1 = output.out1_name
        if not process.element_output2:
            process.element_output2 = output.out2_name
        if process.element_output1 != output.out1_name:
            raise IncompatibleMeasurementProcess(
                f"Naming mismatch between output name in the process ({process.element_output1}) and output name in the"
                f" element ({output.out1_name}). Please provide the same name, or better, don't provide it at all"
            )
        if process.element_output2 != output.out2_name:
            raise IncompatibleMeasurementProcess(
                f"Naming mismatch between output name in the process ({process.element_output2}) and output name in the"
                f" element ({output.out2_name}). Please provide the same name, or better, don't provide it at all"
            )
        return process
    if isinstance(process, DigitalCounting):
        # counting can have multiple outputs (as a list), no need to edit.
        return process

    if isinstance(element, str):
        return process

    output = element.output

    if not isinstance(process, (BasicIntegration, TimeTaggingMeasurementProcess, DigitalRawTimeTagging)):
        raise QmQuaException(f"Not supported measure process type - {type(process)}")

    if isinstance(output, SingleLfOutput):
        if not process.element_output:
            process.element_output = output.name
        if process.element_output != output.name:
            raise ElementOutputAmbiguity(
                f"Naming mismatch between output name in the process ({process.element_output}) and output name in the"
                f" element ({output.name}). Please provide the same name, or better, don't provide it at all"
            )

    elif isinstance(output, ComplexOutput):
        if not process.element_output:
            raise ElementOutputAmbiguity(
                f"Element '{element.name}' has two outputs - '{output.out1_name}' and '{output.out2_name}'. "
                f"The measurement process must set the element's output explicitly"
            )
        if process.element_output not in (output.out1_name, output.out2_name):
            raise ElementOutputAmbiguity(
                f"Element '{element.name}' has two outputs - '{output.out1_name}' and '{output.out2_name}'. "
                f"The given output name ({process.element_output}) matches neither of them"
            )
    else:
        raise QmQuaException(f"Not supported output type - {output}")
    return process
