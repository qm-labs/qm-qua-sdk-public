import abc
import warnings
from pathlib import Path
from typing import BinaryIO, Optional

from qm.utils import deprecation_message


class BinaryAsset(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def for_writing(self) -> BinaryIO:
        raise NotImplementedError()

    @abc.abstractmethod
    def for_reading(self) -> BinaryIO:
        raise NotImplementedError()


class BaseStore(metaclass=abc.ABCMeta):
    """The interface to saving data from a running job"""

    def __init__(self) -> None:
        warnings.warn(
            deprecation_message(
                method="BaseStore",
                deprecated_in="1.2.3",
                removed_in="1.3.0",
                details="Base store is deprecated, and also everything that inherits from it. Please remove it from your code.",
            )
        )
        super().__init__()

    @abc.abstractmethod
    def job_named_result(self, job_id: str, name: str) -> BinaryAsset:
        raise NotImplementedError()

    @abc.abstractmethod
    def all_job_results(self, job_id: str) -> BinaryAsset:
        raise NotImplementedError()


class FileBinaryAsset(BinaryAsset):
    def __init__(self, path: Path) -> None:
        super().__init__()
        self._path = path
        self._opened_fd: Optional[BinaryIO] = None

    def close(self) -> None:
        if self._opened_fd:
            self._opened_fd.close()

    def for_writing(self) -> BinaryIO:
        self.close()
        self._opened_fd = self._path.open("wb")
        return self._opened_fd

    def for_reading(self) -> BinaryIO:
        self.close()
        self._opened_fd = self._path.open("rb")
        return self._opened_fd


class SimpleFileStore(BaseStore):
    def __init__(self, root: str = ".") -> None:
        super().__init__()
        self._root = Path(root).absolute()

    def _job_path(self, job_id: str) -> Path:
        path = Path(f"{self._root}/{job_id}")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def job_named_result(self, job_id: str, name: str) -> BinaryAsset:
        return FileBinaryAsset(self._job_path(job_id).joinpath(f"result_{name}.npy"))

    def all_job_results(self, job_id: str) -> BinaryAsset:
        return FileBinaryAsset(self._job_path(job_id).joinpath("results.npz"))
