"""
A module that provides functionality for creating function expressions, a specific type of AnyScalarExpression.
Currently, all function expressions are exclusively accessible to users through the broadcast object.
This approach is a newer and improved alternative to the functionality provided by LibFunctions, and it works in
much the same way. However, unlike LibFunctions, each function in this class has its own dedicated Proto message for
its description. This results in a significantly clearer API, as opposed to LibFunctions, where all functions share
the same Proto message, making it more challenging to understand the purpose of individual functions.
"""

from typing import List, Union

from qm._loc import _get_loc
from qm.type_hinting import NumberT
from qm.grpc.qm.pb import inc_qua_pb2
from qm.qua._expressions import Scalar, QuaArrayVariable, QuaFunctionOutput, create_qua_scalar_expression


def _standardize_args(
    *args: Union[Scalar[NumberT], QuaArrayVariable[NumberT]]
) -> List[inc_qua_pb2.QuaProgram.FunctionExpression.ScalarOrVectorArgument]:
    standardized_args = []

    for arg in args:
        if isinstance(arg, QuaArrayVariable):
            standardized_args.append(
                inc_qua_pb2.QuaProgram.FunctionExpression.ScalarOrVectorArgument(array=arg.unwrapped)
            )
        else:
            arg = create_qua_scalar_expression(arg)
            standardized_args.append(
                inc_qua_pb2.QuaProgram.FunctionExpression.ScalarOrVectorArgument(scalar=arg.unwrapped)
            )

    return standardized_args


def and_(*values: Union[Scalar[bool], QuaArrayVariable[bool]]) -> QuaFunctionOutput[bool]:
    """Performs a logical AND operation on the input values.

    Args:
        *values (boolean, QUA boolean, Qua array of type boolean): The input values to be combined using a
            logical AND operation. Each input can be a single boolean, a QUA boolean or a QUA array of booleans.
    """
    function_expression = inc_qua_pb2.QuaProgram.FunctionExpression(loc=_get_loc())
    getattr(function_expression, "and").CopyFrom(
        inc_qua_pb2.QuaProgram.FunctionExpression.AndFunction(values=_standardize_args(*values))
    )
    return QuaFunctionOutput(function_expression, bool)


def or_(*values: Union[Scalar[bool], QuaArrayVariable[bool]]) -> QuaFunctionOutput[bool]:
    """Performs a logical OR operation on the input values.

    Args:
        *values (boolean, QUA boolean, Qua array of type boolean): The input values to be combined using a
            logical OR operation. Each input can be a single boolean, a QUA boolean or a QUA array of booleans.
    """
    function_expression = inc_qua_pb2.QuaProgram.FunctionExpression(loc=_get_loc())
    getattr(function_expression, "or").CopyFrom(
        inc_qua_pb2.QuaProgram.FunctionExpression.OrFunction(values=_standardize_args(*values))
    )
    return QuaFunctionOutput(function_expression, bool)


def xor_(*values: Union[Scalar[bool], QuaArrayVariable[bool]]) -> QuaFunctionOutput[bool]:
    """Performs a logical XOR (exclusive OR) operation on the input values.

    Args:
        *values (boolean, QUA boolean, Qua array of type boolean): The input values to be combined using a
            logical XOR operation. Each input can be a single boolean, a QUA boolean, or a QUA array of booleans.
    """
    function_expression = inc_qua_pb2.QuaProgram.FunctionExpression(
        xor=inc_qua_pb2.QuaProgram.FunctionExpression.XorFunction(values=_standardize_args(*values)),
        loc=_get_loc(),
    )
    return QuaFunctionOutput(function_expression, bool)
