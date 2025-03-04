import abc
from typing import TYPE_CHECKING, List, Tuple

from betterproto.lib.google.protobuf import Value, ListValue

from qm.grpc.qua import QuaResultAnalysis

if TYPE_CHECKING:
    from qm.qua._dsl import _ResultStream


class _OutputStream(metaclass=abc.ABCMeta):
    """Even though it looks like a stream, it does not support operations (like __add__) and hence, a different object"""

    def __init__(self, input_stream: "_ResultStream", tag: str):
        self._input_stream = input_stream
        self.tag = tag

    def to_proto(self) -> "ListValue":
        values = [Value(string_value=s) for s in self._operator_array]
        values.append(self._input_stream.to_proto())
        return ListValue(values=values)

    @property
    @abc.abstractmethod
    def _operator_array(self) -> Tuple[str, ...]:
        pass


class _SaveOutputStream(_OutputStream):
    @property
    def _operator_array(self) -> Tuple[str, ...]:
        return "save", self.tag


class _SaveAllOutputStream(_OutputStream):
    @property
    def _operator_array(self) -> Tuple[str, ...]:
        return "saveAll", self.tag


class _AutoSaveAllOutputStream(_OutputStream):
    @property
    def _operator_array(self) -> Tuple[str, ...]:
        return "saveAll", self.tag, "auto"


class _ResultAnalysis:
    def __init__(self, result_analysis: QuaResultAnalysis):
        self._result_analysis = result_analysis
        self._saves: List[_OutputStream] = []

    def _add_output_stream(self, output_stream: _OutputStream) -> None:
        for save in self._saves:
            if save.tag == output_stream.tag:
                raise Exception("can not save two streams with the same tag")
        self._saves.append(output_stream)

    def save(self, tag: str, expression: "_ResultStream") -> None:
        self._add_output_stream(_SaveOutputStream(expression, tag))

    def save_all(self, tag: str, expression: "_ResultStream") -> None:
        self._add_output_stream(_SaveAllOutputStream(expression, tag))

    def auto_save_all(self, tag: str, expression: "_ResultStream") -> None:
        self._add_output_stream(_AutoSaveAllOutputStream(expression, tag))

    def _add_pipeline(self, output: _OutputStream) -> None:
        proto_output = output.to_proto()
        self._result_analysis.model.append(proto_output)

    def generate_proto(self) -> None:
        for save in self._saves:
            self._add_pipeline(save)
