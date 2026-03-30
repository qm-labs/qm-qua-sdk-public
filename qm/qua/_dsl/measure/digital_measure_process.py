import abc
from typing import Union, Optional, Sequence

from qm.type_hinting import Number
from qm.grpc.qm.pb import inc_qua_pb2
from qm.qua._expressions import QuaVariable, QuaArrayVariable
from qm.qua._dsl.measure.analog_measure_process import MeasureProcessAbstract, _add_target_len
from qm.qua._dsl.stream_processing.direct_stream_processing_interface import DirectStreamSourceInterface


class DigitalMeasureProcess(MeasureProcessAbstract, metaclass=abc.ABCMeta):
    def __init__(self, max_time: Number):
        super().__init__()
        self._max_time = max_time

    @property
    def max_time(self) -> int:
        return int(self._max_time)

    @property
    def unwrapped(self) -> inc_qua_pb2.QuaProgram.MeasureProcess:
        return inc_qua_pb2.QuaProgram.MeasureProcess(digital=self._digital_unwrapped)

    @property
    @abc.abstractmethod
    def _digital_unwrapped(self) -> inc_qua_pb2.QuaProgram.DigitalMeasureProcess:
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
    def _digital_unwrapped(self) -> inc_qua_pb2.QuaProgram.DigitalMeasureProcess:
        unwrapped_target = self.target_arr.unwrapped

        time_tagging = inc_qua_pb2.QuaProgram.DigitalMeasureProcess.RawTimeTagging(
            maxTime=self.max_time,
            elementOutput=self.element_output,
            target=unwrapped_target,
        )
        time_tagging = _add_target_len(time_tagging, self.targetLen)

        return inc_qua_pb2.QuaProgram.DigitalMeasureProcess(loc=self.loc, rawTimeTagging=time_tagging)

    def save_stream_if_needed(self) -> None:
        pass


class Counting(DigitalMeasureProcess):
    def __init__(self, element_outputs: Union[str, Sequence[str]], target: QuaVariable[int], max_time: Number):
        super().__init__(max_time)
        self.target_int = target
        self.element_outputs = element_outputs

    @property
    def _digital_unwrapped(self) -> inc_qua_pb2.QuaProgram.DigitalMeasureProcess:
        unwrapped_target = self.target_int.unwrapped

        counting = inc_qua_pb2.QuaProgram.DigitalMeasureProcess.Counting(
            maxTime=self.max_time,
            target=unwrapped_target.variable,
        )
        outputs = self.element_outputs
        if isinstance(outputs, str):
            counting.elementOutputs.append(outputs)
        else:
            counting.elementOutputs.extend(outputs)

        return inc_qua_pb2.QuaProgram.DigitalMeasureProcess(loc=self.loc, counting=counting)

    def save_stream_if_needed(self) -> None:
        if isinstance(self.target_int, DirectStreamSourceInterface):
            self.target_int.save()
