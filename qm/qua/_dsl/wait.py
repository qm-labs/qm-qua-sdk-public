from typing import Tuple, Union, Optional, overload

from google.protobuf.empty_pb2 import Empty

from qm._loc import _get_loc
from qm.grpc.qm.pb import inc_qua_pb2
from qm.exceptions import QmQuaException
from qm.qua._dsl._type_hints import ElementRef
from qm.qua._scope_management.scopes_manager import scopes_manager
from qm.qua._expressions import Scalar, QuaVariable, to_scalar_pb_expression
from qm.qua._dsl._utils import _add_element_to_program, _add_elements_to_program
from qm.config import (
    Pulse,
    Element,
    SingleInput,
    SinglePulse,
    ComplexInput,
    ComplexPulse,
    ElementOutput,
    MultipleInputs,
    ConstantWaveform,
    SingleInputCollection,
)


def pause() -> None:
    """Pause the execution of the job until [qm.jobs.running_qm_job.RunningQmJob.resume][] is called.

    The quantum machines freezes on its current output state.
    """
    statement = inc_qua_pb2.QuaProgram.PauseStatement(loc=_get_loc(), qes=[])
    scopes_manager.append_statement(inc_qua_pb2.QuaProgram.AnyStatement(pause=statement))


def wait(duration: Scalar[int], *elements: ElementRef) -> None:
    r"""Wait for the given duration on all provided elements without outputting anything.
    Duration is in units of the clock cycle (4ns)

    Args:
        duration (Union[int,QUA variable of type int]): time to wait in
            units of the clock cycle (4ns).
        *elements (Union[str,sequence of str]): elements to wait on

    Note:

        The purpose of the `wait` operation is to add latency. In most cases, the
        latency added will be exactly the same as that specified by the QUA variable or
        the literal used. However, in some cases an additional computational latency may
        be added. If the actual wait time has significance, such as in characterization
        experiments, the actual wait time should always be verified with a simulator.

        The minimum accepted duration depends on the QOP version in use. See
        [Minimum Pulse and Wait Durations](../../Guides/timing_in_qua.md#minimum-pulse-and-wait-durations)
        in the documentation for details. Using a value smaller than the minimum accepted
        duration will result in unexpected behavior.

        When using a QUA variable for the duration, there is also a maximum accepted value. See
        [Maximum Pulse and Wait Durations](../../Guides/timing_in_qua.md#maximum-pulse-and-wait-durations)
        in the documentation for details. Using a value larger than the maximum accepted
        duration will result in unexpected behavior.
    """
    names = _add_elements_to_program(*elements)
    loc = _get_loc()
    time = inc_qua_pb2.QuaProgram.AnyScalarExpression()
    time.CopyFrom(to_scalar_pb_expression(duration))
    statement = inc_qua_pb2.QuaProgram.WaitStatement(
        loc=loc,
        time=time,
        qe=[inc_qua_pb2.QuaProgram.QuantumElementReference(name=name, loc=loc) for name in names],
    )
    scopes_manager.append_statement(inc_qua_pb2.QuaProgram.AnyStatement(wait=statement))


@overload
def wait_for_trigger(
    element: Element[ComplexInput, ElementOutput | None],
    pulse_to_play: ComplexPulse,
    trigger_element: Optional[Union[Tuple[str, str], str]] = None,
    time_tag_target: Optional[QuaVariable[int]] = None,
) -> None:
    pass


@overload
def wait_for_trigger(
    element: (
        Element[SingleInput, ElementOutput | None]
        | Element[SingleInputCollection, ElementOutput | None]
        | Element[MultipleInputs, ElementOutput | None]
    ),
    pulse_to_play: SinglePulse,
    trigger_element: Optional[Union[Tuple[str, str], str]] = None,
    time_tag_target: Optional[QuaVariable[int]] = None,
) -> None:
    pass


@overload
def wait_for_trigger(
    element: str,
    pulse_to_play: str,
    trigger_element: Optional[Union[Tuple[str, str], str]] = None,
    time_tag_target: Optional[QuaVariable[int]] = None,
) -> None:
    pass


def wait_for_trigger(
    element: ElementRef,
    pulse_to_play: str | Pulse | None = None,
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
    time_tag_target_pb = None if time_tag_target is None else time_tag_target.unwrapped.variable
    name = _add_element_to_program(element)
    if isinstance(pulse_to_play, Pulse):
        if isinstance(pulse_to_play, ComplexPulse):
            if not (
                isinstance(pulse_to_play.waveform_i, ConstantWaveform)
                and isinstance(pulse_to_play.waveform_q, ConstantWaveform)
            ):
                raise QmQuaException("When providing pulse to `wait_for_trigger` it should be constant pulse")
        if isinstance(pulse_to_play, SinglePulse):
            if not isinstance(pulse_to_play.waveform, ConstantWaveform):
                raise QmQuaException("When providing pulse to `wait_for_trigger` it should be constant pulse")
        if isinstance(element, Element):
            scopes_manager.program_scope.get_element(name).add_pulse(pulse_to_play)
        pulse_to_play = pulse_to_play.name
    loc = _get_loc()
    statement = inc_qua_pb2.QuaProgram.AnyStatement(
        waitForTrigger=inc_qua_pb2.QuaProgram.WaitForTriggerStatement(
            loc=loc,
            qe=[inc_qua_pb2.QuaProgram.QuantumElementReference(name=name, loc=loc)],
        )
    )

    if pulse_to_play is not None:
        statement.waitForTrigger.pulseToPlay.name = pulse_to_play
    if trigger_element is not None:
        if isinstance(trigger_element, tuple):
            el, out = trigger_element
            statement.waitForTrigger.elementOutput.CopyFrom(
                inc_qua_pb2.QuaProgram.WaitForTriggerStatement.ElementOutput(element=el, output=out)
            )
        else:
            statement.waitForTrigger.elementOutput.CopyFrom(
                inc_qua_pb2.QuaProgram.WaitForTriggerStatement.ElementOutput(element=trigger_element)
            )
    else:
        statement.waitForTrigger.globalTrigger.CopyFrom(Empty())
    if time_tag_target_pb is not None:
        statement.waitForTrigger.timeTagTarget.CopyFrom(time_tag_target_pb)

    scopes_manager.append_statement(statement)


def align(*elements: ElementRef) -> None:
    """Align several elements together.

    All the elements referenced in `elements` will wait for all the others to
    finish their currently running statement.

    If no arguments are given, the statement will align all the elements used in the program.

    Args:
        *elements (str): a single element, multiple elements, or none
    """
    loc = _get_loc()
    names = _add_elements_to_program(*elements)
    statement = inc_qua_pb2.QuaProgram.AlignStatement(
        loc=loc,
        qe=[inc_qua_pb2.QuaProgram.QuantumElementReference(name=name, loc=loc) for name in names],
    )
    scopes_manager.append_statement(inc_qua_pb2.QuaProgram.AnyStatement(align=statement))
