import abc
from typing import Union, Optional, Sequence

from qm.type_hinting import Number
from qm.qua._expressions import QuaVariable, QuaArrayVariable
from qm.qua._dsl.measure.analog_measure_process import MeasureProcessAbstract, _add_target_len
from qm.grpc.qua import (
    QuaProgramMeasureProcess,
    QuaProgramDigitalMeasureProcess,
    QuaProgramDigitalMeasureProcessCounting,
    QuaProgramDigitalMeasureProcessRawTimeTagging,
)


class DigitalMeasureProcess(MeasureProcessAbstract, metaclass=abc.ABCMeta):
    def __init__(self, max_time: Number):
        super().__init__()
        self._max_time = max_time

    @property
    def max_time(self) -> int:
        return int(self._max_time)

    @property
    def unwrapped(self) -> QuaProgramMeasureProcess:
        return QuaProgramMeasureProcess(digital=self._digital_unwrapped)

    @property
    @abc.abstractmethod
    def _digital_unwrapped(self) -> QuaProgramDigitalMeasureProcess:
        pass


class RawTimeTagging(DigitalMeasureProcess):
    def __init__(
        self,
        element_output: str,
        target: QuaArrayVariable[int],
        targetLen: Optional[QuaVariable[int]],
        max_time: Number,
    ):
        super().__init__(max_time)
        self.target_arr = target
        self.element_output = element_output
        self.targetLen = targetLen

    @property
    def _digital_unwrapped(self) -> QuaProgramDigitalMeasureProcess:
        unwrapped_target = self.target_arr.unwrapped

        time_tagging = QuaProgramDigitalMeasureProcessRawTimeTagging(
            max_time=self.max_time,
            element_output=self.element_output,
            target=unwrapped_target,
        )
        time_tagging = _add_target_len(time_tagging, self.targetLen)

        return QuaProgramDigitalMeasureProcess(loc=self.loc, raw_time_tagging=time_tagging)


class Counting(DigitalMeasureProcess):
    def __init__(self, element_outputs: Union[str, Sequence[str]], target: QuaVariable[int], max_time: Number):
        super().__init__(max_time)
        self.target_int = target
        self.element_outputs = element_outputs

    @property
    def _digital_unwrapped(self) -> QuaProgramDigitalMeasureProcess:
        unwrapped_target = self.target_int.unwrapped

        counting = QuaProgramDigitalMeasureProcessCounting(
            max_time=self.max_time,
            target=unwrapped_target.variable,
        )
        outputs = self.element_outputs
        if isinstance(outputs, str):
            counting.element_outputs.append(outputs)
        else:
            counting.element_outputs.extend(outputs)

        return QuaProgramDigitalMeasureProcess(loc=self.loc, counting=counting)
