import abc
from typing import Optional
from collections.abc import Sequence

from qm.type_hinting import Number
from qm.config import ElementOutput
from qm.grpc.qm.pb import inc_qua_pb2
from qm.qua._expressions import QuaVariable, QuaArrayVariable
from qm.qua._dsl.measure.analog_measure_process import MeasureProcessAbstract, _add_target_len
from qm.qua._dsl.stream_processing.direct_stream_processing_interface import DirectStreamSourceInterface


class DigitalMeasureProcess(MeasureProcessAbstract, abc.ABC):
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

    @property
    def uses_string_api(self) -> bool:
        # The element output is always a plain str (resolved from the element's config),
        # so it no longer signals whether the "string API" was used.
        return False


class Counting(DigitalMeasureProcess):
    def __init__(
        self,
        element_outputs: str | Sequence[str],
        target: QuaVariable[int],
        max_time: Number,
    ):
        super().__init__(max_time)
        self.target_int = target
        self._element_outputs = (
            [element_outputs] if isinstance(element_outputs, (str, ElementOutput)) else element_outputs
        )

    @property
    def uses_string_api(self) -> bool:
        # The element outputs are always plain strs (resolved from the element's config),
        # so they no longer signal whether the "string API" was used.
        return False

    @property
    def _digital_unwrapped(self) -> inc_qua_pb2.QuaProgram.DigitalMeasureProcess:
        unwrapped_target = self.target_int.unwrapped

        counting = inc_qua_pb2.QuaProgram.DigitalMeasureProcess.Counting(
            maxTime=self.max_time,
            target=unwrapped_target.variable,
        )

        for output in self._element_outputs:
            counting.elementOutputs.append(output)

        return inc_qua_pb2.QuaProgram.DigitalMeasureProcess(loc=self.loc, counting=counting)

    def save_stream_if_needed(self) -> None:
        if isinstance(self.target_int, DirectStreamSourceInterface):
            self.target_int.save()
