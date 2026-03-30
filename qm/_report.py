from enum import Enum
from typing import List, Union
from dataclasses import dataclass

from qm.grpc.qm.pb import job_results_pb2
from qm.grpc.qm.grpc.v2 import job_api_pb2


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

    @classmethod
    def create_from_grpc_message(
        cls,
        error: Union[
            job_results_pb2.GetJobErrorsResponse.Error,
            job_api_pb2.GetJobErrorsResponse.GetJobErrorsResponseSuccess.Error,
        ],
    ) -> "ExecutionError":
        return cls(
            error_code=error.errorCode,
            message=error.message,
            severity=cls._parse_severity(error.errorSeverity),
        )

    @staticmethod
    def _parse_severity(
        error_severity: Union[  # type: ignore[name-defined]
            job_results_pb2.GetJobErrorsResponse.ExecutionErrorSeverity.ValueType,
            job_api_pb2.GetJobErrorsResponse.GetJobErrorsResponseSuccess.ExecutionErrorSeverity.ValueType,
        ],
    ) -> ExecutionErrorSeverity:
        if error_severity in {
            job_results_pb2.GetJobErrorsResponse.ExecutionErrorSeverity.WARNING,
            job_api_pb2.GetJobErrorsResponse.GetJobErrorsResponseSuccess.ExecutionErrorSeverity.WARNING,
        }:
            return ExecutionErrorSeverity.Warn
        elif error_severity in {
            job_results_pb2.GetJobErrorsResponse.ExecutionErrorSeverity.ERROR,
            job_api_pb2.GetJobErrorsResponse.GetJobErrorsResponseSuccess.ExecutionErrorSeverity.ERROR,
        }:
            return ExecutionErrorSeverity.Error
        raise TypeError(f"No severity level: {error_severity}")


class ExecutionReport:
    def __init__(self, job_id: str, errors: List[ExecutionError]) -> None:
        self._job_id = job_id
        self._errors = errors

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
