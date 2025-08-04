from typing import Union

from qm._loc import _get_loc
from qm.api.models.capabilities import QopCaps
from qm.qua._expressions import Scalar, to_scalar_pb_expression
from qm.qua._scope_management.scopes_manager import scopes_manager
from qm.grpc.qua import (
    QuaProgramAnyStatement,
    QuaProgramVarRefExpression,
    QuaProgramZRotationStatement,
    QuaProgramAnyScalarExpression,
    QuaProgramResetFrameStatement,
    QuaProgramArrayVarRefExpression,
    QuaProgramQuantumElementReference,
    QuaProgramFastFrameRotationStatement,
)


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
    loc = _get_loc()
    for element in elements:
        statement = QuaProgramAnyStatement(
            z_rotation=QuaProgramZRotationStatement(
                loc=loc,
                value=QuaProgramAnyScalarExpression().from_dict(to_scalar_pb_expression(angle).to_dict()),
                qe=QuaProgramQuantumElementReference(name=element, loc=loc),
            )
        )
        scopes_manager.append_statement(statement)


def reset_frame(*elements: str) -> None:
    """Resets the frame of the oscillator associated with an element to 0.

    Used to reset all the frame updated made up to this statement.

    Args:
        *elements (str): a single element whose oscillator's phase will
            be reset. multiple elements can be given, in which case all
            of their oscillators' phases will be reset

    """
    loc = _get_loc()
    for element in elements:
        statement = QuaProgramAnyStatement(
            reset_frame=QuaProgramResetFrameStatement(
                loc=loc,
                qe=QuaProgramQuantumElementReference(name=element, loc=loc),
            )
        )
        scopes_manager.append_statement(statement)


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
    scopes_manager.program_scope.add_used_capability(QopCaps.fast_frame_rotation)
    loc = _get_loc()
    for element in elements:
        statement = QuaProgramAnyStatement(
            fast_frame_rotation=QuaProgramFastFrameRotationStatement(
                loc=loc,
                cosine=to_scalar_pb_expression(cosine),
                sine=to_scalar_pb_expression(sine),
                qe=QuaProgramQuantumElementReference(name=element, loc=loc),
            )
        )
        scopes_manager.append_statement(statement)
