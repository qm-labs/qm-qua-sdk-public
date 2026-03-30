from typing import Dict, Type, Tuple, Union, cast

from qm.exceptions import QmQuaException
from qm.grpc.qm.pb import errors_pb2, job_manager_pb2

ResponseType = Union[
    job_manager_pb2.InsertInputStreamResponse,
    job_manager_pb2.SetElementCorrectionResponse,
    job_manager_pb2.GetElementCorrectionResponse,
]

RequestType = Union[
    job_manager_pb2.InsertInputStreamRequest,
    job_manager_pb2.SetElementCorrectionRequest,
    job_manager_pb2.GetElementCorrectionRequest,
]


class QmApiError(QmQuaException):
    @staticmethod
    def build_from_response(request: RequestType, response: ResponseType) -> "QmApiError":
        return QmApiError(0, str(response))

    def __init__(self, code: int, message: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class UnspecifiedError(QmApiError):
    @staticmethod
    def build_from_response(request: RequestType, response: ResponseType) -> "UnspecifiedError":
        return UnspecifiedError("Unspecified operation specific error")

    def __init__(self, message: str) -> None:
        super().__init__(0, message)


class _QmJobError(QmApiError):
    """Base class for exceptions in this module."""

    pass


class MissingJobError(_QmJobError):
    """if the job isn't recognized by the server (can happen if it never ran or if it was already deleted)"""

    def __init__(self) -> None:
        super().__init__(1000)


class InvalidJobExecutionStatusError(_QmJobError):
    def __init__(self) -> None:
        super().__init__(1001)


class InvalidOperationOnSimulatorJobError(_QmJobError):
    def __init__(self) -> None:
        super().__init__(1002)


class InvalidOperationOnRealJobError(_QmJobError):
    def __init__(self) -> None:
        super().__init__(1003)


class UnknownInputStreamError(_QmJobError):
    def __init__(self) -> None:
        super().__init__(1006)


class ConfigQueryError(QmApiError):
    pass


class MissingElementError(ConfigQueryError):
    """"""

    @staticmethod
    def build_from_response(request: RequestType, response: ResponseType) -> "MissingElementError":
        return MissingElementError(response.jobManagerResponseHeader.jobErrorDetails.message)

    def __init__(self, message: str):
        super().__init__(4001, message)


class MissingDigitalInputError(ConfigQueryError):
    """"""

    @staticmethod
    def _build_from_response(request: RequestType, response: ResponseType) -> "MissingDigitalInputError":
        return MissingDigitalInputError(response.jobManagerResponseHeader.jobErrorDetails.message)

    def __init__(self, message: str):
        super().__init__(4002, message)


class _InvalidConfigChangeError(QmApiError):
    pass


class ElementWithSingleInputError(_InvalidConfigChangeError):
    @staticmethod
    def build_from_response(request: RequestType, response: ResponseType) -> "ElementWithSingleInputError":
        return ElementWithSingleInputError(
            cast(
                Union[job_manager_pb2.SetElementCorrectionRequest, job_manager_pb2.GetElementCorrectionRequest], request
            ).qeName
        )

    def __init__(self, element_name: str):
        super().__init__(3000)
        self.element_name = element_name


class InvalidElementCorrectionError(_InvalidConfigChangeError):
    """If the correction values are invalid"""

    @staticmethod
    def build_from_response(request: RequestType, response: ResponseType) -> "InvalidElementCorrectionError":
        return InvalidElementCorrectionError(
            response.jobManagerResponseHeader.jobErrorDetails.message,
            cast(
                Union[job_manager_pb2.SetElementCorrectionRequest, job_manager_pb2.GetElementCorrectionRequest], request
            ).qeName,
            (
                cast(
                    Union[job_manager_pb2.SetElementCorrectionRequest, job_manager_pb2.GetElementCorrectionRequest],
                    request,
                ).correction.v00,
                cast(
                    Union[job_manager_pb2.SetElementCorrectionRequest, job_manager_pb2.GetElementCorrectionRequest],
                    request,
                ).correction.v01,
                cast(
                    Union[job_manager_pb2.SetElementCorrectionRequest, job_manager_pb2.GetElementCorrectionRequest],
                    request,
                ).correction.v10,
                cast(
                    Union[job_manager_pb2.SetElementCorrectionRequest, job_manager_pb2.GetElementCorrectionRequest],
                    request,
                ).correction.v11,
            ),
        )

    def __init__(
        self,
        message: str,
        element_name: str,
        correction: Tuple[float, float, float, float],
    ) -> None:
        super().__init__(3001, message)
        self.element_name = element_name
        self.correction = correction


class ElementWithoutIntermediateFrequencyError(_InvalidConfigChangeError):
    @staticmethod
    def build_from_response(request: RequestType, response: ResponseType) -> "ElementWithoutIntermediateFrequencyError":
        return ElementWithoutIntermediateFrequencyError(
            cast(
                Union[job_manager_pb2.SetElementCorrectionRequest, job_manager_pb2.GetElementCorrectionRequest], request
            ).qeName
        )

    def __init__(self, element_name: str):
        super().__init__(3002)
        self.element_name = element_name


class InvalidDigitalInputThresholdError(_InvalidConfigChangeError):
    @staticmethod
    def build_from_response(request: RequestType, response: ResponseType) -> "InvalidDigitalInputThresholdError":
        return InvalidDigitalInputThresholdError(response.jobManagerResponseHeader.jobErrorDetails.message)

    def __init__(self, message: str):
        super().__init__(3003)
        self.message = message


class InvalidDigitalInputDeadtimeError(_InvalidConfigChangeError):
    @staticmethod
    def build_from_response(request: RequestType, response: ResponseType) -> "InvalidDigitalInputDeadtimeError":
        return InvalidDigitalInputDeadtimeError(response.jobManagerResponseHeader.jobErrorDetails.message)

    def __init__(self, message: str):
        super().__init__(3004)
        self.message = message


class InvalidDigitalInputPolarityError(_InvalidConfigChangeError):
    @staticmethod
    def build_from_response(request: RequestType, response: ResponseType) -> "InvalidDigitalInputPolarityError":
        return InvalidDigitalInputPolarityError(response.jobManagerResponseHeader.jobErrorDetails.message)

    def __init__(self, message: str):
        super().__init__(3005)
        self.message = message


def _handle_job_manager_error(
    request: RequestType,
    response: ResponseType,
    valid_errors: Tuple[Type[QmQuaException], ...],
) -> None:
    api_response: job_manager_pb2.JobManagerResponseHeader = response.jobManagerResponseHeader
    if not api_response.success:
        error_type = api_response.jobManagerErrorType

        if error_type == errors_pb2.JobManagerErrorTypes.MissingJobError:
            raise MissingJobError()
        elif error_type == errors_pb2.JobManagerErrorTypes.InvalidJobExecutionStatusError:
            raise InvalidJobExecutionStatusError()
        elif error_type == errors_pb2.JobManagerErrorTypes.InvalidOperationOnSimulatorJobError:
            raise InvalidOperationOnSimulatorJobError()
        elif error_type == errors_pb2.JobManagerErrorTypes.InvalidOperationOnRealJobError:
            raise InvalidOperationOnRealJobError()
        elif error_type == errors_pb2.JobManagerErrorTypes.JobOperationSpecificError:
            exception_to_raise = _get_handle_job_operation_error(request, response)
            if exception_to_raise is not None and type(exception_to_raise) in valid_errors:
                raise exception_to_raise
            else:
                raise UnspecifiedError("Unspecified operation specific error")
        elif error_type == errors_pb2.JobManagerErrorTypes.ConfigQueryError:
            exception_to_raise = _get_handle_config_query_error(request, response)
            if exception_to_raise is not None and type(exception_to_raise) in valid_errors:
                raise exception_to_raise
            else:
                raise UnspecifiedError("Unspecified operation specific error")
        elif error_type == errors_pb2.JobManagerErrorTypes.UnknownInputStreamError:
            raise UnknownInputStreamError()
        else:
            raise UnspecifiedError("Unspecified operation error")


def _get_handle_config_query_error(request: RequestType, response: ResponseType) -> QmApiError:
    error_type = response.jobManagerResponseHeader.jobErrorDetails.configQueryErrorType
    errors: Dict[int, Type[QmApiError]] = {
        errors_pb2.ConfigQueryErrorTypes.MissingElementError: MissingElementError,
        errors_pb2.ConfigQueryErrorTypes.MissingDigitalInputError: MissingDigitalInputError,
    }

    return errors.get(error_type, UnspecifiedError).build_from_response(request, response)


def _get_handle_job_operation_error(request: RequestType, response: ResponseType) -> QmApiError:
    error_type = response.jobManagerResponseHeader.jobErrorDetails.jobOperationSpecificErrorType
    errors: Dict[int, Type[QmApiError]] = {
        errors_pb2.JobOperationSpecificErrorTypes.SingleInputElementError: ElementWithSingleInputError,
        errors_pb2.JobOperationSpecificErrorTypes.InvalidCorrectionMatrixError: InvalidElementCorrectionError,
        errors_pb2.JobOperationSpecificErrorTypes.ElementWithoutIntermediateFrequencyError: ElementWithoutIntermediateFrequencyError,
        errors_pb2.JobOperationSpecificErrorTypes.InvalidDigitalInputThresholdError: InvalidDigitalInputThresholdError,
        errors_pb2.JobOperationSpecificErrorTypes.InvalidDigitalInputDeadtimeError: InvalidDigitalInputDeadtimeError,
        errors_pb2.JobOperationSpecificErrorTypes.InvalidDigitalInputPolarityError: InvalidDigitalInputPolarityError,
    }

    return errors.get(error_type, UnspecifiedError).build_from_response(request, response)
