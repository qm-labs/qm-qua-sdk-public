from typing import Union

from qm.qua._dsl import function_expressions
from qm.api.models.capabilities import QopCaps
from qm.qua._scope_management.scopes_manager import scopes_manager
from qm.qua._expressions import Scalar, QuaBroadcast, QuaArrayVariable, QuaFunctionOutput


def _create_broadcast_expression(value: QuaFunctionOutput[bool]) -> QuaBroadcast[bool]:
    scopes_manager.program_scope.add_used_capability(QopCaps.broadcast)
    return QuaBroadcast(bool, value.unwrapped)


class broadcast:
    """
    A module that provides functionality for creating broadcast expressions.
    Broadcasting allows more control over making a locally measured variable available to all elements in the QUA program.
    """

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
        return _create_broadcast_expression(function_expressions.and_(*values))

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
        return _create_broadcast_expression(function_expressions.or_(*values))

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
        return _create_broadcast_expression(function_expressions.xor_(*values))
