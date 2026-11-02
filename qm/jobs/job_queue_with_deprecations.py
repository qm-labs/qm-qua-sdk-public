import logging
from typing_extensions import deprecated
from typing import TYPE_CHECKING, Tuple, Optional

from qm.api.v2.job_api import JobApi
from qm.program.program import Program
from qm.jobs.job_queue_base import QmQueueBase
from qm.api.models.capabilities import ServerCapabilities
from qm.api.models.compiler import CompilerOptionArguments
from qm.api.v2.job_api.job_api import JobApiWithDeprecations
from qm.utils.deprecation_utils import QmQuaDeprecationWarning
from qm.type_hinting.execution_overrides import ExecutionOverridesType

logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from qm.api.v2.qm_api_old import QmApiWithDeprecations


class QmQueueWithDeprecations(QmQueueBase[JobApi]):
    """The pending-jobs queue accessed via `qm.queue` on the OPX1000 with QOP3.x. Wraps the new
    job API; each method here is a deprecated wrapper kept for backward compatibility — see the
    individual method docstrings for their replacements.
    """

    def __init__(self, api: "QmApiWithDeprecations", capabilities: ServerCapabilities):
        super().__init__(capabilities)
        self._api = api

    @property
    @deprecated(
        'queue.pending_jobs is deprecated since "1.2.0" and will be removed in "2.0.0". '
        'This property is going to be removed, use qm.get_jobs("In queue")',
        category=QmQuaDeprecationWarning,
        stacklevel=1,
    )
    def pending_jobs(self) -> Tuple[JobApiWithDeprecations, ...]:
        """The pending jobs in the queue.

        Deprecated since 1.2.0; will be removed in 2.0.0. Use ``qm.get_jobs("In queue")`` instead.
        """
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

    @deprecated(
        'queue.add is deprecated since "1.2.0" and will be removed in "2.0.0". '
        "This method is going to be removed, use qm.add_to_queue",
        category=QmQuaDeprecationWarning,
        stacklevel=1,
    )
    def add(
        self,
        program: Program,
        compiler_options: Optional[CompilerOptionArguments] = None,
    ) -> JobApi:
        """Adds a QmJob to the queue.
        Programs in the queue will play as soon as possible.

        Deprecated since 1.2.0; will be removed in 2.0.0. Use ``qm.add_to_queue()`` instead.

        Args:
            program: A QUA program
            compiler_options: Optional arguments for compilation

        Returns:
            The job that was added to the queue

        Example:
            ```python
            qm.queue.add(program)  # adds at the end of the queue
            qm.queue.insert(program, position)  # adds at position
            ```
        """
        if compiler_options is None:
            compiler_options = CompilerOptionArguments()

        return self._api.add_to_queue(program)

    @deprecated(
        'queue.add_compiled is deprecated since "1.2.0" and will be removed in "2.0.0". '
        "This method is going to be removed, use `qm.add_to_queue()`",
        category=QmQuaDeprecationWarning,
        stacklevel=1,
    )
    def add_compiled(self, program_id: str, overrides: Optional[ExecutionOverridesType] = None) -> JobApi:
        """Deprecated - This method is going to be removed, use `qm.add_to_queue()`.

        Adds a compiled QUA program to the end of the queue, optionally
        overriding the values of analog waveforms defined in the program.
        Programs in the queue will play as soon as possible.
        For a detailed explanation see
        [Precompile Jobs](../Guides/features.md#precompile-jobs).

        Args:
            program_id: A QUA program ID returned from the compile
                function
            overrides: Object containing Waveforms to run the program
                with

        Returns:
            The job that was added to the queue
        """
        return self._api.add_to_queue(program_id, overrides=overrides)

    @deprecated(
        'queue.remove_by_id is deprecated since "1.2.0" and will be removed in "2.0.0". '
        "This method is going to be removed, use qm.clear_queue(user_ids=[user_id]) or job.cancel()",
        category=QmQuaDeprecationWarning,
        stacklevel=1,
    )
    def remove_by_id(self, job_id: str) -> int:
        """Removes the pending job with a specific job id

        Deprecated since 1.2.0; will be removed in 2.0.0. Use ``qm.clear_queue([job_id])`` or ``job.cancel()`` instead.

        Args:
            job_id: a QMJob id

        Returns:
            The number of jobs removed

        Example:
            ```python
            qm.queue.remove_by_id(job_id)
            ```
        """
        if job_id is None or job_id == "":
            raise ValueError("job_id can not be empty")
        return len(self._api.clear_queue([job_id]))

    @deprecated(
        'queue.remove_by_user_id is deprecated since "1.2.0" and will be removed in "2.0.0". '
        "This method is going to be removed, use qm.clear_queue(user_ids=[user_id]) or job.cancel()",
        category=QmQuaDeprecationWarning,
        stacklevel=1,
    )
    def remove_by_user_id(self, user_id: str) -> int:
        """Removes all pending jobs with a specific user id

        Deprecated since 1.2.0; will be removed in 2.0.0. Use ``qm.clear_queue(user_ids=[user_id])`` or ``job.cancel()`` instead.

        Args:
            user_id: a user id

        Returns:
            The number of jobs removed

        Example:
            ```python
            qm.queue.remove_by_id(job_id)
            ```
        """
        return len(self._api.clear_queue(user_ids=[user_id]))

    @deprecated(
        'queue.clear is deprecated since "1.2.0" and will be removed in "2.0.0". '
        "This method is going to be removed, use qm.clear_queue",
        category=QmQuaDeprecationWarning,
        stacklevel=1,
    )
    def clear(self) -> int:
        """Empties the queue from all pending jobs

        Deprecated since 1.2.0; will be removed in 2.0.0. Use ``qm.clear_queue()`` instead.

        Returns:
            The number of jobs removed
        """
        return len(self._api.clear_queue())
