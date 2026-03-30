from abc import ABC, abstractmethod

from qm.type_hinting import NumberT
from qm.grpc.qm.pb import inc_qua_pb2
from qm.qua._expressions import QuaVariable
from qm.qua._dsl.stream_processing.stream_processing import ResultStreamSource


class DirectStreamSourceInterface(QuaVariable[NumberT], ABC):
    @abstractmethod
    def get_stream(self) -> ResultStreamSource:
        """Get or create the stream associated with DirectStreamSource for current scope."""
        pass

    @abstractmethod
    def stream_processing(self, current_processed_streams: set[str]) -> None:
        """Process and save the stream associated with DirectStreamSource.

        Mutates current_processed_streams in place, adding the names of streams processed.
        """
        pass

    @property
    @abstractmethod
    def stream_name(self) -> str:
        """Get the name of the stream associated with DirectStreamSource."""
        pass

    @abstractmethod
    def save(self) -> None:
        """Generate the save statement for the stream associated with DirectStreamSource."""
        pass

    @abstractmethod
    def get_save_statement(self) -> inc_qua_pb2.QuaProgram.AnyStatement:
        """Get the save statement for the stream associated with DirectStreamSource."""
        pass
