import logging
from typing import List, Type, Tuple, Optional, cast

from betterproto.lib.google.protobuf import Empty

import qm.grpc.qm_api
from qm.type_hinting import Value
from qm.grpc.qua import QuaProgram
from qm.api.base_api import BaseApi
from qm.grpc.compiler import QuaValues
from qm.grpc.general_messages import Matrix
from qm.api.models.jobs import InsertDirection
from qm.utils.protobuf_utils import LOG_LEVEL_MAP
from qm.api.models.capabilities import OPX_FEM_IDX
from qm.api.models.quantum_machine import QuantumMachineData
from qm.api.models.devices import Polarity, MixerInfo, AnalogOutputPortFilter
from qm.grpc.qua_config import QuaConfig, QuaConfigFemTypes, QuaConfigDeviceDec
from qm.api.models.compiler import CompilerOptionArguments, get_request_compiler_options
from qm.grpc.qm_manager import (
    Controller,
    GetQuantumMachineRequest,
    OpenQuantumMachineRequest,
    CloseQuantumMachineRequest,
)
from qm.grpc.frontend import (
    FrontendStub,
    QmDataRequest,
    QueuePosition,
    CompileRequest,
    IoValueRequest,
    AddToQueueRequest,
    ExecutionOverrides,
    AddCompiledToQueueRequest,
    ResetDataProcessingRequest,
    PerformHalDebugCommandRequest,
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
from qm.grpc.qm_api import (
    DigitalInputPort,
    HighQmApiRequest,
    HighQmApiRequestQePort,
    HighQmApiRequestSetIoValues,
    HighQmApiRequestSetFrequency,
    HighQmApiRequestSetCorrection,
    HighQmApiRequestIoValueSetData,
    HighQmApiRequestSetDigitalRoute,
    HighQmApiRequestSetInputDcOffset,
    HighQmApiRequestSetOutputDcOffset,
    HighQmApiRequestSetOutputFilterTaps,
    HighQmApiRequestAnalogOutputPortFilter,
    HighQmApiRequestSetCorrectionMixerInfo,
    HighQmApiRequestSetDigitalInputDeadtime,
    HighQmApiRequestSetDigitalInputPolarity,
    HighQmApiRequestSetDigitalInputThreshold,
)

logger = logging.getLogger(__name__)


class FrontendApi(BaseApi[FrontendStub]):
    @property
    def _stub_class(self) -> Type[FrontendStub]:
        return FrontendStub

    def get_version(self) -> str:
        response = self._run(self._stub.get_version(Empty(), timeout=self._timeout))
        return response.value

    def healthcheck(self, strict: bool) -> None:
        logger.info("Performing health check")
        response = self._run(self._stub.health_check(Empty(), timeout=self._timeout))

        for warning in response.warning_messages:
            logger.warning(f"Health check warning: {warning}")

        for message in response.message:
            logger.debug(message)

        if not response.ok:
            logger.error(f"Health check error: {response.message}")

            for error in response.error_messages:
                logger.error(f"Health check error: {error}")

            if strict:
                raise QMHealthCheckError("Health check failed")
            return

        logger.info("Health check passed")

    def reset_data_processing(self) -> None:
        self._run(self._stub.reset_data_processing(ResetDataProcessingRequest(), timeout=self._timeout))

    def open_qm(self, config: QuaConfig, close_other_machines: bool, keep_dc_offsets_when_closing: bool = False) -> str:
        request = OpenQuantumMachineRequest(config=config, keep_dc_offsets_when_closing=keep_dc_offsets_when_closing)

        if close_other_machines:
            request.always = True
        else:
            request.never = True

        response = self._run(self._stub.open_quantum_machine(request, timeout=self._timeout))

        if not response.success:
            open_qm_exception = OpenQmException(response.config_validation_errors, response.physical_validation_errors)

            for formatted_error in (
                open_qm_exception.physical_validation_formatted_errors
                + open_qm_exception.config_validation_formatted_errors
            ):
                logger.error(formatted_error)

            raise open_qm_exception

        for warning in response.open_qm_warnings:
            logger.warning(f"Open QM ended with warning {warning.code}: {warning.message}")

        return response.machine_id

    def list_open_quantum_machines(self) -> List[str]:
        response = self._run(self._stub.list_open_quantum_machines(Empty(), timeout=self._timeout))
        return response.machine_i_ds

    def get_quantum_machine(self, qm_id: str) -> QuantumMachineData:
        request = GetQuantumMachineRequest(machine_id=qm_id)
        response = self._run(self._stub.get_quantum_machine(request, timeout=self._timeout))

        if not response.success:
            error_message = "\n".join([error.message for error in response.errors])
            raise QMFailedToGetQuantumMachineError(f"Failed to fetch quantum machine: {error_message}")

        return QuantumMachineData(machine_id=response.machine_id, config=response.config)

    def close_quantum_machine(self, machine_id: str) -> bool:
        request = CloseQuantumMachineRequest(machine_id=machine_id)
        response = self._run(self._stub.close_quantum_machine(request, timeout=self._timeout))
        if not response.success:
            raise QmFailedToCloseQuantumMachineError("\n".join(err.message for err in response.errors))
        return True

    def get_quantum_machine_config(self, machine_id: str) -> QuaConfig:
        machine_data = self.get_quantum_machine(machine_id)
        config = machine_data.config

        # TODO - this is a patch to make the tests work, once we move to the new GRPC messages,
        #  we will need to check it for backwards compatibility.
        if not config.v1_beta.control_devices:
            for controller_name, controller in config.v1_beta.controllers.items():
                config.v1_beta.control_devices[controller_name] = QuaConfigDeviceDec(
                    fems={OPX_FEM_IDX: QuaConfigFemTypes(opx=controller)}
                )
        return machine_data.config

    def close_all_quantum_machines(self) -> None:
        response = self._run(self._stub.close_all_quantum_machines(Empty(), timeout=self._timeout))
        if not response.success:
            messages = [error.message for error in response.errors]
            for msg in messages:
                logger.error(msg)

            raise QMFailedToCloseAllQuantumMachinesError(
                "Can not close all quantum machines. See the following errors:\n" + "\n".join(messages),
            )

    def get_controllers(self) -> List[Controller]:
        response = self._run(self._stub.get_controllers(Empty(), timeout=self._timeout))
        return response.controllers

    def clear_all_job_results(self) -> None:
        self._run(self._stub.clear_all_job_results(Empty(), timeout=self._timeout))

    def send_debug_command(self, controller_name: str, command: str) -> str:
        request = PerformHalDebugCommandRequest(controller_name=controller_name, command=command)
        response = self._run(self._stub.perform_hal_debug_command(request, timeout=self._timeout))

        if not response.success:
            raise QMConnectionError(response.response)
        return response.response

    def add_to_queue(
        self,
        machine_id: str,
        program: QuaProgram,
        compiler_options: CompilerOptionArguments,
        insert_direction: InsertDirection,
    ) -> str:
        queue_position = QueuePosition()
        if insert_direction == InsertDirection.start:
            queue_position.start = Empty()
        elif insert_direction == InsertDirection.end:
            queue_position.end = Empty()

        program.compiler_options = get_request_compiler_options(compiler_options)

        request = AddToQueueRequest(
            quantum_machine_id=machine_id,
            high_level_program=program,
            queue_position=queue_position,
        )

        logger.info("Sending program to QOP for compilation")

        response = self._run(self._stub.add_to_queue(request, timeout=None))

        for message in response.messages:
            logger.log(LOG_LEVEL_MAP[message.level], message.message)

        job_id = response.job_id
        if not response.ok:
            logger.error(f"Job {job_id} failed. Failed to execute program.")
            raise FailedToAddJobToQueueException(f"Job {job_id} failed. Failed to execute program.")

        return job_id

    def add_compiled_to_queue(self, machine_id: str, program_id: str, execution_overrides: ExecutionOverrides) -> str:
        queue_position = QueuePosition()
        queue_position.end = Empty()

        request = AddCompiledToQueueRequest(
            quantum_machine_id=machine_id,
            program_id=program_id,
            queue_position=queue_position,
            execution_overrides=execution_overrides,
        )

        response = self._run(self._stub.add_compiled_to_queue(request, timeout=self._timeout))

        job_id = response.job_id

        for err in response.errors:
            logger.error(err.message)

        if not response.ok:
            logger.error(f"Job {job_id} failed. Failed to execute program.")
            raise FailedToAddJobToQueueException(f"Job {job_id} failed. Failed to execute program.")

        return job_id

    def compile(
        self,
        machine_id: str,
        program: QuaProgram,
        compiler_options: CompilerOptionArguments,
    ) -> str:
        program.compiler_options = get_request_compiler_options(compiler_options)
        request = CompileRequest(quantum_machine_id=machine_id, high_level_program=program)

        response = self._run(self._stub.compile(request, timeout=None))

        for message in response.messages:
            logger.log(LOG_LEVEL_MAP[message.level], message.message)

        program_id = response.program_id
        if not response.ok:
            logger.error(f"Compilation of program {program_id} failed")
            raise CompilationException(f"Compilation of program {program_id} failed")
        return program_id

    def _perform_qm_request(self, request: HighQmApiRequest) -> None:
        response = self._run(self._stub.perform_qm_request(request, timeout=self._timeout))

        if not response.ok:
            error_message = "\n".join(it.message for it in response.errors)
            logger.error(f"Failed: {error_message}")
            raise QMRequestError(f"Failed: {error_message}")

    def set_correction(self, machine_id: str, mixer: MixerInfo, correction: Matrix) -> None:
        correction_request = HighQmApiRequestSetCorrection(
            mixer=HighQmApiRequestSetCorrectionMixerInfo(
                mixer=mixer.mixer,
                frequency_negative=mixer.frequency_negative,
                intermediate_frequency=mixer.intermediate_frequency,
                intermediate_frequency_double=mixer.intermediate_frequency_double,
                lo_frequency=mixer.lo_frequency,
                lo_frequency_double=mixer.lo_frequency_double,
            ),
            correction=cast(qm.grpc.qm_api.Matrix, correction),  # For some reason we have two matrix messages,
            # although they are the same...
        )
        request = HighQmApiRequest(quantum_machine_id=machine_id, set_correction=correction_request)
        self._perform_qm_request(request)

    def set_intermediate_frequency(self, machine_id: str, element: str, value: float) -> None:
        set_frequency_request = HighQmApiRequestSetFrequency(qe=element, value=value)
        request = HighQmApiRequest(quantum_machine_id=machine_id, set_frequency=set_frequency_request)
        self._perform_qm_request(request)

    def set_output_dc_offset(self, machine_id: str, element: str, element_port: str, offset: float) -> None:
        output_dc_offset_request = HighQmApiRequestSetOutputDcOffset(
            qe=HighQmApiRequestQePort(qe=element, port=element_port), i=offset, q=offset
        )
        request = HighQmApiRequest(quantum_machine_id=machine_id, set_output_dc_offset=output_dc_offset_request)
        self._perform_qm_request(request)

    def set_output_filter_taps(
        self,
        machine_id: str,
        element: str,
        element_port: str,
        filter_port: AnalogOutputPortFilter,
    ) -> None:
        output_filter_tap_request = HighQmApiRequestSetOutputFilterTaps(
            qe=HighQmApiRequestQePort(qe=element, port=element_port),
            filter=HighQmApiRequestAnalogOutputPortFilter(
                feedback=filter_port.feedback, feedforward=filter_port.feedforward
            ),
        )
        request = HighQmApiRequest(
            quantum_machine_id=machine_id,
            set_output_filter_taps=output_filter_tap_request,
        )
        self._perform_qm_request(request)

    def set_input_dc_offset(self, machine_id: str, element: str, element_port: str, offset: float) -> None:
        input_dc_offset_request = HighQmApiRequestSetInputDcOffset(
            qe=HighQmApiRequestQePort(qe=element, port=element_port), offset=offset
        )
        request = HighQmApiRequest(quantum_machine_id=machine_id, set_input_dc_offset=input_dc_offset_request)
        self._perform_qm_request(request)

    def set_output_digital_delay(self, machine_id: str, element: str, element_port: str, delay: int) -> None:
        digital_delay_request = HighQmApiRequestSetDigitalRoute(
            delay=HighQmApiRequestQePort(qe=element, port=element_port), value=delay
        )
        request = HighQmApiRequest(quantum_machine_id=machine_id, set_digital_route=digital_delay_request)
        self._perform_qm_request(request)

    def set_output_digital_buffer(self, machine_id: str, element: str, element_port: str, buffer: int) -> None:
        digital_buffer_request = HighQmApiRequestSetDigitalRoute(
            buffer=HighQmApiRequestQePort(qe=element, port=element_port), value=buffer
        )
        request = HighQmApiRequest(quantum_machine_id=machine_id, set_digital_route=digital_buffer_request)
        self._perform_qm_request(request)

    def set_io_values(self, machine_id: str, values: List[Optional[Value]]) -> None:
        type_to_value_mapping = {
            int: "int_value",
            float: "double_value",
            bool: "boolean_value",
        }

        set_data = []
        for index, value in enumerate(values):
            if value is not None:
                set_data_request = HighQmApiRequestIoValueSetData(io_number=index + 1)
                setattr(set_data_request, type_to_value_mapping[type(value)], value)
                set_data.append(set_data_request)

        set_io_values = HighQmApiRequestSetIoValues(all=True, io_value_set_data=set_data)
        request = HighQmApiRequest(quantum_machine_id=machine_id, set_io_values=set_io_values)
        self._perform_qm_request(request)

    def set_digital_input_threshold(
        self, machine_id: str, controller_name: str, fem_number: int, port_number: int, threshold: float
    ) -> None:
        digital_input_threshold_request = HighQmApiRequestSetDigitalInputThreshold(
            digital_port=DigitalInputPort(
                controller_name=controller_name, fem_number=fem_number, port_number=port_number
            ),
            threshold=threshold,
        )
        request = HighQmApiRequest(
            quantum_machine_id=machine_id,
            set_digital_input_threshold=digital_input_threshold_request,
        )
        self._perform_qm_request(request)

    def set_digital_input_dead_time(
        self, machine_id: str, controller_name: str, fem_number: int, port_number: int, dead_time: int
    ) -> None:
        digital_input_dead_time_request = HighQmApiRequestSetDigitalInputDeadtime(
            digital_port=DigitalInputPort(
                controller_name=controller_name, fem_number=fem_number, port_number=port_number
            ),
            deadtime=dead_time,
        )
        request = HighQmApiRequest(
            quantum_machine_id=machine_id,
            set_digital_input_deadtime=digital_input_dead_time_request,
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
        digital_input_polarity_request = HighQmApiRequestSetDigitalInputPolarity(
            digital_port=DigitalInputPort(
                controller_name=controller_name, fem_number=fem_number, port_number=port_number
            ),
            polarity=polarity.value,  # type: ignore[arg-type]
        )
        request = HighQmApiRequest(
            quantum_machine_id=machine_id,
            set_digital_input_polarity=digital_input_polarity_request,
        )
        self._perform_qm_request(request)

    def get_io_values(self, machine_id: str) -> Tuple[QuaValues, ...]:
        request = QmDataRequest(
            io_value_request=[
                IoValueRequest(io_number=1, quantum_machine_id=machine_id),
                IoValueRequest(io_number=2, quantum_machine_id=machine_id),
            ]
        )
        response = self._run(self._stub.request_data(request, timeout=self._timeout))

        if not response.success:
            raise QMRequestDataError("\n".join(err.message for err in response.errors))

        return tuple(resp.values for resp in response.io_value_response)
