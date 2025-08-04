from pprint import pformat
from collections import defaultdict
from collections.abc import Collection
from abc import ABCMeta, abstractmethod
from typing import Any, List, Generic, TypeVar, Sequence

import betterproto
from marshmallow import ValidationError

from qm.StreamMetadata import StreamMetadataError
from qm.grpc.qm_manager import ConfigValidationMessage, PhysicalValidationMessage


class QmQuaException(Exception):
    def __init__(self, message: str, *args: Any):
        self.message = message
        super().__init__(message, *args)


class QmmException(QmQuaException):
    pass


class OctaveConfigDeprecationException(QmmException):
    def __init__(self) -> None:
        super().__init__(
            "Received a response from the QM-app that includes octaves, please remove the OctaveConfig "
            "and move the configuration to the QUA-config."
        )


class ProgramScopeAccessError(QmQuaException):
    def __init__(self) -> None:
        super().__init__("Program cannot be accessed while still in scope.")


class NoScopeFoundException(QmQuaException):
    pass


class JobNotFoundException(QmQuaException):
    def __init__(self, job_id: str) -> None:
        super().__init__(f"Job {job_id} not found.")


class OpenQmException(QmQuaException):
    def __init__(
        self,
        config_validation_errors: Sequence[ConfigValidationMessage],
        physical_validation_errors: Sequence[PhysicalValidationMessage],
    ):
        self.config_validation_formatted_errors = QopConfigValidationError(
            config_validation_errors
        ).validation_formatted_errors
        self.physical_validation_formatted_errors = QopPhysicalValidationError(
            physical_validation_errors
        ).validation_formatted_errors

    def __str__(self) -> str:
        config_validation_error_message = "\n".join(self.config_validation_formatted_errors)
        physical_validation_error_message = "\n".join(self.physical_validation_formatted_errors)

        return f"Can not open QM, see the following errors:\n{config_validation_error_message}\n{physical_validation_error_message}"


class FailedToExecuteJobException(QmQuaException):
    pass


class FailedToAddJobToQueueException(QmQuaException):
    pass


class CompilationException(QmQuaException):
    pass


class JobCancelledError(QmQuaException):
    pass


class JobFailedError(QmQuaException):
    pass


class ErrorJobStateError(QmQuaException):
    def __init__(self, *args: Any, error_list: List[str]):
        super().__init__(*args)
        self._error_list = error_list if error_list else []

    def __str__(self) -> str:
        errors_string = "\n".join(error for error in self._error_list)
        return f"{super().__str__()}\n{errors_string}"


class UnknownJobStateError(QmQuaException):
    pass


class InvalidStreamMetadataError(QmQuaException):
    def __init__(self, stream_metadata_errors: List[StreamMetadataError], *args: Any):
        stream_errors_message = "\n".join(f"{e.error} at: {e.location}" for e in stream_metadata_errors)
        message = f"Error creating stream metadata:\n{stream_errors_message}"
        super().__init__(message, *args)


class ConfigValidationException(QmQuaException):
    pass


def _format_validation_error(curr_error: object) -> object:
    if isinstance(curr_error, defaultdict):
        to_return = {}
        for k, v in curr_error.items():
            for error in v.values():
                to_return[k] = _format_validation_error(error)
                # There is a hidden assumption here of a single error per entry
                break
        return to_return
    elif isinstance(curr_error, dict):
        to_return = {}
        for k, v in curr_error.items():
            to_return[k] = _format_validation_error(v)
        return to_return
    elif isinstance(curr_error, Collection):
        if all(isinstance(i, str) for i in curr_error):
            return curr_error
        else:
            return [_format_validation_error(i) for i in curr_error]
    raise ValueError(f"Unexpected type {type(curr_error)} in validation error")


class ConfigSchemaError(ConfigValidationException):
    def __init__(self, data: ValidationError) -> None:
        self.data = data
        self.formatted_dict = _format_validation_error(data.messages)
        super().__init__(pformat(self.formatted_dict, width=120))


class NoInputsOrOutputsError(ConfigValidationException):
    def __init__(self) -> None:
        super().__init__("An element must have either outputs or inputs. Please specify at least one.")


class ConfigSerializationException(QmQuaException):
    pass


class UnsupportedCapabilitiesError(QmQuaException):
    pass


class CapabilitiesNotInitializedError(QmQuaException):
    def __init__(self) -> None:
        super().__init__(
            "Capabilities are required but not initialized. Please use QuantumMachinesManager to connect to a QOP server"
            " or manually set the capabilities using the `QuantumMachinesManager.set_capabilities_offline()` function."
            " Please see the function documentation on how to set the capabilities you need."
        )


class InvalidConfigError(QmQuaException):
    pass


class QMHealthCheckError(QmQuaException):
    pass


class QMFailedToGetQuantumMachineError(QmQuaException):
    pass


class QMSimulationError(QmQuaException):
    pass


class QmFailedToCloseQuantumMachineError(QmQuaException):
    pass


class QMFailedToCloseAllQuantumMachinesError(QmFailedToCloseQuantumMachineError):
    pass


class QMRequestError(QmQuaException):
    pass


class QMConnectionError(QmQuaException):
    pass


class QMTimeoutError(QmQuaException):
    pass


class QMRequestDataError(QmQuaException):
    pass


class QmServerDetectionError(QmQuaException):
    pass


class QmValueError(QmQuaException, ValueError):
    pass


class QmInvalidSchemaError(QmQuaException):
    pass


class QmInvalidResult(QmQuaException):
    pass


class QmNoResultsError(QmQuaException):
    pass


class FunctionInputError(QmQuaException):
    pass


class AnotherJobIsRunning(QmQuaException):
    def __init__(self) -> None:
        super().__init__("Another job is running on the QM. Halt it first")


class CalibrationException(QmQuaException):
    pass


class CantCalibrateElementError(CalibrationException):
    pass


class OctaveConnectionError(QmQuaException):
    pass


class OctaveLoopbackError(OctaveConnectionError):
    def __init__(self) -> None:
        super().__init__("lo loopback between different octave devices are not supported.")


class NoOutputPortDeclared(OctaveConnectionError):
    pass


class OctaveCableSwapError(OctaveConnectionError):
    def __init__(self) -> None:
        super().__init__("Cable swap detected. Please check your connections.")


class ElementUpconverterDeclarationError(OctaveConnectionError):
    def __init__(self) -> None:
        super().__init__(
            "Element declaration error, the I and Q connections are not connected to the same upconverter."
        )


class LOFrequencyMismatch(ConfigValidationException):
    def __init__(self) -> None:
        super().__init__(
            "LO frequency mismatch. The frequency stated in the element is different from "
            "the one stated in the Octave, remove the one in the element."
        )


class OctaveConnectionAmbiguity(ConfigValidationException):
    def __init__(self) -> None:
        super().__init__(
            "It is not allowed to override the default connection of the Octave. You should either state the "
            "default connection to Octave in the controller level, or set each port separately in the port level."
        )


class InvalidOctaveParameter(ConfigValidationException):
    pass


class OctaveUnsupportedOnUpdate(ConfigValidationException):
    pass


class ConfigurationLockedByOctave(ConfigValidationException):
    pass


class ElementOutputConnectionAmbiguity(ConfigValidationException):
    pass


class QmRedirectionError(QmQuaException):
    pass


class QmLocationParsingError(QmQuaException):
    pass


class ElementInputConnectionAmbiguity(ConfigValidationException):
    pass


class StreamProcessingDataLossError(QmQuaException):
    pass


class DataFetchingError(QmQuaException):
    pass


ValidationType = TypeVar("ValidationType", PhysicalValidationMessage, ConfigValidationMessage)


class QopValidationError(QmQuaException, Generic[ValidationType], metaclass=ABCMeta):
    def __init__(self, validation_errors: Sequence[ValidationType]):
        self.validation_formatted_errors = self._format_validation_errors(validation_errors)

    @property
    @abstractmethod
    def error_type(self) -> str:
        pass

    def _format_validation_errors(self, validation_errors: Sequence[ValidationType]) -> List[str]:
        error_messages = []
        for sub_error in validation_errors:
            error_messages.append(
                f'{self.error_type} in key "{sub_error.path}" [{sub_error.group}] : {sub_error.message}'
            )
        return error_messages

    def __str__(self) -> str:
        return "\n".join(self.validation_formatted_errors)


class QopPhysicalValidationError(QopValidationError[PhysicalValidationMessage]):
    """
    An exception class for describing physical configuration errors arising from validation by the QOP server.
    """

    @property
    def error_type(self) -> str:
        return "PHYSICAL CONFIG ERROR"


class QopConfigValidationError(QopValidationError[ConfigValidationMessage]):
    """
    An exception class for describing configuration errors arising from validation by the QOP server.
    """

    @property
    def error_type(self) -> str:
        return "CONFIG ERROR"


class ReservedFieldNameError(QmQuaException):
    pass


class InvalidQuaArraySubclassError(QmQuaException):
    pass


ErrorType = TypeVar("ErrorType", bound=betterproto.Message)


class QopResponseError(Exception, Generic[ErrorType]):
    def __init__(self, error: ErrorType):
        self._error = error

    @property
    def error(self) -> ErrorType:
        return self._error

    def __str__(self) -> str:
        details = getattr(self._error, "details", "")
        to_return = f"Error from QOP, details:\n{details}." if details else f"Error from QOP: {self._error}"
        return to_return
