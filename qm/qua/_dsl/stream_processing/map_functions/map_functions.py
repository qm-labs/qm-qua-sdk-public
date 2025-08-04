import warnings
from collections.abc import Iterable
from typing import Union, Optional, Sequence

from qm.type_hinting import Number
from qm.qua._dsl._type_hints import OneOrMore
from qm.qua._dsl.stream_processing.map_functions.map_function_classes import (
    FFT,
    Demod,
    Average,
    DotProduct,
    Convolution,
    BooleanToInt,
    TupleMultiply,
    ConvolutionMode,
    TupleDotProduct,
    MultiplyByScalar,
    MultiplyByVector,
    TupleConvolution,
)


class MapFunctions:
    @staticmethod
    def average(axis: Optional[OneOrMore[Number]] = None) -> Average:
        """Perform a running average on a stream item. The Output of this operation is the
        running average of the values in the stream starting from the beginning of the
        QUA program.

        Args:
            axis: optional Axis or axes along which to average.

        Returns:
            stream object
        """
        return Average(axis)

    @staticmethod
    def dot_product(vector: Sequence[Number]) -> DotProduct:
        """Computes dot product of the given vector and an item of the input stream

        Args:
            vector: constant vector of numbers

        Returns:
            stream object
        """
        return DotProduct(vector)

    @staticmethod
    def tuple_dot_product() -> TupleDotProduct:
        """Computes dot product between the two vectors of the input stream

        Returns:
            stream object
        """
        return TupleDotProduct()

    @staticmethod
    def multiply_by(scalar_or_vector: OneOrMore[Number]) -> Union[MultiplyByVector, MultiplyByScalar]:
        """Multiply the input stream item by a constant scalar or vector.
        the input item can be either scalar or vector.

        Args:
            scalar_or_vector: either a scalar number, or a vector of
                scalars.

        Returns:
            stream object
        """
        if isinstance(scalar_or_vector, Iterable):
            return MultiplyByVector(scalar_or_vector)
        else:
            return MultiplyByScalar(scalar_or_vector)

    @staticmethod
    def tuple_multiply() -> TupleMultiply:
        """Computes multiplication between the two elements of the input stream.
        Can be any combination of scalar and vectors.

        Returns:
            stream object
        """
        return TupleMultiply()

    @staticmethod
    def convolution(constant_vector: Sequence[Number], mode: Optional[ConvolutionMode] = "") -> Convolution:
        """Computes discrete, linear convolution of one-dimensional constant vector and
        one-dimensional vector item of the input stream.

        Args:
            constant_vector: vector of numbers
            mode: "full", "same" or "valid"

        Returns:
            stream object
        """
        if mode is None:
            warnings.warn(
                "mode=None is deprecated, use empty-string or (recommended) don't write the mode at-all.",
                DeprecationWarning,
            )
            mode = ""
        return Convolution(constant_vector, mode)

    @staticmethod
    def tuple_convolution(mode: Optional[ConvolutionMode] = "") -> TupleConvolution:
        """Computes discrete, linear convolution of two one-dimensional vectors of the
        input stream

        Args:
            mode: "full", "same" or "valid"

        Returns:
            stream object
        """
        if mode is None:
            warnings.warn(
                "mode=None is deprecated, use empty-string or (recommended) don't write the mode at-all.",
                DeprecationWarning,
            )
            mode = ""
        return TupleConvolution(mode)

    @staticmethod
    def fft(output: Optional[str] = None) -> FFT:
        """Computes one-dimensional discrete fourier transform for every item in the
        stream.
        Item can be a vector of numbers, in this case fft will assume all imaginary
        numbers are 0.
        Item can also be a vector of number pairs - in this case for each pair - the
        first will be real and second imaginary.

        Args:
            output: supported from QOP 1.30 and QOP 2.0, options are
                "normal", "abs" and "angle":

                *   "normal" - Same as default (none), returns a 2d array of
                    size Nx2, where N is the length of the original vector.
                    The first item in each pair is the real part, and the 2nd
                    is the imaginary part.
                *   "abs" - Returns a 1d array of size N with the abs of the fft.
                *   "angle" - Returns the angle between the imaginary and real
                    parts in radians.

        Returns:
            stream object
        """
        return FFT(output)

    @staticmethod
    def boolean_to_int() -> BooleanToInt:
        """
        Converts boolean to integer number - 1 for true and 0 for false

        Returns:
            stream object
        """
        return BooleanToInt()

    @staticmethod
    def demod(
        frequency: Number,
        iw_cos: OneOrMore[Number],
        iw_sin: OneOrMore[Number],
        *,
        integrate: Optional[bool] = None,
    ) -> Demod:
        """Demodulates the acquired data from the indicated stream at the given frequency
        and integration weights.
        If operating on a stream of tuples, assumes that the 2nd item is the timestamps
        and uses them for the demodulation, reproducing the demodulation performed
        in real time.
        If operated on a single stream, assumes that the first item is at time zero and
        that the elements are separated by 1ns.

        Args:
            frequency: frequency for demodulation calculation
            iw_cos: cosine integration weight. Integration weight can be
                either a scalar for constant integration weight, or a
                python iterable for arbitrary integration weights.
            iw_sin: sine integration weight. Integration weight can be
                either a scalar for constant integration weight, or a
                python iterable for arbitrary integration weights.
            integrate: sum the demodulation result and returns a scalar
                if True (default), else the demodulated stream without
                summation is returned

        Returns:
            stream object

        Example:
            ```python
            with stream_processing():
                adc_stream.input1().with_timestamps().map(FUNCTIONS.demod(freq, 1.0, 0.0, integrate=False)).average().save('cos_env')
                adc_stream.input1().with_timestamps().map(FUNCTIONS.demod(freq, 1.0, 0.0)).average().save('cos_result')  # Default is integrate=True
            ```

        Note:
            The demodulation in the stream processing **does not** take in consideration
            any real-time modifications to the frame, phase or frequency of the element.
            If the program has any QUA command that changes them, the result of the
            stream processing demodulation will be invalid.

        """
        return Demod(frequency, iw_cos, iw_sin, integrate)


FUNCTIONS = MapFunctions()
