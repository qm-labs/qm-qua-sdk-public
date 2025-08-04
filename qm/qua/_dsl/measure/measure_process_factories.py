import abc
from typing import Any, Dict, Type, Union, Optional, Sequence, overload

from qm.exceptions import QmQuaException
from qm.qua._expressions import QuaVariable, QuaArrayCell, QuaArrayVariable
from qm.qua._dsl.measure.analog_measure_process import RawTimeTagging as AnalogRawTimeTagging
from qm.qua._dsl.measure.digital_measure_process import RawTimeTagging as DigitalRawTimeTagging
from qm.qua._dsl.measure.digital_measure_process import Counting as DigitalMeasureProcessCounting
from qm.qua._dsl.measure.analog_measure_process import (
    BareIntegration,
    BasicIntegration,
    DemodIntegration,
    DualMeasureProcess,
    HighResTimeTagging,
    ScalarProcessTarget,
    VectorProcessTarget,
    DualDemodIntegration,
    SlicedAnalogTimeDivision,
    AccumulatedAnalogTimeDivision,
    MovingWindowAnalogTimeDivision,
)

DEFAULT_OUT1 = "out1"
DEFAULT_OUT2 = "out2"


class _AccumulationMethod(metaclass=abc.ABCMeta):
    loc = ""

    @classmethod
    def _full_target(cls, target: Union[QuaVariable[float], QuaArrayCell[float]]) -> ScalarProcessTarget:
        return ScalarProcessTarget(cls.loc, target)

    @classmethod
    def _sliced_target(cls, target: QuaArrayVariable[float], samples_per_chunk: int) -> VectorProcessTarget:
        analog_time_division = SlicedAnalogTimeDivision(cls.loc, samples_per_chunk)
        return VectorProcessTarget(cls.loc, target, analog_time_division)

    @classmethod
    def _accumulated_target(cls, target: QuaArrayVariable[float], samples_per_chunk: int) -> VectorProcessTarget:
        analog_time_division = AccumulatedAnalogTimeDivision(cls.loc, samples_per_chunk)
        return VectorProcessTarget(cls.loc, target, analog_time_division)

    @classmethod
    def _moving_window_target(
        cls, target: QuaArrayVariable[float], samples_per_chunk: int, chunks_per_window: int
    ) -> VectorProcessTarget:
        analog_time_division = MovingWindowAnalogTimeDivision(cls.loc, samples_per_chunk, chunks_per_window)
        return VectorProcessTarget(cls.loc, target, analog_time_division)


class _RealAccumulationMethod(_AccumulationMethod, metaclass=abc.ABCMeta):
    @classmethod
    @abc.abstractmethod
    def _get_return_func(cls) -> Type[BasicIntegration]:
        pass

    @classmethod
    def full(
        cls, iw: str, target: Union[QuaVariable[float], QuaArrayCell[float]], element_output: str = ""
    ) -> BasicIntegration:
        return cls._get_return_func()(element_output, iw, cls._full_target(target))

    @classmethod
    def sliced(
        cls,
        iw: str,
        target: QuaArrayVariable[float],
        samples_per_chunk: int,
        element_output: str = "",
    ) -> BasicIntegration:
        return cls._get_return_func()(element_output, iw, cls._sliced_target(target, samples_per_chunk))

    @classmethod
    def accumulated(
        cls,
        iw: str,
        target: QuaArrayVariable[float],
        samples_per_chunk: int,
        element_output: str = "",
    ) -> BasicIntegration:
        return cls._get_return_func()(element_output, iw, cls._accumulated_target(target, samples_per_chunk))

    @classmethod
    def moving_window(
        cls,
        iw: str,
        target: QuaArrayVariable[float],
        samples_per_chunk: int,
        chunks_per_window: int,
        element_output: str = "",
    ) -> BasicIntegration:
        return cls._get_return_func()(
            element_output,
            iw,
            cls._moving_window_target(target, samples_per_chunk, chunks_per_window),
        )


class _DualAccumulationMethod(_AccumulationMethod, metaclass=abc.ABCMeta):
    @classmethod
    @abc.abstractmethod
    def _get_return_func(cls) -> Type[DualMeasureProcess]:
        pass

    @staticmethod
    def _make_dict_from_args(args: Sequence[object], names: Sequence[str]) -> Dict[str, object]:
        return {name: arg for name, arg in zip(names, args)}

    @overload
    @classmethod
    def full(
        cls,
        iw1: str,
        iw2: str,
        target: Union[QuaVariable[float], QuaArrayCell[float]],
    ) -> DualMeasureProcess:
        ...

    @overload
    @classmethod
    def full(
        cls,
        iw1: str,
        element_output1: str,
        iw2: str,
        element_output2: str,
        target: Union[QuaVariable[float], QuaArrayCell[float]],
    ) -> DualMeasureProcess:
        ...

    @classmethod
    def full(cls, *args: Any, **kwargs: Any) -> DualMeasureProcess:
        if len(args) + len(kwargs) == 3:
            kwargs.update(_DualAccumulationMethod._make_dict_from_args(args, ["iw1", "iw2", "target"]))
            kwargs["element_output1"] = DEFAULT_OUT1
            kwargs["element_output2"] = DEFAULT_OUT2
            return cls.full(**kwargs)
        elif len(args) + len(kwargs) == 5:
            kwargs.update(
                _DualAccumulationMethod._make_dict_from_args(
                    args, ["iw1", "element_output1", "iw2", "element_output2", "target"]
                )
            )
        else:
            raise QmQuaException("Invalid number of arguments")

        return cls._get_return_func()(
            kwargs["element_output1"],
            kwargs["element_output2"],
            kwargs["iw1"],
            kwargs["iw2"],
            cls._full_target(kwargs["target"]),
        )

    @overload
    @classmethod
    def sliced(
        cls,
        iw1: str,
        iw2: str,
        samples_per_chunk: int,
        target: QuaArrayVariable[float],
    ) -> DualMeasureProcess:
        pass

    @overload
    @classmethod
    def sliced(
        cls,
        iw1: str,
        element_output1: str,
        iw2: str,
        element_output2: str,
        samples_per_chunk: int,
        target: QuaArrayVariable[float],
    ) -> DualMeasureProcess:
        pass

    @classmethod
    def sliced(cls, *args: Any, **kwargs: Any) -> DualMeasureProcess:
        """This feature is currently not supported in QUA"""
        if len(args) + len(kwargs) == 4:
            kwargs.update(
                _DualAccumulationMethod._make_dict_from_args(args, ["iw1", "iw2", "samples_per_chunk", "target"])
            )
            kwargs["element_output1"] = DEFAULT_OUT1
            kwargs["element_output2"] = DEFAULT_OUT2
            return cls.sliced(**kwargs)
        elif len(args) + len(kwargs) == 6:
            kwargs.update(
                _DualAccumulationMethod._make_dict_from_args(
                    args,
                    ["iw1", "element_output1", "iw2", "element_output2", "samples_per_chunk", "target"],
                )
            )
        else:
            raise QmQuaException("Invalid number of arguments")

        return cls._get_return_func()(
            kwargs["element_output1"],
            kwargs["element_output2"],
            kwargs["iw1"],
            kwargs["iw2"],
            cls._sliced_target(kwargs["target"], kwargs["samples_per_chunk"]),
        )

    @overload
    @classmethod
    def accumulated(
        cls,
        iw1: str,
        iw2: str,
        samples_per_chunk: int,
        target: QuaArrayVariable[float],
    ) -> DualMeasureProcess:
        pass

    @overload
    @classmethod
    def accumulated(
        cls,
        iw1: str,
        element_output1: str,
        iw2: str,
        element_output2: str,
        samples_per_chunk: int,
        target: QuaArrayVariable[float],
    ) -> DualMeasureProcess:
        pass

    @classmethod
    def accumulated(cls, *args: Any, **kwargs: Any) -> DualMeasureProcess:
        """This feature is currently not supported in QUA"""
        if len(args) + len(kwargs) == 4:
            kwargs.update(
                _DualAccumulationMethod._make_dict_from_args(args, ["iw1", "iw2", "samples_per_chunk", "target"])
            )
            kwargs["element_output1"] = DEFAULT_OUT1
            kwargs["element_output2"] = DEFAULT_OUT2
            return cls.accumulated(**kwargs)
        elif len(args) + len(kwargs) == 6:
            kwargs.update(
                _DualAccumulationMethod._make_dict_from_args(
                    args,
                    ["iw1", "element_output1", "iw2", "element_output2", "samples_per_chunk", "target"],
                )
            )
        else:
            raise QmQuaException("Invalid number of arguments")

        return cls._get_return_func()(
            kwargs["element_output1"],
            kwargs["element_output2"],
            kwargs["iw1"],
            kwargs["iw2"],
            cls._accumulated_target(kwargs["target"], kwargs["samples_per_chunk"]),
        )

    @overload
    @classmethod
    def moving_window(
        cls,
        iw1: str,
        iw2: str,
        samples_per_chunk: int,
        chunks_per_window: int,
        target: QuaArrayVariable[float],
    ) -> DualMeasureProcess:
        pass

    @overload
    @classmethod
    def moving_window(
        cls,
        iw1: str,
        element_output1: str,
        iw2: str,
        element_output2: str,
        samples_per_chunk: int,
        chunks_per_window: int,
        target: QuaArrayVariable[float],
    ) -> DualMeasureProcess:
        pass

    @classmethod
    def moving_window(cls, *args: Any, **kwargs: Any) -> DualMeasureProcess:
        """This feature is currently not supported in QUA"""
        if len(args) + len(kwargs) == 5:
            kwargs.update(
                _DualAccumulationMethod._make_dict_from_args(
                    args, ["iw1", "iw2", "samples_per_chunk", "chunks_per_window", "target"]
                )
            )
            kwargs["element_output1"] = DEFAULT_OUT1
            kwargs["element_output2"] = DEFAULT_OUT2
            return cls.moving_window(**kwargs)
        elif len(args) + len(kwargs) == 7:
            kwargs.update(
                _DualAccumulationMethod._make_dict_from_args(
                    args,
                    [
                        "iw1",
                        "element_output1",
                        "iw2",
                        "element_output2",
                        "samples_per_chunk",
                        "chunks_per_window",
                        "target",
                    ],
                )
            )
        else:
            raise QmQuaException("Invalid number of arguments")

        return cls._get_return_func()(
            kwargs["element_output1"],
            kwargs["element_output2"],
            kwargs["iw1"],
            kwargs["iw2"],
            cls._moving_window_target(kwargs["target"], kwargs["samples_per_chunk"], kwargs["chunks_per_window"]),
        )


class time_tagging:
    """A base class for specifying the time tagging process in the [measure][qm.qua.measure] statement.
    These are the options that can be used inside the measure command as part of the ``time_tagging`` process.
    """

    loc = ""

    @staticmethod
    def analog(
        target: QuaArrayVariable[int],
        max_time: int,
        targetLen: Optional[QuaVariable[int]] = None,
        element_output: str = "",
    ) -> AnalogRawTimeTagging:
        """Performs time tagging. See [Time tagging](../../Guides/features.md#time-tagging).

        Args:
            target (QUA array of type int): The QUA array into which the
                times of the detected pulses are saved (the units depend on the system, see the [documentation](../../Guides/features.md#time-tagging))
            max_time (int): The time in which pulses are detected
                (Must be larger than the pulse duration)
            targetLen (QUA int): A QUA int which will get the number of
                pulses detected
            element_output (str): The output of an element from which to get the pulses.
                Required when there are multiple outputs in the element. Optional otherwise.
        """
        return AnalogRawTimeTagging(element_output, target, targetLen, max_time)

    @staticmethod
    def digital(
        target: QuaArrayVariable[int],
        max_time: int,
        targetLen: Optional[QuaVariable[int]] = None,
        element_output: str = "",
    ) -> DigitalRawTimeTagging:
        """Performs time tagging from the attached OPD.
         See [Time tagging](../../Guides/features.md#time-tagging).

        -- Available with the OPD addon --

        Args:
            target (QUA array of type int): The QUA array into which the
                times of the detected pulses are saved (in ns)
            max_time (int): The time in which pulses are detected
                (Must be larger than the pulse duration)
            targetLen (QUA int): A QUA int which will get the number of
                pulses detected
            element_output (str): The output of an element from which to get the pulses.
                Required when there are multiple outputs in the element. Optional otherwise.
        """
        return DigitalRawTimeTagging(element_output, target, targetLen, max_time)

    @staticmethod
    def high_res(
        target: QuaArrayVariable[int],
        max_time: int,
        targetLen: Optional[QuaVariable[int]] = None,
        element_output: str = "",
    ) -> HighResTimeTagging:
        """Performs high resolution time tagging. See [Time tagging](../../Guides/features.md#time-tagging).

        -- Available from QOP 2.0 --

        Args:
            target (QUA array of type int): The QUA array into which the
                times of the detected pulses are saved (in ps)
            max_time (int): The time in which pulses are detected
                (Must be larger than the pulse duration)
            targetLen (QUA int): A QUA int which will get the number of
                pulses detected
            element_output (str): The output of an element from which to get the pulses.
                Required when there are multiple outputs in the element. Optional otherwise.
        """
        return HighResTimeTagging(element_output, target, targetLen, max_time)


class counting:
    """A base class for specifying the counting process in the [measure][qm.qua.measure] statement.
    These are the options which can be used inside the measure command as part of the ``counting`` process.

    -- Available with the OPD addon --
    """

    loc = ""

    @staticmethod
    def digital(
        target: QuaVariable[int],
        max_time: int,
        element_outputs: str = "",
    ) -> DigitalMeasureProcessCounting:
        """Performs counting from the attached OPD. See [Time tagging](../../Guides/features.md#time-tagging).

        -- Available with the OPD addon --

        Args:
            target (QUA int): A QUA int which will get the number of
                pulses detected
            max_time (int): The time in which pulses are detected
                (Must be larger than the pulse duration)
            element_outputs (str): the outputs of an element from which
                to get ADC results
        """
        return DigitalMeasureProcessCounting(element_outputs, target, max_time)


class demod(_RealAccumulationMethod):
    """
    A class for specifying the demodulation processes in the [measure][qm.qua.measure] statement.
    """

    @classmethod
    def _get_return_func(cls) -> Type[BasicIntegration]:
        return DemodIntegration

    @classmethod
    def full(
        cls, iw: str, target: Union[QuaVariable[float], QuaArrayCell[float]], element_output: str = ""
    ) -> BasicIntegration:
        """
        Perform an ordinary demodulation.
        See [Full demodulation](../../Guides/features.md#full-demodulation).

        Args:
            iw (str): integration weights
            target (QUA variable): variable to which demod result is
                saved
            element_output (str): The output of an element from which to get the ADC data.
                Required for elements with `MWOutput` or with multiple `outputs`.
                Optional otherwise.
        """
        return super().full(iw, target, element_output)

    @classmethod
    def sliced(
        cls,
        iw: str,
        target: QuaArrayVariable[float],
        samples_per_chunk: int,
        element_output: str = "",
    ) -> BasicIntegration:
        """
        Perform a demodulation in which the demodulation process is split into chunks,
        and the value of each chunk is saved in an array cell.
        See [Sliced demodulation](../../Guides/features.md#sliced-demodulation).

        Args:
            iw (str): integration weights
            target (QUA array): variable to which demod result is saved
            samples_per_chunk (int): The number of ADC samples to be
                used for each chunk is this number times 4.
            element_output (str): The output of an element from which to get the ADC data.
                Required for elements with `MWOutput` or with multiple `outputs`.
                Optional otherwise.
        """
        return super().sliced(iw, target, samples_per_chunk, element_output)

    @classmethod
    def accumulated(
        cls,
        iw: str,
        target: QuaArrayVariable[float],
        samples_per_chunk: int,
        element_output: str = "",
    ) -> BasicIntegration:
        """
        Perform a demodulation in which the demodulation process is split into chunks,
        and the accumulated result is saved in each array cell.
        See [Accumulated demodulation](../../Guides/features.md#accumulated-demodulation).

        Args:
            iw (str): integration weights
            target (QUA array): variable to which demod result is saved
            samples_per_chunk (int): The number of ADC samples to be
                used for each chunk is this number times 4.
            element_output (str): The output of an element from which to get the ADC data.
                Required for elements with `MWOutput` or with multiple `outputs`.
                Optional otherwise.
        """
        return super().accumulated(iw, target, samples_per_chunk, element_output)

    @classmethod
    def moving_window(
        cls,
        iw: str,
        target: QuaArrayVariable[float],
        samples_per_chunk: int,
        chunks_per_window: int,
        element_output: str = "",
    ) -> BasicIntegration:
        """
        Perform a demodulation in which the demodulation process is split into chunks,
        and several chunks are accumulated and saved to each array cell, creating a moving window effect.
        See [Moving window demodulation](../../Guides/features.md#moving-window-demodulation).

        Args:
            iw (str): integration weights
            target (QUA array): variable to which demod result is saved
            samples_per_chunk (int): The number of ADC samples to be
                used for each chunk is this number times 4.
            chunks_per_window (int): The number of chunks to use in the
                moving window
            element_output (str): The output of an element from which to get the ADC data.
                Required for elements with `MWOutput` or with multiple `outputs`.
                Optional otherwise.
        """
        return super().moving_window(iw, target, samples_per_chunk, chunks_per_window, element_output)


class dual_demod(_DualAccumulationMethod):
    """
    A class for specifying the dual demod processes in the [measure][qm.qua.measure] statement.
    Dual demod allows demodulating two inputs simultaneously and summing up the result.
    """

    @classmethod
    def _get_return_func(cls) -> Type[DualMeasureProcess]:
        return DualDemodIntegration

    @overload
    @classmethod
    def full(
        cls,
        iw1: str,
        iw2: str,
        target: Union[QuaVariable[float], QuaArrayCell[float]],
    ) -> DualMeasureProcess:
        """
        Perform an ordinary dual demodulation.
        See [Dual demodulation](../../Guides/demod.md#dual-demodulation).

        Args:
            iw1 (str): integration weights to be applied to the I quadrature of a `MWOutput` element
                or `out1` for an element with multiple `outputs`.
            iw2 (str): integration weights to be applied to the Q quadrature of a `MWOutput` element
                or `out2` for an element with multiple `outputs`.
            target (QUA variable): variable to which the demod result is saved
        """
        return super().full(iw1, iw2, target)

    @overload
    @classmethod
    def full(
        cls,
        iw1: str,
        element_output1: str,
        iw2: str,
        element_output2: str,
        target: Union[QuaVariable[float], QuaArrayCell[float]],
    ) -> DualMeasureProcess:
        """
        Perform an ordinary dual demodulation.
        See [Dual demodulation](../../Guides/demod.md#dual-demodulation).

        Args:
            iw1 (str): integration weights to be applied to element_output1
            element_output1 (str): the output of an element from which to get ADC results
            iw2 (str): integration weights to be applied to element_output2
            element_output2 (str): the output of an element from which to get ADC results
            target (QUA variable): variable to which the demod result is saved
        """
        return super().full(iw1, element_output1, iw2, element_output2, target)

    @classmethod
    def full(cls, *args: Any, **kwargs: Any) -> DualMeasureProcess:
        """
        Perform an ordinary dual demodulation.
        See [Dual demodulation](../../Guides/demod.md#dual-demodulation).

        Args:
            iw1 (str): integration weights to be applied to the I quadrature of a `MWOutput` element
                or `out1` for an element with multiple `outputs`.
            iw2 (str): integration weights to be applied to the Q quadrature of a `MWOutput` element
                or `out2` for an element with multiple `outputs`.
            target (QUA variable): variable to which the demod result is saved
        """
        return super().full(*args, **kwargs)


class integration(_RealAccumulationMethod):
    """
    A class for specifying the integration processes in the [measure][qm.qua.measure] statement.
    """

    @classmethod
    def _get_return_func(cls) -> Type[BasicIntegration]:
        return BareIntegration

    @classmethod
    def full(
        cls, iw: str, target: Union[QuaVariable[float], QuaArrayCell[float]], element_output: str = ""
    ) -> BasicIntegration:
        """
        Perform an ordinary integration.
        See [Full integration](../../Guides/features.md#full).

        Args:
            iw (str): integration weights
            target (QUA variable): variable to which demod result is
                saved
            element_output (str): The output of an element from which to get the ADC data.
                Required for elements with `MWOutput` or with multiple `outputs`.
                Optional otherwise.
        """
        return super().full(iw, target, element_output)

    @classmethod
    def sliced(
        cls,
        iw: str,
        target: QuaArrayVariable[float],
        samples_per_chunk: int,
        element_output: str = "",
    ) -> BasicIntegration:
        """
        Perform an integration in which the integration process is split into chunks,
        and the value of each chunk is saved in an array cell.
        See [Sliced integration](../../Guides/features.md#sliced).

        Args:
            iw (str): integration weights
            target (QUA array): variable to which demod result is saved
            samples_per_chunk (int): The number of ADC samples to be
                used for each chunk is this number times 4.
            element_output (str): The output of an element from which to get the ADC data.
                Required for elements with `MWOutput` or with multiple `outputs`.
                Optional otherwise.
        """
        return super().sliced(iw, target, samples_per_chunk, element_output)

    @classmethod
    def accumulated(
        cls,
        iw: str,
        target: QuaArrayVariable[float],
        samples_per_chunk: int,
        element_output: str = "",
    ) -> BasicIntegration:
        """
        Perform an integration in which the integration process is split into chunks,
        and the accumulated result is saved in each array cell.
        See [Accumulated integration](../../Guides/features.md#accumulated).

        Args:
            iw (str): integration weights
            target (QUA array): variable to which demod result is saved
            samples_per_chunk (int): The number of ADC samples to be
                used for each chunk is this number times 4.
            element_output (str): The output of an element from which to get the ADC data.
                Required for elements with `MWOutput` or with multiple `outputs`.
                Optional otherwise.
        """
        return super().accumulated(iw, target, samples_per_chunk, element_output)

    @classmethod
    def moving_window(
        cls,
        iw: str,
        target: QuaArrayVariable[float],
        samples_per_chunk: int,
        chunks_per_window: int,
        element_output: str = "",
    ) -> BasicIntegration:
        """
        Perform an integration in which the integration process is split into chunks,
        and several chunks are accumulated and saved to each array cell, creating a moving window effect.
        See [Moving window integration](../../Guides/features.md#moving-window).

        Args:
            iw (str): integration weights
            target (QUA array): variable to which demod result is saved
            samples_per_chunk (int): The number of ADC samples to be
                used for each chunk is this number times 4.
            chunks_per_window (int): The number of chunks to use in the
                moving window
            element_output (str): The output of an element from which to get the ADC data.
                Required for elements with `MWOutput` or with multiple `outputs`.
                Optional otherwise.
        """
        return super().moving_window(iw, target, samples_per_chunk, chunks_per_window, element_output)
