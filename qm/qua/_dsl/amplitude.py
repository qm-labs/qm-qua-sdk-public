from typing import Tuple, Optional, overload

from qm.exceptions import QmQuaException
from qm.grpc.qua import QuaProgramAnyScalarExpression
from qm.qua._dsl._type_hints import MessageExpressionType
from qm.qua._expressions import Scalar, to_scalar_pb_expression

AmpValuesType = Tuple[
    MessageExpressionType,
    Optional[MessageExpressionType],
    Optional[MessageExpressionType],
    Optional[MessageExpressionType],
]


# Although _PulseAmp is a protected class, it is used by QUAM.
# Therefore, any breaking changes should be communicated to the QUAM authors.
class _PulseAmp:
    def __init__(
        self,
        v1: QuaProgramAnyScalarExpression,
        v2: Optional[QuaProgramAnyScalarExpression],
        v3: Optional[QuaProgramAnyScalarExpression],
        v4: Optional[QuaProgramAnyScalarExpression],
    ):
        if v1 is None:
            raise QmQuaException("amp can be one value or a matrix of 4")
        if v2 is None and v3 is None and v4 is None:
            pass
        elif v2 is not None and v3 is not None and v4 is not None:
            pass
        else:
            raise QmQuaException("amp can be one value or a matrix of 4.")

        self.v1 = v1
        self.v2 = v2
        self.v3 = v3
        self.v4 = v4

    def value(self) -> AmpValuesType:
        return self.v1, self.v2, self.v3, self.v4

    def __rmul__(self, other: str) -> Tuple[str, AmpValuesType]:
        return self * other

    def __mul__(self, other: str) -> Tuple[str, AmpValuesType]:
        if not isinstance(other, str):
            raise QmQuaException("you can multiply only a pulse")
        return other, self.value()


@overload
def amp(v1: Scalar[float]) -> _PulseAmp:
    ...


@overload
def amp(v1: Scalar[float], v2: Scalar[float], v3: Scalar[float], v4: Scalar[float]) -> _PulseAmp:
    ...


def amp(
    v1: Scalar[float],
    v2: Optional[Scalar[float]] = None,
    v3: Optional[Scalar[float]] = None,
    v4: Optional[Scalar[float]] = None,
) -> _PulseAmp:
    """To be used only within a [play][qm.qua.play] or [measure][qm.qua.measure] command, as a multiplication to
    the `operation`.

    It is possible to scale the pulse's amplitude dynamically by using the following syntax:

    ``play('pulse_name' * amp(v), 'element')``

    where ``v`` is QUA variable of type fixed. Range of v: -2 to $2 - 2^{-16}$ in steps of $2^{-16}$.

    Moreover, if the pulse is intended to a mixedInputs element and thus is defined with two waveforms,
    the two waveforms, described as a column vector, can be multiplied by a matrix:

    ``play('pulse_name' * amp(v_00, v_01, v_10, v_11), 'element'),``

    where ``v_ij``, i,j={0,1}, are QUA variables of type fixed.
    Note that ``v_ij`` should satisfy -2 <= ``v_ij`` <= $2 - 2{-16}$.

    Note that scaling in this manner, rather than in the configuration, might result
    in a computational overhead.
    See [QUA Best Practice Guide](../../Guides/best_practices.md#general) for more information.

    Args:
        v1: If only this variable is given, it is the scaler amplitude
            factor which multiples the `pulse` associated with the
            `operation`. If all variables are given, then it is the
            first element in the amplitude matrix which multiples the
            `pulse` associated with the `operation`.
        v2: The second element in the amplitude matrix which multiples
            the `pulse` associated with the `operation`.
        v3: The third element in the amplitude matrix which multiples
            the `pulse` associated with the `operation`.
        v4: The forth element in the amplitude matrix which multiples
            the `pulse` associated with the `operation`.
    """

    def _cast_number(v: Optional[Scalar[float]]) -> Optional[QuaProgramAnyScalarExpression]:
        if v is None:
            return None
        return to_scalar_pb_expression(v)

    return _PulseAmp(to_scalar_pb_expression(v1), _cast_number(v2), _cast_number(v3), _cast_number(v4))
