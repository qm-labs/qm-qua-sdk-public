from qm._loc import _get_loc
from qm.exceptions import QmQuaException
from qm.qua._expressions import Scalar, to_scalar_pb_expression
from qm.qua._scope_management.scopes_manager import scopes_manager
from qm.grpc.qua import (
    QuaProgramCorrection,
    QuaProgramAnyStatement,
    QuaProgramAnyScalarExpression,
    QuaProgramSetDcOffsetStatement,
    QuaProgramQuantumElementReference,
    QuaProgramUpdateFrequencyStatement,
    QuaProgramUpdateCorrectionStatement,
    QuaProgramUpdateFrequencyStatementUnits,
)


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
    try:
        units_enum = QuaProgramUpdateFrequencyStatementUnits[units]  # type: ignore[valid-type, type-arg]
    except KeyError:
        raise QmQuaException(f'unknown units "{units}"')

    loc = _get_loc()
    statement = QuaProgramUpdateFrequencyStatement(
        loc=loc,
        qe=QuaProgramQuantumElementReference(name=element, loc=loc),
        units=units_enum,
        keep_phase=keep_phase,
        value=QuaProgramAnyScalarExpression().from_dict(to_scalar_pb_expression(new_frequency).to_dict()),
    )
    scopes_manager.append_statement(QuaProgramAnyStatement(update_frequency=statement))


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

        Make sure to update the correction after you called [`update_frequency`][qm.qua.update_frequency]

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
    loc = _get_loc()
    statement = QuaProgramUpdateCorrectionStatement(
        loc=loc,
        qe=QuaProgramQuantumElementReference(name=element, loc=loc),
        correction=QuaProgramCorrection(
            c0=to_scalar_pb_expression(c00),
            c1=to_scalar_pb_expression(c01),
            c2=to_scalar_pb_expression(c10),
            c3=to_scalar_pb_expression(c11),
        ),
    )
    scopes_manager.append_statement(QuaProgramAnyStatement(update_correction=statement))


def set_dc_offset(element: str, element_input: str, offset: Scalar[float]) -> None:
    """Set the DC offset of an element's input to the given value.
    Up to QOP 3.5, this value will remain the DC offset until changed or until the Quantum Machine is closed.
    From QOP 3.5, the DC offset will be reset to the QM's idle value at the end of each program.

    -- Available from QOP 2.0 --

    Args:
        element: The element to update its DC offset
        element_input: The desired input of the element, can be 'single'
            for a 'singleInput' element or 'I' or 'Q' for a 'mixInputs'
            element
        offset: The offset to set
    """
    loc = _get_loc()
    statement = QuaProgramSetDcOffsetStatement(
        loc=loc,
        qe=QuaProgramQuantumElementReference(name=element, loc=loc),
        qe_input_reference=element_input,
        offset=to_scalar_pb_expression(offset),
    )
    scopes_manager.append_statement(QuaProgramAnyStatement(set_dc_offset=statement))
