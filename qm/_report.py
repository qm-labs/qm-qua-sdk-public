from enum import Enum
from typing import List
from dataclasses import dataclass

from qm.api.job_result_api import JobResultServiceApi
from qm.grpc.results_analyser import GetJobErrorsResponseExecutionErrorSeverity


class ExecutionErrorSeverity(Enum):
    Warn = 0
    Error = 1


@dataclass(frozen=True)
class ExecutionError:
    error_code: int
    message: str
    severity: ExecutionErrorSeverity

    def __repr__(self) -> str:
        return f"{self.error_code}\t\t{self.severity.name}\t\t{self.message}"


class ExecutionReport:
    def __init__(self, job_id: str, service: JobResultServiceApi) -> None:
        self._job_id = job_id
        self._service = service
        self._errors = self._load_errors()

    def _load_errors(self) -> List[ExecutionError]:
        return [
            ExecutionError(
                error_code=item.error_code,
                message=item.message,
                severity=ExecutionReport._parse_error_severity(item.error_severity),
            )
            for item in self._service.get_job_errors(self._job_id)
        ]

    @staticmethod
    def _parse_error_severity(error_severity: GetJobErrorsResponseExecutionErrorSeverity) -> ExecutionErrorSeverity:
        if error_severity == GetJobErrorsResponseExecutionErrorSeverity.WARNING:
            return ExecutionErrorSeverity.Warn
        elif error_severity == GetJobErrorsResponseExecutionErrorSeverity.ERROR:
            return ExecutionErrorSeverity.Error
        raise TypeError(f"No severity level: {error_severity}")

    def has_errors(self) -> bool:
        """Returns: True if encountered a runtime error while executing the job."""
        return len(self._errors) > 0

    def errors(self) -> List[ExecutionError]:
        """Returns: list of all execution errors for this job"""
        return self._errors.copy()

    @property
    def _report_header(self) -> str:
        return (
            f"Execution report for job {self._job_id}\nErrors:\n"
            f"Please refer to section: "
            f"Error Indications and Error Reporting in documentation for additional information\n\n"
            "code\t\tseverity\tmessage"
        )

    def __repr__(self) -> str:
        if not self.has_errors():
            return f"Execution report for job {self._job_id}\nNo errors"

        errors_str = self._report_header
        for error in self._errors:
            errors_str += "\n" + str(error)
        return errors_str
