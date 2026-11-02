from typing_extensions import deprecated

from qm._loc import _get_loc
from qm.grpc.qm.pb import inc_qua_pb2
from qm.qua._dsl._type_hints import ElementRef
from qm.qua._dsl._utils import _add_element_to_program
from qm.utils.deprecation_utils import QmQuaDeprecationWarning
from qm.qua._scope_management.scopes_manager import scopes_manager


@deprecated(
    'reset_phase is deprecated since "1.2.2" and will be removed in "2.0.0". reset_if_phase instead',
    category=QmQuaDeprecationWarning,
    stacklevel=1,
)
def reset_phase(element: ElementRef) -> None:
    """Resets the intermediate frequency phase of the oscillator associated with ``element``.

    Deprecated since 1.2.2; will be removed in 2.0.0. Use ``reset_if_phase()`` instead.

    Args:
        element: the element whose oscillator phase is reset.
    """
    reset_if_phase(element)


def reset_if_phase(element: ElementRef) -> None:
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
    name = _add_element_to_program(element)
    statement = inc_qua_pb2.QuaProgram.ResetPhaseStatement(
        loc=loc, qe=inc_qua_pb2.QuaProgram.QuantumElementReference(name=name, loc=loc)
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
