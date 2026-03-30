import logging
from typing import List, Type, Tuple, Optional

from google.protobuf.empty_pb2 import Empty
from google.protobuf.wrappers_pb2 import StringValue

from qm.type_hinting import Value
from qm.api.base_api import BaseApi
from qm.api.models.jobs import InsertDirection
from qm.api.models.capabilities import OPX_FEM_IDX
from qm.grpc.qm.pb.frontend_pb2_grpc import FrontendStub
from qm.api.models.quantum_machine import QuantumMachineData
from qm.utils.protobuf_utils import LOG_LEVEL_MAP, proto_repeated_to_list
from qm.api.models.devices import Polarity, MixerInfo, AnalogOutputPortFilter
from qm.api.models.compiler import CompilerOptionArguments, get_request_compiler_options
from qm.grpc.qm.pb import (
    inc_qua_pb2,
    compiler_pb2,
    frontend_pb2,
    inc_qm_api_pb2,
    qm_manager_pb2,
    inc_qua_config_pb2,
    general_messages_pb2,
)
from qm.exceptions import (
    QMRequestError,
    OpenQmException,
    QMConnectionError,
    QMHealthCheckError,
    QMRequestDataError,
    CompilationException,
    FailedToAddJobToQueueException,
    QMFailedToGetQuantumMachineError,
    QmFailedToCloseQuantumMachineError,
    QMFailedToCloseAllQuantumMachinesError,
)

logger = logging.getLogger(__name__)


class FrontendApi(BaseApi[FrontendStub]):
    @property
    def _stub_class(self) -> Type[FrontendStub]:
        return FrontendStub

    def get_version(self) -> str:
        response: StringValue = self._run(self._stub.GetVersion, Empty(), timeout=self._timeout)
        return response.value

    def healthcheck(self, strict: bool) -> None:
        logger.info("Performing health check")
        response = self._run(self._stub.HealthCheck, Empty(), timeout=self._timeout)

        for warning in response.warningMessages:
            logger.warning(f"Health check warning: {warning}")

        for message in response.message:
            logger.debug(message)

        if not response.ok:
            logger.error(f"Health check error: {response.message}")

            for error in response.errorMessages:
                logger.error(f"Health check error: {error}")

            if strict:
                raise QMHealthCheckError("Health check failed")
            return

        logger.info("Health check passed")

    def reset_data_processing(self) -> None:
        self._run(self._stub.ResetDataProcessing, frontend_pb2.ResetDataProcessingRequest(), timeout=self._timeout)

    def open_qm(
        self,
        config: inc_qua_config_pb2.QuaConfig,
        close_other_machines: bool,
        keep_dc_offsets_when_closing: bool = False,
    ) -> str:
        request = qm_manager_pb2.OpenQuantumMachineRequest(
            config=config, keep_dc_offsets_when_closing=keep_dc_offsets_when_closing
        )

        if close_other_machines:
            request.always = True
        else:
            request.never = True

        response: qm_manager_pb2.OpenQuantumMachineResponse = self._run(
            self._stub.OpenQuantumMachine, request, timeout=self._timeout
        )

        if not response.success:
            open_qm_exception = OpenQmException(response.configValidationErrors, response.physicalValidationErrors)

            for formatted_error in (
                open_qm_exception.physical_validation_formatted_errors
                + open_qm_exception.config_validation_formatted_errors
            ):
                logger.error(formatted_error)

            raise open_qm_exception

        for warning in response.openQmWarnings:
            logger.warning(f"Open QM ended with warning {warning.code}: {warning.message}")

        return response.machineID

    def list_open_quantum_machines(self) -> List[str]:
        response = self._run(self._stub.ListOpenQuantumMachines, Empty(), timeout=self._timeout)
        return list(response.machineIDs)

    def get_quantum_machine(self, qm_id: str) -> QuantumMachineData:
        request = qm_manager_pb2.GetQuantumMachineRequest(machineID=qm_id)
        response = self._run(self._stub.GetQuantumMachine, request, timeout=self._timeout)

        if not response.success:
            error_message = "\n".join([error.message for error in response.errors])
            raise QMFailedToGetQuantumMachineError(f"Failed to fetch quantum machine: {error_message}")

        return QuantumMachineData(machine_id=response.machineID, config=response.config)

    def close_quantum_machine(self, machine_id: str) -> bool:
        request = qm_manager_pb2.CloseQuantumMachineRequest(machineID=machine_id)
        response = self._run(self._stub.CloseQuantumMachine, request, timeout=self._timeout)
        if not response.success:
            raise QmFailedToCloseQuantumMachineError("\n".join(err.message for err in response.errors))
        return True

    def get_quantum_machine_config(self, machine_id: str) -> inc_qua_config_pb2.QuaConfig:
        machine_data = self.get_quantum_machine(machine_id)
        config = machine_data.config

        if len(config.v1beta.controlDevices) == 0:
            for controller_name, controller in config.v1beta.controllers.items():
                config.v1beta.controlDevices[controller_name].CopyFrom(
                    inc_qua_config_pb2.QuaConfig.DeviceDec(
                        fems={OPX_FEM_IDX: inc_qua_config_pb2.QuaConfig.FEMTypes(opx=controller)}
                    )
                )
        return machine_data.config

    def close_all_quantum_machines(self) -> None:
        response = self._run(self._stub.CloseAllQuantumMachines, Empty(), timeout=self._timeout)
        if not response.success:
            messages = [error.message for error in response.errors]
            for msg in messages:
                logger.error(msg)

            raise QMFailedToCloseAllQuantumMachinesError(
                "Can not close all quantum machines. See the following errors:\n" + "\n".join(messages),
            )

    def get_controllers(self) -> List[qm_manager_pb2.Controller]:
        response: qm_manager_pb2.GetControllersResponse = self._run(
            self._stub.GetControllers, Empty(), timeout=self._timeout
        )
        return proto_repeated_to_list(response.controllers)

    def clear_all_job_results(self) -> None:
        self._run(self._stub.ClearAllJobResults, Empty(), timeout=self._timeout)

    def send_debug_command(self, controller_name: str, command: str) -> str:
        request = frontend_pb2.PerformHalDebugCommandRequest(controllerName=controller_name, command=command)
        response: frontend_pb2.PerformHalDebugCommandResponse = self._run(
            self._stub.PerformHalDebugCommand, request, timeout=self._timeout
        )

        if not response.success:
            raise QMConnectionError(response.response)
        return response.response

    def add_to_queue(
        self,
        machine_id: str,
        program: inc_qua_pb2.QuaProgram,
        compiler_options: CompilerOptionArguments,
        insert_direction: InsertDirection,
    ) -> str:
        queue_position = frontend_pb2.QueuePosition()
        if insert_direction == InsertDirection.start:
            queue_position.start.CopyFrom(Empty())
        elif insert_direction == InsertDirection.end:
            queue_position.end.CopyFrom(Empty())

        program.compilerOptions.CopyFrom(get_request_compiler_options(compiler_options))

        request = frontend_pb2.AddToQueueRequest(
            quantumMachineId=machine_id,
            highLevelProgram=program,
            queuePosition=queue_position,
        )

        logger.info("Sending program to QOP for compilation")

        response: frontend_pb2.AddToQueueResponse = self._run(self._stub.AddToQueue, request, timeout=None)

        for message in response.messages:
            logger.log(LOG_LEVEL_MAP[message.level], message.message)

        job_id = response.jobId
        if not response.ok:
            logger.error(f"Job {job_id} failed. Failed to execute program.")
            raise FailedToAddJobToQueueException(f"Job {job_id} failed. Failed to execute program.")

        return job_id

    def add_compiled_to_queue(
        self, machine_id: str, program_id: str, execution_overrides: frontend_pb2.ExecutionOverrides
    ) -> str:
        queue_position = frontend_pb2.QueuePosition()
        queue_position.end.CopyFrom(Empty())

        request = frontend_pb2.AddCompiledToQueueRequest(
            quantumMachineId=machine_id,
            programId=program_id,
            queuePosition=queue_position,
            executionOverrides=execution_overrides,
        )

        response: frontend_pb2.AddCompiledToQueueResponse = self._run(
            self._stub.AddCompiledToQueue, request, timeout=self._timeout
        )

        job_id = response.jobId

        for err in response.errors:
            logger.error(err.message)

        if not response.ok:
            logger.error(f"Job {job_id} failed. Failed to execute program.")
            raise FailedToAddJobToQueueException(f"Job {job_id} failed. Failed to execute program.")

        return job_id

    def compile(
        self,
        machine_id: str,
        program: inc_qua_pb2.QuaProgram,
        compiler_options: CompilerOptionArguments,
    ) -> str:
        program.compilerOptions.CopyFrom(get_request_compiler_options(compiler_options))
        request = frontend_pb2.CompileRequest(quantumMachineId=machine_id, highLevelProgram=program)

        response: frontend_pb2.CompileResponse = self._run(self._stub.Compile, request, timeout=None)

        for message in response.messages:
            logger.log(LOG_LEVEL_MAP[message.level], message.message)

        program_id = response.programId
        if not response.ok:
            logger.error(f"Compilation of program {program_id} failed")
            raise CompilationException(f"Compilation of program {program_id} failed")
        return program_id

    def _perform_qm_request(self, request: inc_qm_api_pb2.HighQmApiRequest) -> None:
        response = self._run(self._stub.PerformQmRequest, request, timeout=self._timeout)

        if not response.ok:
            error_message = "\n".join(it.message for it in response.errors)
            logger.error(f"Failed: {error_message}")
            raise QMRequestError(f"Failed: {error_message}")

    def set_correction(self, machine_id: str, mixer: MixerInfo, correction: general_messages_pb2.Matrix) -> None:
        correction_request = inc_qm_api_pb2.HighQmApiRequest.SetCorrection(
            mixer=inc_qm_api_pb2.HighQmApiRequest.SetCorrectionMixerInfo(
                mixer=mixer.mixer,
                frequencyNegative=mixer.frequency_negative,
                intermediateFrequency=mixer.intermediate_frequency,
                intermediateFrequencyDouble=mixer.intermediate_frequency_double,
                loFrequency=mixer.lo_frequency,
                loFrequencyDouble=mixer.lo_frequency_double,
            ),
            # For some reason we have two general_messages_pb2.Matrix messages
            correction=inc_qm_api_pb2.Matrix(
                v00=correction.v00, v01=correction.v01, v10=correction.v10, v11=correction.v11
            ),
            # although they are the same...
        )
        request = inc_qm_api_pb2.HighQmApiRequest(quantumMachineId=machine_id, setCorrection=correction_request)
        self._perform_qm_request(request)

    def set_intermediate_frequency(self, machine_id: str, element: str, value: float) -> None:
        set_frequency_request = inc_qm_api_pb2.HighQmApiRequest.SetFrequency(qe=element, value=value)
        request = inc_qm_api_pb2.HighQmApiRequest(quantumMachineId=machine_id, setFrequency=set_frequency_request)
        self._perform_qm_request(request)

    def set_output_dc_offset(self, machine_id: str, element: str, element_port: str, offset: float) -> None:
        output_dc_offset_request = inc_qm_api_pb2.HighQmApiRequest.SetOutputDcOffset(
            qe=inc_qm_api_pb2.HighQmApiRequest.QePort(qe=element, port=element_port), I=offset, Q=offset
        )
        request = inc_qm_api_pb2.HighQmApiRequest(
            quantumMachineId=machine_id, setOutputDcOffset=output_dc_offset_request
        )
        self._perform_qm_request(request)

    def set_output_filter_taps(
        self,
        machine_id: str,
        element: str,
        element_port: str,
        filter_port: AnalogOutputPortFilter,
    ) -> None:
        output_filter_tap_request = inc_qm_api_pb2.HighQmApiRequest.SetOutputFilterTaps(
            qe=inc_qm_api_pb2.HighQmApiRequest.QePort(qe=element, port=element_port),
            filter=inc_qm_api_pb2.HighQmApiRequest.AnalogOutputPortFilter(
                feedback=filter_port.feedback, feedforward=filter_port.feedforward
            ),
        )
        request = inc_qm_api_pb2.HighQmApiRequest(
            quantumMachineId=machine_id,
            setOutputFilterTaps=output_filter_tap_request,
        )
        self._perform_qm_request(request)

    def set_input_dc_offset(self, machine_id: str, element: str, element_port: str, offset: float) -> None:
        input_dc_offset_request = inc_qm_api_pb2.HighQmApiRequest.SetInputDcOffset(
            qe=inc_qm_api_pb2.HighQmApiRequest.QePort(qe=element, port=element_port), offset=offset
        )
        request = inc_qm_api_pb2.HighQmApiRequest(quantumMachineId=machine_id, setInputDcOffset=input_dc_offset_request)
        self._perform_qm_request(request)

    def set_output_digital_delay(self, machine_id: str, element: str, element_port: str, delay: int) -> None:
        digital_delay_request = inc_qm_api_pb2.HighQmApiRequest.SetDigitalRoute(
            delay=inc_qm_api_pb2.HighQmApiRequest.QePort(qe=element, port=element_port), value=delay
        )
        request = inc_qm_api_pb2.HighQmApiRequest(quantumMachineId=machine_id, setDigitalRoute=digital_delay_request)
        self._perform_qm_request(request)

    def set_output_digital_buffer(self, machine_id: str, element: str, element_port: str, buffer: int) -> None:
        digital_buffer_request = inc_qm_api_pb2.HighQmApiRequest.SetDigitalRoute(
            buffer=inc_qm_api_pb2.HighQmApiRequest.QePort(qe=element, port=element_port), value=buffer
        )
        request = inc_qm_api_pb2.HighQmApiRequest(quantumMachineId=machine_id, setDigitalRoute=digital_buffer_request)
        self._perform_qm_request(request)

    def set_io_values(self, machine_id: str, values: List[Optional[Value]]) -> None:
        type_to_value_mapping = {
            int: "intValue",
            float: "doubleValue",
            bool: "booleanValue",
        }

        set_data = []
        for index, value in enumerate(values):
            if value is not None:
                set_data_request = inc_qm_api_pb2.HighQmApiRequest.IOValueSetData(io_number=index + 1)
                setattr(set_data_request, type_to_value_mapping[type(value)], value)
                set_data.append(set_data_request)

        set_io_values = inc_qm_api_pb2.HighQmApiRequest.SetIOValues(all=True, ioValueSetData=set_data)
        request = inc_qm_api_pb2.HighQmApiRequest(quantumMachineId=machine_id, setIOValues=set_io_values)
        self._perform_qm_request(request)

    def set_digital_input_threshold(
        self, machine_id: str, controller_name: str, fem_number: int, port_number: int, threshold: float
    ) -> None:
        digital_input_threshold_request = inc_qm_api_pb2.HighQmApiRequest.SetDigitalInputThreshold(
            digitalPort=inc_qm_api_pb2.DigitalInputPort(
                controllerName=controller_name, fem_Number=fem_number, portNumber=port_number
            ),
            threshold=threshold,
        )
        request = inc_qm_api_pb2.HighQmApiRequest(
            quantumMachineId=machine_id,
            setDigitalInputThreshold=digital_input_threshold_request,
        )
        self._perform_qm_request(request)

    def set_digital_input_dead_time(
        self, machine_id: str, controller_name: str, fem_number: int, port_number: int, dead_time: int
    ) -> None:
        digital_input_dead_time_request = inc_qm_api_pb2.HighQmApiRequest.SetDigitalInputDeadtime(
            digitalPort=inc_qm_api_pb2.DigitalInputPort(
                controllerName=controller_name, fem_Number=fem_number, portNumber=port_number
            ),
            deadtime=dead_time,
        )
        request = inc_qm_api_pb2.HighQmApiRequest(
            quantumMachineId=machine_id,
            setDigitalInputDeadtime=digital_input_dead_time_request,
        )
        self._perform_qm_request(request)

    def set_digital_input_polarity(
        self,
        machine_id: str,
        controller_name: str,
        fem_number: int,
        port_number: int,
        polarity: Polarity,
    ) -> None:
        digital_input_polarity_request = inc_qm_api_pb2.HighQmApiRequest.SetDigitalInputPolarity(
            digitalPort=inc_qm_api_pb2.DigitalInputPort(
                controllerName=controller_name, fem_Number=fem_number, portNumber=port_number
            ),
            polarity=polarity.value,
        )
        request = inc_qm_api_pb2.HighQmApiRequest(
            quantumMachineId=machine_id,
            setDigitalInputPolarity=digital_input_polarity_request,
        )
        self._perform_qm_request(request)

    def get_io_values(self, machine_id: str) -> Tuple[compiler_pb2.QuaValues, ...]:
        request = frontend_pb2.QmDataRequest(
            io_value_Request=[
                frontend_pb2.IOValueRequest(io_number=1, quantumMachineId=machine_id),
                frontend_pb2.IOValueRequest(io_number=2, quantumMachineId=machine_id),
            ]
        )
        response = self._run(self._stub.RequestData, request, timeout=self._timeout)

        if not response.success:
            raise QMRequestDataError("\n".join(err.message for err in response.errors))

        return tuple(resp.values for resp in response.io_value_response)
