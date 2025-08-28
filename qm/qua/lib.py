import random
import warnings
from typing import Any, List, Type, Tuple, Union, TypeVar, Callable, Optional, Sequence, overload

from qm._loc import _get_loc
from qm.type_hinting.general import NumberT
from qm.qua._dsl.variable_handling import assign, declare
from qm.utils import deprecation_message, get_iterable_elements_datatype
from qm.grpc.qua import (
    QuaProgramAnyScalarExpression,
    QuaProgramLibFunctionExpression,
    QuaProgramLibFunctionExpressionArgument,
)
from qm.qua._expressions import (
    Scalar,
    Vector,
    QuaVariable,
    ScalarOfAnyType,
    VectorOfAnyType,
    QuaArrayVariable,
    QuaLibFunctionOutput,
    fixed,
    create_qua_scalar_expression,
)

S = TypeVar("S", bool, int, float)
SomeCallable = Callable[..., Any]


def _get_func_lib_and_name(function: SomeCallable) -> Tuple[str, str]:
    lib_name, func_name = function.__qualname__.split(".")
    return lib_name.lower(), func_name


def _create_qua_vector_expression(value: Vector[NumberT]) -> QuaArrayVariable[NumberT]:
    if isinstance(value, QuaArrayVariable):
        return value
    data_type = get_iterable_elements_datatype(value)
    return declare(data_type, value=value)


def _standardize_args(*args: Union[ScalarOfAnyType, VectorOfAnyType]) -> List[QuaProgramLibFunctionExpressionArgument]:
    standardized_args = []

    for arg in args:
        # Checking if the argument is a vector, unfortunately python doesn't allow to use isinstance(arg, Vector)
        if isinstance(arg, (Sequence, QuaArrayVariable)):
            if isinstance(arg, Sequence):
                arg = _create_qua_vector_expression(arg)
            standardized_args.append(QuaProgramLibFunctionExpressionArgument(array=arg.unwrapped))
        else:
            arg = create_qua_scalar_expression(arg)
            standardized_args.append(QuaProgramLibFunctionExpressionArgument(scalar=arg.unwrapped))

    return standardized_args


def __create_output_expression(
    function: SomeCallable,
    output_type: Type[NumberT],
    *args: Union[ScalarOfAnyType, VectorOfAnyType],
) -> QuaLibFunctionOutput[NumberT]:
    standardized_args = _standardize_args(*args)
    lib_name, func_name = _get_func_lib_and_name(function)
    any_scalar_expression = QuaProgramAnyScalarExpression(
        lib_function=QuaProgramLibFunctionExpression(
            function_name=func_name, arguments=standardized_args, library_name=lib_name, loc=_get_loc()
        )
    )
    return QuaLibFunctionOutput(any_scalar_expression, output_type)


def _create_output_expression(
    function: SomeCallable, output_type: Type[NumberT], *args: ScalarOfAnyType
) -> QuaLibFunctionOutput[NumberT]:
    return __create_output_expression(function, output_type, *args)


def _create_vectors_output_expression(
    function: SomeCallable, output_type: Type[S], *args: VectorOfAnyType
) -> QuaLibFunctionOutput[S]:
    return __create_output_expression(function, output_type, *args)


def call_library_function(
    function: SomeCallable, output_type: Type[NumberT], *args: ScalarOfAnyType
) -> QuaLibFunctionOutput[NumberT]:
    warnings.warn(
        deprecation_message(
            method="call_library_function",
            deprecated_in="1.2.2",
            removed_in="1.4.0",
            details="""
Please call the required function directly from the available classes.
For instance, instead of using call_library_function(Random.rand_int, int, x, y), simply use Random(x).rand_int(y).""",
        )
    )
    return _create_output_expression(function, output_type, *args)


def call_vectors_library_function(
    function: SomeCallable, output_type: Type[S], *args: Vector[NumberT]
) -> QuaLibFunctionOutput[S]:
    warnings.warn(
        deprecation_message(
            method="call_vectors_library_function",
            deprecated_in="1.2.2",
            removed_in="1.4.0",
            details="""
Please call the required function directly from the available classes.
For instance, instead of using call_vectors_library_function(Math.sum, x.dtype, x), simply use Math.sum(x).""",
        )
    )
    return _create_vectors_output_expression(function, output_type, *args)


class Math:
    @staticmethod
    def log(x: Scalar[float], base: Scalar[float]) -> QuaLibFunctionOutput[float]:
        r"""Computes $\mathrm{log}_{base}(x)$

        Args:
            x: a QUA fixed larger than pow2(-8)=0.00390625
            base: a QUA fixed larger than pow2(1/8)=1.09051

        Returns:
            a QUA fixed
        """
        return _create_output_expression(Math.log, float, x, base)

    @staticmethod
    def pow(base: Scalar[float], x: Scalar[float]) -> QuaLibFunctionOutput[float]:
        r"""Computes ${base}^{x}$.
        Does not support base=1, nor the case where both base=0 & x=0.

        Args:
            base: a non-negative QUA fixed
            x: a QUA fixed

        Returns:
            a QUA fixed
        """
        return _create_output_expression(Math.pow, float, base, x)

    @staticmethod
    def div(x: Scalar[NumberT], y: Scalar[NumberT]) -> QuaLibFunctionOutput[float]:
        r"""Computes the division between two same-type variables $x/y$

        Args:
            x: a QUA parameter
            y: a QUA parameter not equal to 0

        Returns:
            a QUA fixed
        """
        return _create_output_expression(Math.div, float, x, y)

    @staticmethod
    def exp(x: Scalar[float]) -> QuaLibFunctionOutput[float]:
        r"""Computes $e^{x}$

        Args:
            x: a QUA fixed smaller than ln(8)=2.0794415416

        Returns:
            a QUA fixed
        """
        return _create_output_expression(Math.exp, float, x)

    @staticmethod
    def pow2(x: Scalar[float]) -> QuaLibFunctionOutput[float]:
        r"""Computes $2^{x}$

        Args:
            x: a QUA fixed smaller than 3 (to avoid overflow)

        Returns:
            a QUA fixed
        """
        return _create_output_expression(Math.pow2, float, x)

    @staticmethod
    def ln(x: Scalar[float]) -> QuaLibFunctionOutput[float]:
        r"""Computes $\mathrm{ln}(x)$

        Args:
            x: a QUA fixed larger than exp(-8)=0.0003354627

        Returns:
            a QUA fixed
        """
        return _create_output_expression(Math.ln, float, x)

    @staticmethod
    def log2(x: Scalar[float]) -> QuaLibFunctionOutput[float]:
        r"""Computes $\mathrm{log}_{2}(x)$

        Args:
            x: a QUA fixed larger than pow2(-8)=0.00390625

        Returns:
            a QUA fixed
        """
        return _create_output_expression(Math.log2, float, x)

    @staticmethod
    def log10(x: Scalar[float]) -> QuaLibFunctionOutput[float]:
        r"""Computes $\mathrm{log}_{10}(x)$

        Args:
            x: a QUA fixed larger than pow10(-8)=0.00000001

        Returns:
            a QUA fixed
        """
        return _create_output_expression(Math.log10, float, x)

    @staticmethod
    def sqrt(x: Scalar[float]) -> QuaLibFunctionOutput[float]:
        r"""Computes the square root of x

        Args:
            x: a non-negative QUA fixed

        Returns:
            a QUA fixed
        """
        return _create_output_expression(Math.sqrt, float, x)

    @staticmethod
    def inv_sqrt(x: Scalar[float]) -> QuaLibFunctionOutput[float]:
        r"""Computes the inverse square root of x

        Args:
            x: a QUA fixed larger than 1/64

        Returns:
            a QUA fixed
        """
        return _create_output_expression(Math.sqrt, float, x)

    @staticmethod
    def inv(x: Scalar[float]) -> QuaLibFunctionOutput[float]:
        r"""Computes the inverse of x

        Args:
            x: a QUA fixed which is x<=-1/8 or 1/8<x

        Returns:
            a QUA fixed
        """
        return _create_output_expression(Math.inv, float, x)

    @staticmethod
    def MSB(x: Scalar[NumberT]) -> QuaLibFunctionOutput[int]:
        r"""
        Finds the index of the most significant bit in the parameter x.
        Notes:

        - Result is independent of sign, for example, +3 and -3 will return the same msb
        - The returned value will be the closet log2, rounded down.

          This is given by $\mathrm{floor}(\mathrm{log}_2(|x|))$.

          For example:

          - msb(0.1) will return -4.
          - msb(5) will return 2.
        - For an integer, msb(0) will return 0.
        - For a fixed point number, msb(0) will return -28.

        Args:
            x: a QUA fixed or a QUA int

        Returns:
            a QUA int
        """
        return _create_output_expression(Math.MSB, int, x)

    @staticmethod
    def msb(x: Scalar[NumberT]) -> QuaLibFunctionOutput[int]:
        return Math.MSB(x)

    @staticmethod
    def elu(x: Scalar[float]) -> QuaLibFunctionOutput[float]:
        r"""Computes the Exponential Linear Unit activation function of x
          $\mathrm{ELU(x)} = \mathrm{max}(0, x) + \mathrm{min}(0, \mathrm{exp}(x)-1)$.

        Args:
            x: a QUA fixed

        Returns:
            a QUA fixed
        """
        return _create_output_expression(Math.elu, float, x)

    @staticmethod
    def aelu(x: Scalar[float]) -> QuaLibFunctionOutput[float]:
        r"""Computes faster an approximated Exponential Linear Unit activation function of x
          $\mathrm{aELU}(x) \sim \mathrm{ELU}(x)$

        Args:
            x: a QUA fixed

        Returns:
            a QUA fixed
        """
        return _create_output_expression(Math.aelu, float, x)

    @staticmethod
    def selu(x: Scalar[float]) -> QuaLibFunctionOutput[float]:
        r"""Computes the Scaled Exponential Linear Unit activation function of x
        $\mathrm{SELU}(x) = s*(\mathrm{max}(0, x)+a*\mathrm{min}(0, \mathrm{exp}(x)-1))$,
        $a=1.67326324$, $s=1.05070098$

        Args:
            x: a QUA fixed

        Returns:
            a QUA fixed
        """
        return _create_output_expression(Math.selu, float, x)

    @staticmethod
    def relu(x: Scalar[float]) -> QuaLibFunctionOutput[float]:
        r"""Computes the Rectified Linear Unit activation function of x
          $\mathrm{ReLU}(x) = \mathrm{max}(0, x)$

        Args:
            x: a QUA fixed

        Returns:
            a QUA fixed
        """
        return _create_output_expression(Math.relu, float, x)

    @staticmethod
    def plrelu(x: Scalar[float], a: Scalar[float]) -> QuaLibFunctionOutput[float]:
        r"""Computes the Parametric Leaky Rectified Linear Unit activation function of x
          $\mathrm{PLReLU}(x, a) = \mathrm{max}(0, x)+a*\mathrm{min}(0, x)$

        Args:
            x: a QUA fixed
            a: a QUA fixed

        Returns:
            a QUA fixed
        """
        return _create_output_expression(Math.plrelu, float, x, a)

    @staticmethod
    def lrelu(x: Scalar[float]) -> QuaLibFunctionOutput[float]:
        r"""Computes the Leaky Rectified Linear Unit activation function of x
          $\mathrm{LReLU}(x)=\mathrm{max}(0, x)+0.01*\mathrm{min}(0, x)$

        Args:
            x: a QUA fixed

        Returns:
            a QUA fixed
        """
        return _create_output_expression(Math.lrelu, float, x)

    @staticmethod
    def sin2pi(x: Scalar[float]) -> QuaLibFunctionOutput[float]:
        r"""Computes $\mathrm{sin}(2 \pi x)$.
        This is more efficient than `Math.sin(2*np.pi*x)`.
        In addition, this function is immune to overflows: An overflow means that the argument gets a $\pm 16$, which does not change the result due to the periodicity of the sine function.

        Args:
            x (QUA variable of type fixed): the angle in radians

        Returns:
            a QUA fixed
        """
        return _create_output_expression(Math.sin2pi, float, x)

    @staticmethod
    def cos2pi(x: Scalar[float]) -> QuaLibFunctionOutput[float]:
        r"""Computes $\mathrm{cos}(2 \pi x)$.
        This is more efficient than Math.cos($2 \pi x$).
        In addition, this function is immune to overflows: An overflow means that the argument gets a :math:`\pm 16`, which does not change the result due to the periodicity of the cosine function.

        Args:
            x (QUA variable of type fixed): the angle in radians

        Returns:
            a QUA fixed
        """
        return _create_output_expression(Math.cos2pi, float, x)

    @staticmethod
    def atan_2pi(x: Scalar[float]) -> QuaLibFunctionOutput[float]:
        r"""Computes $\mathrm{1/2 \pi * atan}(x)$

        -- Available from QOP 2.4 --

        Args:
            x (a QUA fixed): The tangent ratio (opposite/adjacent)

        Returns:
            a QUA fixed
        """
        return _create_output_expression(Math.atan_2pi, float, x)

    @staticmethod
    def atan2_2pi(y: Scalar[float], x: Scalar[float]) -> QuaLibFunctionOutput[float]:
        r"""Computes $\mathrm{1/2 \pi * atan2}(y,x)$

        -- Available from QOP 2.4 --

        Args:
            y (a QUA fixed): The coordinate y (opposite)
            x (a QUA fixed): The coordinate x (adjacent)

        Returns:
            a QUA fixed
        """
        return _create_output_expression(Math.atan2_2pi, float, y, x)

    @staticmethod
    def abs(x: Scalar[NumberT]) -> QuaLibFunctionOutput[float]:
        r"""Computes the absolute value of x

        Args:
            x: a QUA variable

        Returns:
            a QUA fixed
        """
        return _create_output_expression(Math.abs, float, x)

    @staticmethod
    def sin(x: Scalar[float]) -> QuaLibFunctionOutput[float]:
        r"""Computes $\mathrm{sin}(x)$

        Args:
            x (QUA variable of type fixed): the angle in radians

        Returns:
            a QUA fixed
        """
        return _create_output_expression(Math.sin, float, x)

    @staticmethod
    def atan(x: Scalar[float]) -> QuaLibFunctionOutput[float]:
        r"""Computes $\mathrm{atan}(x)$

        -- Available from QOP 2.4 --

        Args:
            x (a QUA fixed which is -1 <= x <= 1): the tangent ratio (opposite/adjacent)

        Returns:
            a QUA fixed
        """
        return _create_output_expression(Math.atan, float, x)

    @staticmethod
    def atan2(y: Scalar[float], x: Scalar[float]) -> QuaLibFunctionOutput[float]:
        r"""Computes $\mathrm{atan2}(y,x)$

        -- Available from QOP 2.4 --

        Args:
            y (a QUA fixed): the coordinate y (opposite)
            x (a QUA fixed): the coordinate x (adjacent)

        Returns:
            a QUA fixed
        """
        return _create_output_expression(Math.atan2, float, y, x)

    @staticmethod
    def cos(x: Scalar[float]) -> QuaLibFunctionOutput[float]:
        r"""Computes $\mathrm{cos}(x)$

        Args:
            x (QUA variable of type fixed): the angle in radians

        Returns:
            a QUA fixed
        """
        return _create_output_expression(Math.cos, float, x)

    @staticmethod
    def sum(x: Vector[NumberT]) -> QuaLibFunctionOutput[NumberT]:
        r"""Computes the sum of an array x

        Args:
            x: a QUA array

        Returns:
            the sum of the array, has same type as x
        """
        standard_x = _create_qua_vector_expression(x)
        return _create_vectors_output_expression(Math.sum, standard_x.dtype, standard_x)

    @staticmethod
    def max(x: Vector[NumberT]) -> QuaLibFunctionOutput[NumberT]:
        r"""Computes the max of an array x

        Args:
            x: a QUA array

        Returns:
            the max value of the array, has same type as x
        """
        standard_x = _create_qua_vector_expression(x)
        return _create_vectors_output_expression(Math.max, standard_x.dtype, standard_x)

    @staticmethod
    def min(x: Vector[NumberT]) -> QuaLibFunctionOutput[NumberT]:
        r"""Computes the min of an array x

        Args:
            x: a QUA array

        Returns:
            the min value of the array, has same type as x
        """
        standard_x = _create_qua_vector_expression(x)
        return _create_vectors_output_expression(Math.min, standard_x.dtype, standard_x)

    @staticmethod
    def argmax(x: Vector[NumberT]) -> QuaLibFunctionOutput[int]:
        r"""Return the index of the maximum of an array

        Args:
            x: a QUA array

        Returns:
            the index of maximum value of array, a QUA Integer
        """
        standard_x = _create_qua_vector_expression(x)
        return _create_vectors_output_expression(Math.argmax, int, standard_x)

    @staticmethod
    def argmin(x: Vector[NumberT]) -> QuaLibFunctionOutput[int]:
        r"""Return the index of the minimum of an array

        Args:
            x: a QUA array

        Returns:
            the index of minimum value of array, a QUA Integer
        """
        standard_x = _create_qua_vector_expression(x)
        return _create_vectors_output_expression(Math.argmin, int, standard_x)

    @staticmethod
    @overload
    def dot(x: Union[Vector[int], Vector[bool]], y: Union[Vector[int], Vector[bool]]) -> QuaLibFunctionOutput[int]:
        ...

    @staticmethod
    @overload
    def dot(x: Vector[float], y: VectorOfAnyType) -> QuaLibFunctionOutput[float]:
        ...

    @staticmethod
    @overload
    def dot(x: VectorOfAnyType, y: Vector[float]) -> QuaLibFunctionOutput[float]:
        ...

    @staticmethod
    def dot(x: VectorOfAnyType, y: VectorOfAnyType) -> Union[QuaLibFunctionOutput[float], QuaLibFunctionOutput[int]]:
        r"""Calculates a dot product of two QUA arrays of identical size.

        Args:
            x: a QUA array
            y: a QUA array

        Returns:
            The dot product of x and y.
            If either x or y is an array of type `Fixed`, then the result is `Fixed`. Otherwise, it is an `Int`

        Example:
            ```python
            assign(c, dot(a, b))
            ```
        """
        standard_x = _create_qua_vector_expression(x)  # type: ignore[misc]
        standard_y = _create_qua_vector_expression(y)  # type: ignore[misc]

        if issubclass(standard_x.dtype, float) or issubclass(standard_y.dtype, float):
            return _create_vectors_output_expression(Math.dot, fixed, standard_x, standard_y)
        else:
            return _create_vectors_output_expression(Math.dot, int, standard_x, standard_y)


class Cast:
    @staticmethod
    def mul_int_by_fixed(x: Scalar[int], y: Scalar[float]) -> QuaLibFunctionOutput[int]:
        r"""Multiplies an int x by a fixed y, returning an int

        Args:
            x: a QUA integer
            y: a QUA fixed

        Returns:
            a QUA int which equals x*y
        """
        return _create_output_expression(Cast.mul_int_by_fixed, int, x, y)

    @staticmethod
    def mul_fixed_by_int(x: Scalar[float], y: Scalar[int]) -> QuaLibFunctionOutput[float]:
        r"""Multiplies a fixed x by an int y, returning a fixed

        Args:
            x: a QUA fixed
            y: a QUA int

        Returns:
            a QUA fixed which equals x*y
        """
        return _create_output_expression(Cast.mul_fixed_by_int, float, x, y)

    @staticmethod
    def to_int(x: Scalar[NumberT]) -> QuaLibFunctionOutput[int]:
        r"""Casts a variable to int. Supports int, fixed or bool

        Args:
            x: a QUA variable

        Returns:
            a QUA int
        """
        return _create_output_expression(Cast.to_int, int, x)

    @staticmethod
    def to_fixed(x: Scalar[NumberT]) -> QuaLibFunctionOutput[float]:
        r"""Casts a variable to fixed. Supports int, fixed or bool

        Args:
            x: a QUA variable

        Returns:
            a QUA fixed
        """
        return _create_output_expression(Cast.to_fixed, float, x)

    @staticmethod
    def to_bool(x: Scalar[NumberT]) -> QuaLibFunctionOutput[bool]:
        r"""Casts a variable to bool. Supports int, fixed or bool

        Args:
            x: a QUA variable

        Returns:
            a QUA bool
        """
        return _create_output_expression(Cast.to_bool, bool, x)

    @staticmethod
    def unsafe_cast_int(x: Scalar[NumberT]) -> QuaLibFunctionOutput[int]:
        r"""Treats the given input variable, bitwise, as an integer.
        For a given fixed point number, this is equivalent to multiplying by
        $2^{28}$

        Supports int, fixed or bool.

        Args:
            x: a QUA variable

        Returns:
            a QUA int
        """
        return _create_output_expression(Cast.unsafe_cast_int, int, x)

    @staticmethod
    def unsafe_cast_fixed(x: Scalar[NumberT]) -> QuaLibFunctionOutput[float]:
        r"""Treats the given input variable, bitwise, as a fixed point number.
        For a given integer, this is equivalent to multiplying by $2^{-28}$

        Supports int, fixed or bool.

        Args:
            x: a QUA variable

        Returns:
            a QUA fixed
        """
        return _create_output_expression(Cast.unsafe_cast_fixed, float, x)

    @staticmethod
    def unsafe_cast_bool(x: Scalar[NumberT]) -> QuaLibFunctionOutput[bool]:
        r"""Treats the given input variable, bitwise, as a boolean.
        A boolean is determined by the right-most bit, so for a given integer, this is
        equivalent to a parity check.

        Supports int, fixed or bool.

        Warning:
            Saving a boolean number which was unsafely cast from an integer/fixed will give the wrong value in python.

        Args:
            x: a QUA variable

        Returns:
            a QUA bool
        """
        return _create_output_expression(Cast.unsafe_cast_bool, bool, x)


class Util:
    @staticmethod
    def cond(
        condition: Scalar[bool],
        true_result: Scalar[NumberT],
        false_result: Scalar[NumberT],
    ) -> QuaLibFunctionOutput[NumberT]:
        r"""Quick conditional operation. This is equivalent to a ternary operator available in some languages:
        i.e. `a ? b : c`, meaning `b` if `a` is true, or `c` if `a` is false.
        There is less computation overhead (less latency) when running this operation relative to the if conditional.

        Example:
            ```python
            assign(var, cond(a, b, c)) #where a is a boolean expression
            ```
        """
        true_result = create_qua_scalar_expression(true_result)
        return _create_output_expression(Util.cond, true_result.dtype, condition, true_result, false_result)


class Random:
    def __init__(self, seed: Optional[Scalar[int]] = None) -> None:
        r"""A class for generating pseudo-random numbers in QUA

        Args:
            seed: Optional. An integer / QUA integer seed for the pseudo-random number
                generator.
        """
        if seed is None:
            seed = random.randrange((1 << 28) - 1)

        if isinstance(seed, int):
            self._seed = declare(int, value=seed)
        elif isinstance(seed, QuaVariable):
            self._seed = seed
        else:
            # If seed is neither an int nor a QuaVariable, we still need it as a QuaVariable (and therefore use
            # 'declare') to support assignment (used in set_seed)
            self._seed = declare(int)
            self.set_seed(seed)

    def set_seed(self, exp: Scalar[int]) -> None:
        r"""Set the seed for the pseudo-random number generator

        Args:
            exp: a QUA expression
        """
        assign(self._seed, exp)

    def rand_int(self, max_int: Scalar[int]) -> QuaLibFunctionOutput[int]:
        r"""Returns a pseudorandom integer in range [0, max_int)

        Args:
            max_int: maximum value

        :Example:
            >>> a = Random()
            >>> assign(b, a.rand_int(max_int))
        """
        return _create_output_expression(Random.rand_int, int, self._seed, max_int)

    def rand_fixed(self) -> QuaLibFunctionOutput[float]:
        r"""Returns a pseudorandom fixed in range [0.0, 1.0)

        :Example:
            >>> a = Random()
            >>> assign(b, a.rand_fixed())
        """
        return _create_output_expression(Random.rand_fixed, float, self._seed)
