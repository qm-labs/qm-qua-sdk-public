import logging
import warnings
from typing import TYPE_CHECKING, Tuple, Optional

from qm.api.v2.job_api import JobApi
from qm.persistence import BaseStore
from qm.program.program import Program
from qm.utils import deprecation_message
from qm.jobs.job_queue_base import QmQueueBase
from qm.api.models.capabilities import ServerCapabilities
from qm.api.models.compiler import CompilerOptionArguments
from qm.api.v2.job_api.job_api import JobApiWithDeprecations

logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from qm.api.v2.qm_api_old import QmApiWithDeprecations


class QmQueueWithDeprecations(QmQueueBase[JobApi]):
    def __init__(self, store: BaseStore, api: "QmApiWithDeprecations", capabilities: ServerCapabilities):
        super().__init__(store, capabilities)
        self._api = api

    @property
    def pending_jobs(self) -> Tuple[JobApiWithDeprecations, ...]:
        warnings.warn(
            deprecation_message(
                method="queue.pending_jobs",
                deprecated_in="1.2.0",
                removed_in="1.4.0",
                details='This property is going to be removed, use qm.get_jobs("In queue").',
            ),
            DeprecationWarning,
            stacklevel=1,
        )
        return self._get_pending_jobs()

    def _get_pending_jobs(
        self, job_id: Optional[str] = None, position: Optional[int] = None, user_id: Optional[str] = None
    ) -> Tuple[JobApiWithDeprecations, ...]:
        if position is not None:
            logger.warning("Position is not supported in the new API")
        new_jobs = self._api.get_jobs(
            job_ids=[job_id] if job_id else [],
            user_ids=[user_id] if user_id else [],
            status=["In queue"],
        )
        result = tuple(self._api.get_job_by_id(job.id) for job in new_jobs)
        return result

    def add(
        self,
        program: Program,
        compiler_options: Optional[CompilerOptionArguments] = None,
    ) -> JobApi:
        """Adds a QmJob to the queue.
        Programs in the queue will play as soon as possible.

        Args:
            program: A QUA program
            compiler_options: Optional arguments for compilation

        Example:
            ```python
            qm.queue.add(program)  # adds at the end of the queue
            qm.queue.insert(program, position)  # adds at position
            ```
        """
        warnings.warn(
            deprecation_message(
                method="queue.add",
                deprecated_in="1.2.0",
                removed_in="1.4.0",
                details="This method is going to be removed, use qm.add_to_queue.",
            ),
            DeprecationWarning,
            stacklevel=1,
        )
        if compiler_options is None:
            compiler_options = CompilerOptionArguments()

        return self._api.add_to_queue(program)

    def add_compiled(self, program_id: str) -> JobApi:
        """Deprecated - This method is going to be removed, use `qm.add_to_queue()`.

        Adds a compiled QUA program to the end of the queueץ
        Programs in the queue will play as soon as possible.
        For a detailed explanation see
        [Precompile Jobs](../Guides/features.md#precompile-jobs).

        Args:
            program_id: A QUA program ID returned from the compile
                function
        """
        warnings.warn(
            deprecation_message(
                method="queue.add_compiled",
                deprecated_in="1.2.0",
                removed_in="1.4.0",
                details="This method is going to be removed, use `qm.add_to_queue()`.",
            ),
            DeprecationWarning,
            stacklevel=1,
        )
        return self._api.add_to_queue(program_id)

    def remove_by_id(self, job_id: str) -> int:
        """Removes the pending job with a specific job id

        Args:
            job_id: a QMJob id

        Returns:
            The number of jobs removed

        Example:
            ```python
            qm.queue.remove_by_id(job_id)
            ```
        """
        warnings.warn(
            deprecation_message(
                method="queue.remove_by_id",
                deprecated_in="1.2.0",
                removed_in="1.4.0",
                details="This method is going to be removed, use qm.clear_queue(user_ids=[user_id]) or job.cancel().",
            ),
            DeprecationWarning,
            stacklevel=1,
        )
        if job_id is None or job_id == "":
            raise ValueError("job_id can not be empty")
        return len(self._api.clear_queue([job_id]))

    def remove_by_user_id(self, user_id: str) -> int:
        """Removes all pending jobs with a specific user id

        Args:
            user_id: a user id

        Returns:
            The number of jobs removed

        Example:
            ```python
            qm.queue.remove_by_id(job_id)
            ```
        """
        warnings.warn(
            deprecation_message(
                method="queue.remove_by_user_id",
                deprecated_in="1.2.0",
                removed_in="1.4.0",
                details="This method is going to be removed, use qm.clear_queue(user_ids=[user_id]) or job.cancel().",
            ),
            DeprecationWarning,
            stacklevel=1,
        )
        return len(self._api.clear_queue(user_ids=[user_id]))

    def clear(self) -> int:
        """Empties the queue from all pending jobs

        Returns:
            The number of jobs removed
        """
        warnings.warn(
            deprecation_message(
                method="queue.clear",
                deprecated_in="1.2.0",
                removed_in="1.4.0",
                details="This method is going to be removed, use qm.clear_queue.",
            ),
            DeprecationWarning,
            stacklevel=1,
        )
        return len(self._api.clear_queue())
