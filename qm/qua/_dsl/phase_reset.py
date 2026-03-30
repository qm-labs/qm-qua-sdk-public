import warnings

from qm._loc import _get_loc
from qm.grpc.qm.pb import inc_qua_pb2
from qm.utils import deprecation_message
from qm.qua._scope_management.scopes_manager import scopes_manager


def reset_phase(element: str) -> None:
    warnings.warn(
        deprecation_message(
            method="reset_phase",
            deprecated_in="1.2.2",
            removed_in="2.0.0",
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
          This also includes implicit align statements added by the compiler.
        * Reset phase will only reset the phase of the intermediate frequency (:math:`\\omega_{IF}`) currently in use.

    Args:
        element: an element
    """

    loc = _get_loc()
    statement = inc_qua_pb2.QuaProgram.ResetPhaseStatement(
        loc=loc, qe=inc_qua_pb2.QuaProgram.QuantumElementReference(name=element, loc=loc)
    )
    scopes_manager.append_statement(inc_qua_pb2.QuaProgram.AnyStatement(resetPhase=statement))


def reset_global_phase() -> None:
    """
    Resets the global phase of all the elements in the program.
    This will reset both the intermediate frequency phase and the upconverters/downconverters in use.

    Unlike `reset_if_phase()`, this is a standalone global instruction and is not attached to the next
    `play()` or `align()`.
    """
    statement = inc_qua_pb2.QuaProgram.ResetGlobalPhaseStatement(loc=_get_loc())
    scopes_manager.append_statement(inc_qua_pb2.QuaProgram.AnyStatement(resetGlobalPhase=statement))
