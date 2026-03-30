from abc import ABC, abstractmethod
from typing import Generic, Optional, Sequence

from qm.exceptions import QmQuaException
from qm.qua._scope_management._core_scopes import _LoopScope
from qm.qua._scope_management.scopes_manager import scopes_manager
from qm.qua.extensions.qua_iterators.qua_iterators_types import V, MetaDataType


class IterableBase(ABC, Generic[V]):
    def __init__(self, name: str, metadata: Optional[MetaDataType] = None):
        self._name = name
        self._metadata = metadata if metadata is not None else {}
        self._averaged_streams: frozenset[str] = frozenset()

    @property
    def name(self) -> str:
        return self._name

    @property
    def metadata(self) -> MetaDataType:
        return self._metadata

    # Return type intentionally omitted: subclasses declare specific return types
    # (QuaIteratorType[V], NativeIteratorType[V], MultiIteratorType). Annotating the
    # base with the IteratorType union (which collapses to Iterator[Any]) prevents
    # IDEs from resolving the narrower subclass types.
    @abstractmethod
    def __iter__(self):  # type: ignore[no-untyped-def]
        pass

    def __len__(self) -> int:
        return len(self.values)

    @property
    def buffer_size(self) -> int:
        return len(self)

    @property
    @abstractmethod
    def values(self) -> Sequence[V]:
        """
        get iterator values
        """
        pass

    def _get_current_scope(self) -> _LoopScope:
        """
        get current scope
        """
        curr_scope = scopes_manager.current_scope
        if not isinstance(curr_scope, _LoopScope):
            raise QmQuaException("Iterables can only be a loop scope.")
        return curr_scope

    def _add_to_current_scope(self) -> None:
        curr_scope = self._get_current_scope()
        curr_scope.set_scope_metadata(self.name, len(self))

    def _set_averaged_streams(self) -> None:
        """
        set averaged streams from scope
        """
        curr_scope = self._get_current_scope()
        self._averaged_streams = curr_scope.averaged_streams()

    def is_stream_averaged(self, stream_name: str) -> bool:
        """
        Check if stream is averaged on this iterable
        """
        return stream_name in self._averaged_streams

    @property
    def is_qua_iterable(self) -> bool:
        return False
