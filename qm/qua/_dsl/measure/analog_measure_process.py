import abc
from typing import Union, TypeVar, Optional

from qm._loc import _get_loc
from qm.type_hinting import Number
from qm.grpc.qm.pb import inc_qua_pb2
from qm.exceptions import QmQuaException
from qm.utils.protobuf_utils import which_one_of
from qm.qua._expressions import QuaVariable, QuaArrayCell, QuaArrayVariable
from qm.qua._dsl.stream_processing.direct_stream_processing_interface import DirectStreamSourceInterface


class AnalogTimeDivision(metaclass=abc.ABCMeta):
    def __init__(self, loc: str, samples_per_chunk: int):
        self.loc = loc
        self.samples_per_chunk = samples_per_chunk

    @property
    @abc.abstractmethod
    def unwrapped(self) -> inc_qua_pb2.QuaProgram.AnalogProcessTarget.TimeDivision:
        pass


class SlicedAnalogTimeDivision(AnalogTimeDivision):
    @property
    def unwrapped(self) -> inc_qua_pb2.QuaProgram.AnalogProcessTarget.TimeDivision:
        return inc_qua_pb2.QuaProgram.AnalogProcessTarget.TimeDivision(
            sliced=inc_qua_pb2.QuaProgram.AnalogTimeDivision.Sliced(samplesPerChunk=self.samples_per_chunk)
        )


class AccumulatedAnalogTimeDivision(AnalogTimeDivision):
    @property
    def unwrapped(self) -> inc_qua_pb2.QuaProgram.AnalogProcessTarget.TimeDivision:
        return inc_qua_pb2.QuaProgram.AnalogProcessTarget.TimeDivision(
            accumulated=inc_qua_pb2.QuaProgram.AnalogTimeDivision.Accumulated(samplesPerChunk=self.samples_per_chunk)
        )


class MovingWindowAnalogTimeDivision(AnalogTimeDivision):
    def __init__(self, loc: str, samples_per_chunk: int, chunks_per_window: int):
        super().__init__(loc, samples_per_chunk)
        self.chunks_per_window = chunks_per_window

    @property
    def unwrapped(self) -> inc_qua_pb2.QuaProgram.AnalogProcessTarget.TimeDivision:
        return inc_qua_pb2.QuaProgram.AnalogProcessTarget.TimeDivision(
            movingWindow=inc_qua_pb2.QuaProgram.AnalogTimeDivision.MovingWindow(
                samplesPerChunk=self.samples_per_chunk,
                chunksPerWindow=self.chunks_per_window,
            )
        )


class AnalogProcessTarget(metaclass=abc.ABCMeta):
    def __init__(self, loc: str):
        self.loc = loc

    @property
    @abc.abstractmethod
    def unwrapped(self) -> inc_qua_pb2.QuaProgram.AnalogProcessTarget:
        pass

    @abc.abstractmethod
    def save_stream_if_needed(self) -> None:
        pass


class ScalarProcessTarget(AnalogProcessTarget):
    def __init__(self, loc: str, target: Union[QuaVariable[float], QuaArrayCell[float]]):
        super().__init__(loc)
        self.target = target

    @property
    def unwrapped(self) -> inc_qua_pb2.QuaProgram.AnalogProcessTarget:
        target_exp = self.target.unwrapped
        if not isinstance(target_exp, inc_qua_pb2.QuaProgram.AnyScalarExpression):
            raise QmQuaException(f"Unknown type - {type(target_exp)}")

        target_type, found = which_one_of(target_exp, "expression_oneof")
        if isinstance(found, inc_qua_pb2.QuaProgram.VarRefExpression):
            target = inc_qua_pb2.QuaProgram.AnalogProcessTarget.ScalarProcessTarget(variable=found)
        elif isinstance(found, inc_qua_pb2.QuaProgram.ArrayCellRefExpression):
            target = inc_qua_pb2.QuaProgram.AnalogProcessTarget.ScalarProcessTarget(arrayCell=found)
        else:
            raise QmQuaException(f"Unknown target type - {target_type}")
        return inc_qua_pb2.QuaProgram.AnalogProcessTarget(scalarProcess=target)

    def save_stream_if_needed(self) -> None:
        if isinstance(self.target, DirectStreamSourceInterface):
            self.target.save()


class VectorProcessTarget(AnalogProcessTarget):
    def __init__(self, loc: str, target: QuaArrayVariable[float], time_division: AnalogTimeDivision):
        super().__init__(loc)
        self.time_division = time_division
        self.target = target

    @property
    def unwrapped(self) -> inc_qua_pb2.QuaProgram.AnalogProcessTarget:
        target_exp = self.target.unwrapped
        target = inc_qua_pb2.QuaProgram.AnalogProcessTarget.VectorProcessTarget(
            array=target_exp,
            timeDivision=self.time_division.unwrapped,
        )
        return inc_qua_pb2.QuaProgram.AnalogProcessTarget(vectorProcess=target)

    def save_stream_if_needed(self) -> None:
        if isinstance(self.target, DirectStreamSourceInterface):
            self.target.save()


class MeasureProcessAbstract(metaclass=abc.ABCMeta):
    def __init__(self) -> None:
        self.loc = _get_loc()

    @property
    @abc.abstractmethod
    def unwrapped(self) -> inc_qua_pb2.QuaProgram.MeasureProcess:
        pass

    @abc.abstractmethod
    def save_stream_if_needed(self) -> None:
        pass


class AnalogMeasureProcess(MeasureProcessAbstract, metaclass=abc.ABCMeta):
    def __init__(self, target: AnalogProcessTarget):
        super().__init__()
        self.target = target

    @property
    def unwrapped(self) -> inc_qua_pb2.QuaProgram.MeasureProcess:
        return inc_qua_pb2.QuaProgram.MeasureProcess(analog=self._analog_unwrapped)

    @property
    @abc.abstractmethod
    def _analog_unwrapped(self) -> inc_qua_pb2.QuaProgram.AnalogMeasureProcess:
        pass

    def save_stream_if_needed(self) -> None:
        self.target.save_stream_if_needed()


class BasicIntegration(AnalogMeasureProcess):
    def __init__(self, element_output: str, iw: str, target: AnalogProcessTarget):
        super().__init__(target)
        self.element_output = element_output
        self.iw = iw

    @property
    @abc.abstractmethod
    def _analog_unwrapped(self) -> inc_qua_pb2.QuaProgram.AnalogMeasureProcess:
        pass


class BareIntegration(BasicIntegration):
    @property
    def _analog_unwrapped(self) -> inc_qua_pb2.QuaProgram.AnalogMeasureProcess:
        return inc_qua_pb2.QuaProgram.AnalogMeasureProcess(
            loc=self.loc,
            bareIntegration=inc_qua_pb2.QuaProgram.AnalogMeasureProcess.BareIntegration(
                integration=inc_qua_pb2.QuaProgram.IntegrationWeightReference(name=self.iw),
                elementOutput=self.element_output,
                target=self.target.unwrapped,
            ),
        )


class DemodIntegration(BasicIntegration):
    @property
    def _analog_unwrapped(self) -> inc_qua_pb2.QuaProgram.AnalogMeasureProcess:
        return inc_qua_pb2.QuaProgram.AnalogMeasureProcess(
            loc=self.loc,
            demodIntegration=inc_qua_pb2.QuaProgram.AnalogMeasureProcess.DemodIntegration(
                integration=inc_qua_pb2.QuaProgram.IntegrationWeightReference(name=self.iw),
                elementOutput=self.element_output,
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
    def _analog_unwrapped(self) -> inc_qua_pb2.QuaProgram.AnalogMeasureProcess:
        return inc_qua_pb2.QuaProgram.AnalogMeasureProcess(
            loc=self.loc,
            dualDemodIntegration=inc_qua_pb2.QuaProgram.AnalogMeasureProcess.DualDemodIntegration(
                integration1=inc_qua_pb2.QuaProgram.IntegrationWeightReference(name=self.iw1),
                integration2=inc_qua_pb2.QuaProgram.IntegrationWeightReference(name=self.iw2),
                elementOutput1=self.element_output1,
                elementOutput2=self.element_output2,
                target=self.target.unwrapped,
            ),
        )


T = TypeVar(
    "T",
    bound=Union[
        inc_qua_pb2.QuaProgram.AnalogMeasureProcess.RawTimeTagging,
        inc_qua_pb2.QuaProgram.AnalogMeasureProcess.HighResTimeTagging,
        inc_qua_pb2.QuaProgram.DigitalMeasureProcess.RawTimeTagging,
    ],
)


def _add_target_len(time_tagging: T, target_len: Optional[QuaVariable[int]]) -> T:
    if target_len is not None:
        time_tagging.targetLen.CopyFrom(target_len.unwrapped.variable)
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
    def unwrapped_target(self) -> inc_qua_pb2.QuaProgram.ArrayVarRefExpression:
        a = self.time_tagging_target.unwrapped
        assert isinstance(a, inc_qua_pb2.QuaProgram.ArrayVarRefExpression)
        return a

    @property
    def unwrapped(self) -> inc_qua_pb2.QuaProgram.MeasureProcess:
        return inc_qua_pb2.QuaProgram.MeasureProcess(analog=self._analog_unwrapped)

    @property
    @abc.abstractmethod
    def _analog_unwrapped(self) -> inc_qua_pb2.QuaProgram.AnalogMeasureProcess:
        pass

    def save_stream_if_needed(self) -> None:
        pass


class RawTimeTagging(TimeTaggingMeasurementProcess):
    @property
    def _analog_unwrapped(self) -> inc_qua_pb2.QuaProgram.AnalogMeasureProcess:
        time_tagging = inc_qua_pb2.QuaProgram.AnalogMeasureProcess.RawTimeTagging(
            maxTime=int(self.max_time),
            elementOutput=self.element_output,
            target=self.unwrapped_target,
        )
        time_tagging = _add_target_len(time_tagging, self.targetLen)
        return inc_qua_pb2.QuaProgram.AnalogMeasureProcess(loc=self.loc, rawTimeTagging=time_tagging)


class HighResTimeTagging(TimeTaggingMeasurementProcess):
    @property
    def _analog_unwrapped(self) -> inc_qua_pb2.QuaProgram.AnalogMeasureProcess:
        time_tagging = inc_qua_pb2.QuaProgram.AnalogMeasureProcess.HighResTimeTagging(
            maxTime=int(self.max_time),
            elementOutput=self.element_output,
            target=self.unwrapped_target,
        )
        time_tagging = _add_target_len(time_tagging, self.targetLen)
        return inc_qua_pb2.QuaProgram.AnalogMeasureProcess(loc=self.loc, highResTimeTagging=time_tagging)
