import warnings

from qm._loc import _get_loc
from qm.utils import deprecation_message
from qm.qua._scope_management.scopes_manager import scopes_manager
from qm.grpc.qua import (
    QuaProgramAnyStatement,
    QuaProgramResetPhaseStatement,
    QuaProgramQuantumElementReference,
    QuaProgramResetGlobalPhaseStatement,
)


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

    loc = _get_loc()
    statement = QuaProgramResetPhaseStatement(loc=loc, qe=QuaProgramQuantumElementReference(name=element, loc=loc))
    scopes_manager.append_statement(QuaProgramAnyStatement(reset_phase=statement))


def reset_global_phase() -> None:
    """
    Resets the global phase of all the elements in the program.
    This will reset both the intermediate frequency phase and the upconverters/downconverters in use.
    """
    statement = QuaProgramResetGlobalPhaseStatement(loc=_get_loc())
    scopes_manager.append_statement(QuaProgramAnyStatement(reset_global_phase=statement))
