from typing import Tuple, Union, Optional

from betterproto.lib.std.google.protobuf import Empty

from qm._loc import _get_loc
from qm.qua._scope_management.scopes_manager import scopes_manager
from qm.qua._expressions import Scalar, QuaVariable, to_scalar_pb_expression
from qm.grpc.qua import (
    QuaProgramAnyStatement,
    QuaProgramWaitStatement,
    QuaProgramAlignStatement,
    QuaProgramPauseStatement,
    QuaProgramAnyScalarExpression,
    QuaProgramQuantumElementReference,
    QuaProgramWaitForTriggerStatement,
    QuaProgramWaitForTriggerStatementElementOutput,
)


def pause() -> None:
    """Pause the execution of the job until [qm.jobs.running_qm_job.RunningQmJob.resume][] is called.

    The quantum machines freezes on its current output state.
    """
    statement = QuaProgramPauseStatement(loc=_get_loc(), qes=[])
    scopes_manager.append_statement(QuaProgramAnyStatement(pause=statement))


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
    loc = _get_loc()
    statement = QuaProgramWaitStatement(
        loc=loc,
        time=QuaProgramAnyScalarExpression().from_dict(to_scalar_pb_expression(duration).to_dict()),
        qe=[QuaProgramQuantumElementReference(name=element, loc=loc) for element in elements],
    )
    scopes_manager.append_statement(QuaProgramAnyStatement(wait=statement))


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
    time_tag_target_pb = None if time_tag_target is None else time_tag_target.unwrapped.variable

    loc = _get_loc()
    statement = QuaProgramAnyStatement(
        wait_for_trigger=QuaProgramWaitForTriggerStatement(
            loc=loc,
            qe=[QuaProgramQuantumElementReference(name=element, loc=loc)],
        )
    )

    if pulse_to_play is not None:
        statement.wait_for_trigger.pulse_to_play.name = pulse_to_play
    if trigger_element is not None:
        if isinstance(trigger_element, tuple):
            el, out = trigger_element
            statement.wait_for_trigger.element_output = QuaProgramWaitForTriggerStatementElementOutput(
                element=el, output=out
            )
        else:
            statement.wait_for_trigger.element_output = QuaProgramWaitForTriggerStatementElementOutput(
                element=trigger_element
            )
    else:
        statement.wait_for_trigger.global_trigger = Empty()
    if time_tag_target_pb is not None:
        statement.wait_for_trigger.time_tag_target = time_tag_target_pb

    scopes_manager.append_statement(statement)


def align(*elements: str) -> None:
    """Align several elements together.

    All the elements referenced in `elements` will wait for all the others to
    finish their currently running statement.

    If no arguments are given, the statement will align all the elements used in the program.

    Args:
        *elements (str): a single element, multiple elements, or none
    """
    loc = _get_loc()
    statement = QuaProgramAlignStatement(
        loc=loc,
        qe=[QuaProgramQuantumElementReference(name=element, loc=loc) for element in elements],
    )
    scopes_manager.append_statement(QuaProgramAnyStatement(align=statement))
