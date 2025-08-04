import abc
from typing import Union, TypeVar, Optional

import betterproto

from qm._loc import _get_loc
from qm.type_hinting import Number
from qm.exceptions import QmQuaException
from qm.qua._expressions import QuaVariable, QuaArrayCell, QuaArrayVariable
from qm.grpc.qua import (
    QuaProgramMeasureProcess,
    QuaProgramVarRefExpression,
    QuaProgramAnalogProcessTarget,
    QuaProgramAnyScalarExpression,
    QuaProgramAnalogMeasureProcess,
    QuaProgramArrayVarRefExpression,
    QuaProgramArrayCellRefExpression,
    QuaProgramAnalogTimeDivisionSliced,
    QuaProgramIntegrationWeightReference,
    QuaProgramAnalogTimeDivisionAccumulated,
    QuaProgramAnalogTimeDivisionMovingWindow,
    QuaProgramAnalogProcessTargetTimeDivision,
    QuaProgramAnalogMeasureProcessRawTimeTagging,
    QuaProgramAnalogMeasureProcessBareIntegration,
    QuaProgramDigitalMeasureProcessRawTimeTagging,
    QuaProgramAnalogMeasureProcessDemodIntegration,
    QuaProgramAnalogMeasureProcessHighResTimeTagging,
    QuaProgramAnalogProcessTargetScalarProcessTarget,
    QuaProgramAnalogProcessTargetVectorProcessTarget,
    QuaProgramAnalogMeasureProcessDualDemodIntegration,
)


class AnalogTimeDivision(metaclass=abc.ABCMeta):
    def __init__(self, loc: str, samples_per_chunk: int):
        self.loc = loc
        self.samples_per_chunk = samples_per_chunk

    @property
    @abc.abstractmethod
    def unwrapped(self) -> QuaProgramAnalogProcessTargetTimeDivision:
        pass


class SlicedAnalogTimeDivision(AnalogTimeDivision):
    @property
    def unwrapped(self) -> QuaProgramAnalogProcessTargetTimeDivision:
        return QuaProgramAnalogProcessTargetTimeDivision(
            sliced=QuaProgramAnalogTimeDivisionSliced(samples_per_chunk=self.samples_per_chunk)
        )


class AccumulatedAnalogTimeDivision(AnalogTimeDivision):
    @property
    def unwrapped(self) -> QuaProgramAnalogProcessTargetTimeDivision:
        return QuaProgramAnalogProcessTargetTimeDivision(
            accumulated=QuaProgramAnalogTimeDivisionAccumulated(samples_per_chunk=self.samples_per_chunk)
        )


class MovingWindowAnalogTimeDivision(AnalogTimeDivision):
    def __init__(self, loc: str, samples_per_chunk: int, chunks_per_window: int):
        super().__init__(loc, samples_per_chunk)
        self.chunks_per_window = chunks_per_window

    @property
    def unwrapped(self) -> QuaProgramAnalogProcessTargetTimeDivision:
        return QuaProgramAnalogProcessTargetTimeDivision(
            moving_window=QuaProgramAnalogTimeDivisionMovingWindow(
                samples_per_chunk=self.samples_per_chunk,
                chunks_per_window=self.chunks_per_window,
            )
        )


class AnalogProcessTarget(metaclass=abc.ABCMeta):
    def __init__(self, loc: str):
        self.loc = loc

    @property
    @abc.abstractmethod
    def unwrapped(self) -> QuaProgramAnalogProcessTarget:
        pass


class ScalarProcessTarget(AnalogProcessTarget):
    def __init__(self, loc: str, target: Union[QuaVariable[float], QuaArrayCell[float]]):
        super().__init__(loc)
        self.target = target

    @property
    def unwrapped(self) -> QuaProgramAnalogProcessTarget:
        target_exp = self.target.unwrapped
        if not isinstance(target_exp, QuaProgramAnyScalarExpression):
            raise QmQuaException(f"Unknown type - {type(target_exp)}")

        target_type, found = betterproto.which_one_of(target_exp, "expression_oneof")
        if isinstance(found, QuaProgramVarRefExpression):
            target = QuaProgramAnalogProcessTargetScalarProcessTarget(variable=found)
        elif isinstance(found, QuaProgramArrayCellRefExpression):
            target = QuaProgramAnalogProcessTargetScalarProcessTarget(array_cell=found)
        else:
            raise QmQuaException(f"Unknown target type - {target_type}")
        return QuaProgramAnalogProcessTarget(scalar_process=target)


class VectorProcessTarget(AnalogProcessTarget):
    def __init__(self, loc: str, target: QuaArrayVariable[float], time_division: AnalogTimeDivision):
        super().__init__(loc)
        self.time_division = time_division
        self.target = target

    @property
    def unwrapped(self) -> QuaProgramAnalogProcessTarget:
        target_exp = self.target.unwrapped
        target = QuaProgramAnalogProcessTargetVectorProcessTarget(
            array=target_exp,
            time_division=QuaProgramAnalogProcessTargetTimeDivision().from_dict(self.time_division.unwrapped.to_dict()),
        )
        return QuaProgramAnalogProcessTarget(vector_process=target)


class MeasureProcessAbstract(metaclass=abc.ABCMeta):
    def __init__(self) -> None:
        self.loc = _get_loc()

    @property
    @abc.abstractmethod
    def unwrapped(self) -> QuaProgramMeasureProcess:
        pass


class AnalogMeasureProcess(MeasureProcessAbstract, metaclass=abc.ABCMeta):
    def __init__(self, target: AnalogProcessTarget):
        super().__init__()
        self.target = target

    @property
    def unwrapped(self) -> QuaProgramMeasureProcess:
        return QuaProgramMeasureProcess(analog=self._analog_unwrapped)

    @property
    @abc.abstractmethod
    def _analog_unwrapped(self) -> QuaProgramAnalogMeasureProcess:
        pass


class BasicIntegration(AnalogMeasureProcess):
    def __init__(self, element_output: str, iw: str, target: AnalogProcessTarget):
        super().__init__(target)
        self.element_output = element_output
        self.iw = iw

    @property
    @abc.abstractmethod
    def _analog_unwrapped(self) -> QuaProgramAnalogMeasureProcess:
        pass


class BareIntegration(BasicIntegration):
    @property
    def _analog_unwrapped(self) -> QuaProgramAnalogMeasureProcess:
        return QuaProgramAnalogMeasureProcess(
            loc=self.loc,
            bare_integration=QuaProgramAnalogMeasureProcessBareIntegration(
                integration=QuaProgramIntegrationWeightReference(name=self.iw),
                element_output=self.element_output,
                target=self.target.unwrapped,
            ),
        )


class DemodIntegration(BasicIntegration):
    @property
    def _analog_unwrapped(self) -> QuaProgramAnalogMeasureProcess:
        return QuaProgramAnalogMeasureProcess(
            loc=self.loc,
            demod_integration=QuaProgramAnalogMeasureProcessDemodIntegration(
                integration=QuaProgramIntegrationWeightReference(name=self.iw),
                element_output=self.element_output,
                target=self.target.unwrapped,
            ),
        )


class DualMeasureProcess(AnalogMeasureProcess, metaclass=abc.ABCMeta):
    def __init__(
        self,
        element_output1: str,
        element_output2: str,
        iw1: str,
        iw2: str,
        target: AnalogProcessTarget,
    ):
        super().__init__(target)
        self.element_output1 = element_output1
        self.element_output2 = element_output2
        self.iw1 = iw1
        self.iw2 = iw2


class DualDemodIntegration(DualMeasureProcess):
    @property
    def _analog_unwrapped(self) -> QuaProgramAnalogMeasureProcess:
        return QuaProgramAnalogMeasureProcess(
            loc=self.loc,
            dual_demod_integration=QuaProgramAnalogMeasureProcessDualDemodIntegration(
                integration1=QuaProgramIntegrationWeightReference(name=self.iw1),
                integration2=QuaProgramIntegrationWeightReference(name=self.iw2),
                element_output1=self.element_output1,
                element_output2=self.element_output2,
                target=self.target.unwrapped,
            ),
        )


T = TypeVar(
    "T",
    bound=Union[
        QuaProgramAnalogMeasureProcessRawTimeTagging,
        QuaProgramAnalogMeasureProcessHighResTimeTagging,
        QuaProgramDigitalMeasureProcessRawTimeTagging,
    ],
)


def _add_target_len(time_tagging: T, target_len: Optional[QuaVariable[int]]) -> T:
    if target_len is not None:
        time_tagging.target_len = target_len.unwrapped.variable
    return time_tagging


class TimeTaggingMeasurementProcess(MeasureProcessAbstract, metaclass=abc.ABCMeta):
    def __init__(
        self,
        element_output: str,
        target: QuaArrayVariable[int],
        targetLen: Optional[QuaVariable[int]],
        max_time: Number,
    ):
        super().__init__()
        self.time_tagging_target = target
        self.element_output = element_output
        self.targetLen = targetLen
        self.max_time = max_time

    @property
    def unwrapped_target(self) -> QuaProgramArrayVarRefExpression:
        a = self.time_tagging_target.unwrapped
        assert isinstance(a, QuaProgramArrayVarRefExpression)
        return a

    @property
    def unwrapped(self) -> QuaProgramMeasureProcess:
        return QuaProgramMeasureProcess(analog=self._analog_unwrapped)

    @property
    @abc.abstractmethod
    def _analog_unwrapped(self) -> QuaProgramAnalogMeasureProcess:
        pass


class RawTimeTagging(TimeTaggingMeasurementProcess):
    @property
    def _analog_unwrapped(self) -> QuaProgramAnalogMeasureProcess:
        time_tagging = QuaProgramAnalogMeasureProcessRawTimeTagging(
            max_time=int(self.max_time),
            element_output=self.element_output,
            target=self.unwrapped_target,
        )
        time_tagging = _add_target_len(time_tagging, self.targetLen)
        return QuaProgramAnalogMeasureProcess(loc=self.loc, raw_time_tagging=time_tagging)


class HighResTimeTagging(TimeTaggingMeasurementProcess):
    @property
    def _analog_unwrapped(self) -> QuaProgramAnalogMeasureProcess:
        time_tagging = QuaProgramAnalogMeasureProcessHighResTimeTagging(
            max_time=int(self.max_time),
            element_output=self.element_output,
            target=self.unwrapped_target,
        )
        time_tagging = _add_target_len(time_tagging, self.targetLen)
        return QuaProgramAnalogMeasureProcess(loc=self.loc, high_res_time_tagging=time_tagging)
