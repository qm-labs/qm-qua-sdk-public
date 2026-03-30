import abc
from collections import defaultdict
from typing import Dict, Tuple, Callable, Hashable

from qm.grpc.octave.v1 import api_pb2
from qm.utils.general_utils import Singleton


class BatchSingleton(metaclass=Singleton):
    def __init__(self) -> None:
        self._batch_mode = False
        self._start_batch_callbacks: Dict[Hashable, Callable[[], None]] = {}
        self._end_batch_callbacks: Dict[Hashable, Callable[[], None]] = {}

        self._cached_updates: Dict[int, Dict[Tuple[int, str], api_pb2.SingleUpdate]] = defaultdict(dict)
        self._cached_modules: Dict[int, Dict[Tuple[int, str], api_pb2.SingleUpdate]] = defaultdict(dict)

    @property
    def is_batch_mode(self) -> bool:
        return self._batch_mode

    def start_batch_mode(self) -> None:
        if not self._batch_mode:
            for callback in self._start_batch_callbacks.values():
                callback()
        self._batch_mode = True

    def end_batch_mode(self) -> None:
        if self._batch_mode:
            for callback in self._end_batch_callbacks.values():
                callback()
            self._cached_updates = defaultdict(dict)
            self._cached_modules = defaultdict(dict)
        self._batch_mode = False

    def set_cached_modules(self, obj: Hashable, modules: Dict[Tuple[int, str], api_pb2.SingleUpdate]) -> None:
        self._cached_modules[hash(obj)] = modules

    def set_cached_updates(self, obj: Hashable, modules: Dict[Tuple[int, str], api_pb2.SingleUpdate]) -> None:
        self._cached_updates[hash(obj)] = modules

    def get_cached_updates(self, obj: Hashable) -> Dict[Tuple[int, str], api_pb2.SingleUpdate]:
        return self._cached_updates[hash(obj)]

    def get_cached_modules(self, obj: Hashable) -> Dict[Tuple[int, str], api_pb2.SingleUpdate]:
        return self._cached_modules[hash(obj)]

    def register_start_batch_callback(self, obj: Hashable, callback: Callable[[], None]) -> None:
        self._start_batch_callbacks[hash(obj)] = callback

    def register_end_batch_callback(self, obj: Hashable, callback: Callable[[], None]) -> None:
        self._end_batch_callbacks[hash(obj)] = callback

    def unregister_start_batch_callback(self, obj: Hashable) -> None:
        self._start_batch_callbacks.pop(hash(obj))

    def unregister_end_batch_callback(self, obj: Hashable) -> None:
        self._end_batch_callbacks.pop(hash(obj))


class Batched(metaclass=abc.ABCMeta):
    def __init__(self) -> None:
        BatchSingleton().register_start_batch_callback(self, self._start_batch_callback)
        BatchSingleton().register_end_batch_callback(self, self._end_batch_callback)

    def __del__(self) -> None:
        BatchSingleton().unregister_start_batch_callback(self)
        BatchSingleton().unregister_end_batch_callback(self)

    @abc.abstractmethod
    def _start_batch_callback(self) -> None:
        pass

    @abc.abstractmethod
    def _end_batch_callback(self) -> None:
        pass

    @abc.abstractmethod
    def __hash__(self) -> int:
        pass
