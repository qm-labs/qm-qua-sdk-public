import json
import logging
import warnings
from typing import Dict, List, Tuple, Union, Literal, Optional, Sequence, cast, overload

from qm.api.v2.job_api import JobApi
from qm.octave import QmOctaveConfig
from qm.program.program import Program
from qm.utils import deprecation_message
from qm.exceptions import FunctionInputError
from qm.octave.octave_manager import OctaveManager
from qm.simulate.interface import SimulationConfig
from qm.api.models.capabilities import ServerCapabilities
from qm.api.models.server_details import ConnectionDetails
from qm.api.v2.qm_api import QmApi, IoValue, NoRunningQmJob
from qm.api.v2.job_api.job_api import JobApiWithDeprecations
from qm.type_hinting import Value, Number, NumpySupportedValue
from qm.type_hinting.general import PathLike, NumpySupportedFloat
from qm.jobs.job_queue_with_deprecations import QmQueueWithDeprecations
from qm.api.v2.job_api.simulated_job_api import SimulatedJobApiWithDeprecations
from qm.api.models.compiler import CompilerOptionArguments, standardize_compiler_params
from qm.type_hinting.config_types import FEM_IDX, FullQuaConfig, LogicalQuaConfig, ControllerQuaConfig
from qm.utils.config_utils import (
    get_fem_config,
    get_logical_pb_config,
    element_has_mix_inputs,
    get_controller_pb_config,
)
from qm.grpc.qua_config import (
    QuaConfig,
    QuaConfigElementDec,
    QuaConfigQuaConfigV1,
    QuaConfigMicrowaveFemDec,
    QuaConfigAdcPortReference,
    QuaConfigDacPortReference,
)

logger = logging.getLogger(__name__)


class QmApiWithDeprecations(QmApi):
    SIMULATED_JOB_CLASS = SimulatedJobApiWithDeprecations

    def __init__(
        self,
        connection_details: ConnectionDetails,
        qm_id: str,
        capabilities: ServerCapabilities,
        octave_config: Optional[QmOctaveConfig],
        octave_manager: OctaveManager,
        pb_config: Optional[QuaConfig] = None,
    ):
        super().__init__(connection_details, qm_id, capabilities, octave_config, octave_manager, pb_config)
        self._queue = QmQueueWithDeprecations(api=self, capabilities=self._caps)

    def _get_job(self, job_id: str) -> JobApiWithDeprecations:
        return JobApiWithDeprecations(self.connection_details, job_id, capabilities=self._caps)

    def get_job_by_id(self, job_id: str) -> JobApiWithDeprecations:
        """
        Deprecated - This method is going to be removed, please use `qmm.get_job()`.

        Returns the job object for the given id.
        Args:
            job_id: The job id
        Returns:
             The job object
        """
        warnings.warn(
            deprecation_message(
                method="qm.get_job_by_id",
                deprecated_in="1.2.0",
                removed_in="1.4.0",
                details="This method is going to be removed, please use `qmm.get_job()`.",
            ),
            DeprecationWarning,
            stacklevel=1,
        )
        # The cast is needed to tell mypy (and pycharm) that the return type is JobApiWithDeprecations. Mypy thinks
        # the return type is JobApi because "get_job()" returns JobApi, even though the method "_get_job()" is
        # overridden in this class to return JobApiWithDeprecations.
        job = cast(JobApiWithDeprecations, self.get_job(job_id))
        return job

    @property
    def queue(self) -> QmQueueWithDeprecations:
        warnings.warn(
            deprecation_message(
                method="qm.queue",
                deprecated_in="1.2.0",
                removed_in="1.4.0",
                details="This property is going to be removed, all functionality will exist directly under "
                "`QuantumMachine`. For example, instead of `qm.queue.add(prog)` use `qm.add_to_queue(prog)`.",
            ),
            DeprecationWarning,
            stacklevel=1,
        )
        return self._queue

    def close(self) -> bool:  # type: ignore[override]
        """Closes the quantum machine.

        Returns:
             `True` if the close request succeeded.
        """
        super().close()
        return True

    def execute(  # type: ignore[override]
        self,
        program: Program,
        duration_limit: None = None,
        data_limit: None = None,
        force_execution: None = None,
        dry_run: None = None,
        simulate: Optional[SimulationConfig] = None,
        *,
        config: Optional[Union[FullQuaConfig, LogicalQuaConfig]] = None,
        compiler_options: Optional[CompilerOptionArguments] = None,
        strict: Optional[bool] = None,
        flags: Optional[List[str]] = None,
    ) -> JobApi:
        """Executes a program and returns a job object to keep track of execution and get
        results.

        Note:

            Calling execute will halt any currently running program and clear the current
            queue. If you want to add a job to the queue, use qm.queue.add()

        Args:
            program: A QUA ``program()`` object to execute
            duration_limit: This parameter is ignored and will be removed in future versions
            data_limit: This parameter is ignored and will be removed in future versions
            force_execution: This parameter is ignored and will be removed in future versions
            dry_run: This parameter is ignored and will be removed in future versions
            simulate: If given, will be simulated instead of executed.
            config:  -- Available from QOP 3.5 --
                The configuration used with the program. The logical config is required if it was not supplied to the `QuantumMachine`.
                A full configuration (containing both logical and controller configs), can be used to override the default `QuantumMachine` settings.
            compiler_options: Optional arguments for compilation.
            strict: This parameter is deprecated, please use `compiler_options`
            flags: This parameter is deprecated, please use `compiler_options`
        Returns:
            A ``QmJob`` object (see Job API).
        """
        if not isinstance(program, Program):
            raise Exception("program argument must be of type qm.program.Program")

        self._caps.validate(program.used_capabilities)

        if config:
            self._validate_capability_for_config_param(self.execute.__name__)

        for x, name in [
            (duration_limit, "`duration_limit'"),
            (data_limit, "`data_limit'"),
            (force_execution, "`force_execution'"),
            (dry_run, "`dry_run'"),
        ]:
            if x is not None:
                warnings.warn(
                    deprecation_message(
                        method=f"The argument {name}",
                        deprecated_in="1.2.0",
                        removed_in="1.4.0",
                    ),
                )

        compiler_options = standardize_compiler_params(compiler_options, strict, flags)

        if simulate is not None:
            warnings.warn(
                deprecation_message(
                    method="The argument simulate",
                    deprecated_in="1.2.0",
                    removed_in="1.4.0",
                    details="The simulate argument is deprecated, please use the simulate method.",
                ),
            )
            return self.simulate(program, simulate, compiler_options=compiler_options)

        logger.info("Clearing queue")
        self.clear_queue()
        current_running_job = self._get_running_job()
        if current_running_job is not None:
            logger.info(f"Cancelling currently running job - {current_running_job.id}")
            current_running_job.cancel()

        new_job_api = self.add_to_queue(program, config=config, compiler_options=compiler_options)
        new_job_api.wait_until({"Running"}, timeout=5 * 60)
        # The timeout here is just for the backwards compatibility behaviour.
        # See that in the father function there is no `wait_until`
        return new_job_api

    def list_controllers(self) -> Tuple[str, ...]:
        """
        Deprecated - This method is going to be removed, please use `qm.get_config()`.

        Gets a list with the defined controllers in this qm

        Returns:
            The names of the controllers configured in this qm
        """
        warnings.warn(
            deprecation_message(
                method="qm.list_controllers",
                deprecated_in="1.2.0",
                removed_in="1.4.0",
                details="This method is going to be removed, please get data from `qm.get_config()`.",
            ),
            DeprecationWarning,
            stacklevel=1,
        )
        controller_config = get_controller_pb_config(self._get_pb_config())
        # This if statement is not necessary, but helps mypy understand that we are trying to access the controllers
        # attribute only if the controller_config is of type QuaConfigQuaConfigV1 (which still has the deprecated
        # controllers attribute).
        if isinstance(controller_config, QuaConfigQuaConfigV1):
            return tuple(controller_config.control_devices) or tuple(controller_config.controllers)

        return tuple(controller_config.control_devices)

    def set_mixer_correction(
        self,
        mixer: str,
        intermediate_frequency: Number,
        lo_frequency: Number,
        values: Tuple[float, float, float, float],
    ) -> None:
        """Deprecated - This method is going to be removed, please use `job.set_element_correction()`.

        Sets the correction matrix for correcting gain and phase imbalances
        of an IQ mixer for the supplied intermediate frequency and LO frequency.

        Args:
            mixer (str): the name of the mixer, as defined in the
                configuration
            intermediate_frequency (Union[int|float]): the intermediate
                frequency for which to apply the correction matrix
            lo_frequency (int): the LO frequency for which to apply the
                correction matrix
            values (tuple):

                tuple is of the form (v00, v01, v10, v11) where
                the matrix is
                | v00 v01 |
                | v10 v11 |

        Note:

            Currently, the OPX does not support multiple mixer calibration entries.
            This function will accept IF & LO frequencies written in the config file,
            and will update the correction matrix for all the elements with the given
            mixer/frequencies combination when the program started.

            It’s not recommended to use this method while a job is running.
            To change the calibration values for a running job,
            use job.set_element_correction
        """
        warnings.warn(
            deprecation_message(
                method="qm.set_mixer_correction",
                deprecated_in="1.2.0",
                removed_in="1.4.0",
                details="This method is going to be removed, please use `job.set_element_correction()`.",
            ),
            DeprecationWarning,
            stacklevel=1,
        )
        config: ControllerQuaConfig = {
            "mixers": {
                mixer: [
                    {
                        "correction": values,
                        "intermediate_frequency": intermediate_frequency,
                        "lo_frequency": lo_frequency,
                    }
                ]
            },
        }
        self.update_config(config)
        job = self._get_running_job()
        if job is not None:
            for name, element_config in self._get_elements_pb_config().items():
                if not element_has_mix_inputs(element_config):
                    continue
                mixer_cond = element_config.mix_inputs.mixer == mixer
                if_cond = element_config.intermediate_frequency == intermediate_frequency
                lo_cond = element_config.mix_inputs.lo_frequency == lo_frequency
                if mixer_cond and if_cond and lo_cond:
                    job.set_element_correction(name, values)

    def set_intermediate_frequency(self, element: str, freq: float) -> None:
        """
        Deprecated - This method is going to be moved to the job API, please use `job.set_intermediate_frequency()`.

        Sets the intermediate frequency of the element

        Args:
            element (str): the name of the element whose intermediate
                frequency will be updated
            freq (float): the intermediate frequency to set to the given
                element
        """
        warnings.warn(
            deprecation_message(
                method="qm.set_intermediate_frequency",
                deprecated_in="1.2.0",
                removed_in="1.4.0",
                details="This method is going to be moved to the job API, please use "
                "`job.set_intermediate_frequency()`.",
            ),
            DeprecationWarning,
            stacklevel=1,
        )
        job = self._strict_get_running_job()
        job.set_intermediate_frequency(element, freq)

    def get_intermediate_frequency(self, element: str) -> float:
        """
        Deprecated - This method is going to be moved to the job API, please use `job.get_intermediate_frequency()`.

        Gets the intermediate frequency of the element

        Args:
            element (str): the name of the element whose intermediate
                frequency will be updated

        Returns:
            The intermediate frequency
        """
        warnings.warn(
            deprecation_message(
                method="qm.get_intermediate_frequency",
                deprecated_in="1.2.0",
                removed_in="1.4.0",
                details="This method is going to be moved to the job API, please use "
                "`job.get_intermediate_frequency()`.",
            ),
            DeprecationWarning,
            stacklevel=1,
        )
        job = self._strict_get_running_job()
        return job.get_intermediate_frequency(element)

    def get_output_dc_offset_by_element(
        self, element: str, iq_input: Optional[Literal["I", "Q", "single"]] = None
    ) -> float:
        """Deprecated - This method is going to be removed, please get idle value from `qm.get_config()`
            or current value from job `job.get_output_dc_offset_by_element()`

        Get the current DC offset of the OPX analog output channel associated with an element.

        Args:
            element: the name of the element to get the correction for
            iq_input: the port name as appears in the element config.
                Options:

                `'single'`
                    for an element with a single input

                `'I'` or `'Q'`
                    for an element with mixer inputs

        Returns:
            the offset, in volts
        """
        warnings.warn(
            deprecation_message(
                method="qm.get_output_dc_offset_by_element",
                deprecated_in="1.2.0",
                removed_in="1.4.0",
                details="This method is going to be removed, please get idle value from `qm.get_config()`"
                " or current value from job `job.get_output_dc_offset_by_element()`",
            ),
            DeprecationWarning,
            stacklevel=1,
        )
        job = self._strict_get_running_job()
        return job.get_output_dc_offset_by_element(element, iq_input)

    @overload
    def set_output_dc_offset_by_element(self, element: str, input: Literal["single", "I", "Q"], offset: float) -> None:
        pass

    @overload
    def set_output_dc_offset_by_element(
        self,
        element: str,
        input: Tuple[Literal["I", "Q"], Literal["I", "Q"]],
        offset: Union[Tuple[float, float], List[float]],
    ) -> None:
        pass

    def set_output_dc_offset_by_element(
        self,
        element: str,
        input: Union[Literal["single", "I", "Q"], Tuple[Literal["I", "Q"], Literal["I", "Q"]], List[Literal["I", "Q"]]],
        offset: Union[float, Tuple[float, float], List[float]],
    ) -> None:
        """Deprecated - This method is going to be removed, please set idle value with `qm.update_config()` or current
            value from job `job.set_output_dc_offset_by_element()`

        Set the current DC offset of the OPX analog output channel associated with an element.

        Args:
            element (str): the name of the element to update the
                correction for
            input (Union[str, Tuple[str,str], List[str]]): the input
                name as appears in the element config. Options:

                `'single'`
                    for an element with a single input

                `'I'` or `'Q'` or a tuple ('I', 'Q')
                    for an element with mixer inputs
            offset (Union[float, Tuple[float,float], List[float]]): The
                dc value to set to, in volts.

        Examples:
            ```python
            qm.set_output_dc_offset_by_element('flux', 'single', 0.1)
            qm.set_output_dc_offset_by_element('qubit', 'I', -0.01)
            qm.set_output_dc_offset_by_element('qubit', ('I', 'Q'), (-0.01, 0.05))
            ```

        Note:

            If the sum of the DC offset and the largest waveform data-point exceed the range,
            DAC output overflow will occur and the output will be corrupted.
        """
        warnings.warn(
            deprecation_message(
                method="qm.set_output_dc_offset_by_element",
                deprecated_in="1.2.0",
                removed_in="1.4.0",
                details="This method is going to be removed, please set idle value with `qm.update_config()`"
                " or current value from job `job.set_output_dc_offset_by_element()`",
            ),
            DeprecationWarning,
            stacklevel=1,
        )
        if isinstance(input, str):
            if not isinstance(offset, (int, float)):
                raise FunctionInputError(f"Input should be int or float, got {type(offset)}")
            if input in {"I", "Q"}:
                ports = self._get_input_ports_from_mixed_input_element(element)
                port = ports[0] if input == "I" else ports[1]
            else:
                port = self._get_input_port_from_single_input_element(element)
            config = self._create_config_for_output_dc_offset_setting(port, offset)
            self.update_config(config)
            job = self._get_running_job()
            if job is not None:
                job.set_output_dc_offset_by_element(element, input, offset)
        elif isinstance(input, (list, tuple)):
            if not set(input) <= {"I", "Q"}:
                raise FunctionInputError(f"Input names should be 'I' or 'Q', got {input}")
            if not (isinstance(offset, (list, tuple)) and len(input) == len(offset)):
                raise FunctionInputError(
                    f"input should be two iterables of the same size," f"got input = {input} and offset = {offset}"
                )
            ports = self._get_input_ports_from_mixed_input_element(element)
            for _input, _offset in zip(input, offset):
                _port = ports[0] if _input == "I" else ports[1]
                config = self._create_config_for_output_dc_offset_setting(_port, _offset)
                self.update_config(config)
            job = self._get_running_job()
            if job is not None:
                job.set_output_dc_offset_by_element(element, input, offset)
        else:
            raise FunctionInputError(f"Input should be str or tuple, got {type(input)}")

    def set_output_filter_by_element(
        self,
        element: str,
        input: str,
        feedforward: Optional[Sequence[NumpySupportedFloat]],
        feedback: Optional[Sequence[NumpySupportedFloat]],
    ) -> None:
        raise NotImplementedError

    def set_input_dc_offset_by_element(self, element: str, output: str, offset: float) -> None:
        """Deprecated - This method is going to be moved to the job API, please use job.set_input_dc_offset_by_element()`

        Set the current DC offset of the OPX analog input channel associated with an element.

        Args:
            element (str): the name of the element to update the
                correction for
            output (str): the output key name as appears in the element
                config under 'outputs'.
            offset (float): the dc value to set to, in volts. Ranges from -0.5 to 0.5 - 2^-16 in steps of
                2^-16.

        Note:
            If the sum of the DC offset and the largest waveform data-point exceed the range,
            DAC output overflow will occur and the output will be corrupted.
        """
        warnings.warn(
            deprecation_message(
                method="qm.set_input_dc_offset_by_element",
                deprecated_in="1.2.0",
                removed_in="1.4.0",
                details="This method is going to be moved to the job API, please use "
                "`job.set_input_dc_offset_by_element()`.",
            ),
            DeprecationWarning,
            stacklevel=1,
        )
        port = self._get_output_port_from_element(element, output)
        config = self._create_config_for_input_dc_offset_setting(port, offset)
        self.update_config(config)

        job = self._get_running_job()
        if job is not None:
            job.set_input_dc_offset_by_element(element, output, offset)

    def get_input_dc_offset_by_element(self, element: str, output: str) -> float:
        """Deprecated - This method is going to be removed, please get the value from `qm.get_config()`.

        Get the current DC offset of the OPX analog input channel associated with an element.

        Args:
            element: the name of the element to get the correction for
            output: the output key name as appears in the element config
                under 'outputs'.

        Returns:
            The offset, in volts
        """
        warnings.warn(
            deprecation_message(
                method="qm.get_input_dc_offset_by_element",
                deprecated_in="1.2.0",
                removed_in="1.4.0",
                details="This method is going to be removed, please get the value from `qm.get_config()`.",
            ),
            DeprecationWarning,
            stacklevel=1,
        )
        config = self._get_pb_config()
        port = self._get_output_port_from_element(element, output)
        fem_config = get_fem_config(config, port)
        if isinstance(fem_config, QuaConfigMicrowaveFemDec):
            raise ValueError(f"Element {element} does not support dc offset.")

        offset = fem_config.analog_inputs[port.number].offset
        assert offset is not None  # Mypy thinks it can be None, but it can't really (offset has a default value)
        return offset

    def get_digital_delay(self, element: str, digital_input: str) -> int:
        """Deprecated - This method is going to be moved to the job API, please use `job.get_output_digital_delay()`.

        Gets the delay of the digital input of the element

        Args:
            element: The name of the element to get the delay for
            digital_input: The digital input name as appears in the
                element's config

        Returns:
            The delay
        """
        warnings.warn(
            deprecation_message(
                method="qm.get_digital_delay",
                deprecated_in="1.2.0",
                removed_in="1.4.0",
                details="This method is going to be moved to the job API, please use "
                "`job.get_output_digital_delay()`.",
            ),
            DeprecationWarning,
            stacklevel=1,
        )
        job = self._strict_get_running_job()
        return job.get_output_digital_delay(element, digital_input)

    def set_digital_delay(self, element: str, digital_input: str, delay: int) -> None:
        """Deprecated - This method is going to be moved to the job API, please use `job.set_output_digital_delay()`.

        Sets the delay of the digital input of the element

        Args:
            element (str): The name of the element to update delay for
            digital_input (str): The digital input name as appears in
                the element's config
            delay (int): The delay value to set to, in ns.
        """
        warnings.warn(
            deprecation_message(
                method="qm.set_digital_delay",
                deprecated_in="1.2.0",
                removed_in="1.4.0",
                details="This method is going to be moved to the job API, please use "
                "`job.set_output_digital_delay()`.",
            ),
            DeprecationWarning,
            stacklevel=1,
        )
        job = self._strict_get_running_job()
        job.set_output_digital_delay(element, digital_input, delay)

    def get_digital_buffer(self, element: str, digital_input: str) -> int:
        """Deprecated - This method is going to be moved to the job API, please use `job.get_output_digital_buffer()`.

        Gets the buffer for digital input of the element

        Args:
            element (str): The name of the element to get the buffer for
            digital_input (str): The digital input name as appears in
                the element's config

        Returns:
            The buffer
        """
        warnings.warn(
            deprecation_message(
                method="qm.get_digital_buffer",
                deprecated_in="1.2.0",
                removed_in="1.4.0",
                details="This method is going to be moved to the job API, please use "
                "`job.get_output_digital_buffer()`.",
            ),
            DeprecationWarning,
            stacklevel=1,
        )
        job = self._strict_get_running_job()
        return job.get_output_digital_buffer(element, digital_input)

    def set_digital_buffer(self, element: str, digital_input: str, buffer: int) -> None:
        """Deprecated - This method is going to be moved to the job API, please use `job.set_output_digital_buffer()`.

        Sets the buffer for digital input of the element

        Args:
            element (str): The name of the element to update buffer for
            digital_input (str): the digital input name as appears in
                the element's config
            buffer (int): The buffer value to set to, in ns.
        """
        warnings.warn(
            deprecation_message(
                method="qm.set_digital_buffer",
                deprecated_in="1.2.0",
                removed_in="1.4.0",
                details="This method is going to be moved to the job API, please use "
                "`job.set_output_digital_buffer()`.",
            ),
            DeprecationWarning,
            stacklevel=1,
        )
        job = self._strict_get_running_job()
        job.set_output_digital_buffer(element, digital_input, buffer)

    def get_time_of_flight(self, element: str) -> int:
        """Deprecated - This method is going to be removed, please get the value from `qm.get_config()`.

        Gets the *time of flight*, associated with a measurement element.

        This is the amount of time between the beginning of a measurement pulse applied to element
        and the time that the data is available to the controller for demodulation or streaming.

        Args:
            element (str): The name of the element to get time of flight
                for

        Returns:
            The time of flight, in ns
        """
        warnings.warn(
            deprecation_message(
                method="qm.get_time_of_flight",
                deprecated_in="1.2.0",
                removed_in="1.4.0",
                details="This method is going to be removed, please get the value from `qm.get_config()`.",
            ),
            DeprecationWarning,
            stacklevel=1,
        )
        tof = self._get_elements_pb_config()[element].time_of_flight
        if tof is None:
            raise ValueError(f"Time of flight for element {element} is not set")
        return tof

    def get_smearing(self, element: str) -> int:
        """Deprecated - This method is going to be removed, please get the value from `qm.get_config()`.

        Gets the *smearing* associated with a measurement element.

        This is a broadening of the raw results acquisition window, to account for dispersive broadening
        in the measurement elements (readout resonators etc.) The acquisition window will be broadened
        by this amount on both sides.

        Args:
            element (str): The name of the element to get smearing for

        Returns:
            The smearing, in ns.
        """
        warnings.warn(
            deprecation_message(
                method="qm.get_smearing",
                deprecated_in="1.2.0",
                removed_in="1.4.0",
                details="This method is going to be removed, please get the value from `qm.get_config()`.",
            ),
            DeprecationWarning,
            stacklevel=1,
        )
        smearing = self._get_elements_pb_config()[element].smearing
        if smearing is None:
            raise ValueError(f"Smearing for element {element} is not set")
        return smearing

    @property
    def io1(self) -> IoValue:
        warnings.warn(
            deprecation_message(
                method="qm.io1",
                deprecated_in="1.2.0",
                removed_in="1.4.0",
                details="This property is going to be removed, please use `job.get_io_values()[0]`",
            ),
            DeprecationWarning,
            stacklevel=1,
        )
        return self.get_io1_value()

    @io1.setter
    def io1(self, value: Value) -> None:
        warnings.warn(
            deprecation_message(
                method="qm.io1",
                deprecated_in="1.2.0",
                removed_in="1.4.0",
                details="This property is going to be removed, please use `job.set_io_values(io1=value)`",
            ),
            DeprecationWarning,
            stacklevel=1,
        )
        self.set_io1_value(value)

    @property
    def io2(self) -> IoValue:
        warnings.warn(
            deprecation_message(
                method="qm.io2",
                deprecated_in="1.2.0",
                removed_in="1.4.0",
                details="This property is going to be removed, please use `job.get_io_values()[1]`",
            ),
            DeprecationWarning,
            stacklevel=1,
        )
        return self.get_io1_value()

    @io2.setter
    def io2(self, value: Value) -> None:
        warnings.warn(
            deprecation_message(
                method="qm.io2",
                deprecated_in="1.2.0",
                removed_in="1.4.0",
                details="This property is going to be removed, please use `job.set_io_values(io2=value)`",
            ),
            DeprecationWarning,
            stacklevel=1,
        )
        self.set_io2_value(value)

    def set_io1_value(self, value_1: Value) -> None:
        """Deprecated - This method is going to be moved to the job API, please use `job.set_io_values(io1=value)`

        Sets the values of ``IO1``

        This can be used later inside a QUA program as a QUA variable ``IO1``, ``IO2`` without declaration.
        The type of QUA variable is inferred from the python type passed to ``value_1``, ``value_2``,
        according to the following rule:

        int -> int
        float -> fixed
        bool -> bool

        Args:
            value_1: The value to be placed in ``IO1``
        """
        warnings.warn(
            deprecation_message(
                method="qm.set_io1_value",
                deprecated_in="1.2.0",
                removed_in="1.4.0",
                details="This method is going to be moved to the job API, please use `job.set_io_values(io1=value)`",
            ),
            DeprecationWarning,
            stacklevel=1,
        )
        self.set_io_values(value_1=value_1)

    def set_io2_value(self, value_2: Value) -> None:
        """Deprecated - This method is going to be moved to the job API, please use `job.set_io_values(io2=value)`

        Sets the values of ``IO2``

        This can be used later inside a QUA program as a QUA variable ``IO1``, ``IO2`` without declaration.
        The type of QUA variable is inferred from the python type passed to ``value_1``, ``value_2``,
        according to the following rule:

        int -> int
        float -> fixed
        bool -> bool

        Args:
            value_2: The value to be placed in ``IO2``
        """
        warnings.warn(
            deprecation_message(
                method="qm.set_io2_value",
                deprecated_in="1.2.0",
                removed_in="1.4.0",
                details="This method is going to be moved to the job API, please use `job.set_io_values(io2=value)`",
            ),
            DeprecationWarning,
            stacklevel=1,
        )
        self.set_io_values(value_2=value_2)

    def set_io_values(
        self,
        value_1: Optional[NumpySupportedValue] = None,
        value_2: Optional[NumpySupportedValue] = None,
    ) -> None:
        """Deprecated - This method is going to be moved to the job API, please use `job.set_io_values()`

        Sets the values of ``IO1`` & ``IO2`

        This can be used later inside a QUA program as a QUA variable ``IO1``, ``IO2`` without declaration.
        The type of QUA variable is inferred from the python type passed to ``value_1``, ``value_2``,
        according to the following rule:

        int -> int
        float -> fixed
        bool -> bool

        Args:
            value_1: The value to be placed in ``IO1``
            value_2: The value to be placed in ``IO2``
        """
        warnings.warn(
            deprecation_message(
                method="qm.set_io_values",
                deprecated_in="1.2.0",
                removed_in="1.4.0",
                details="This method is going to be moved to the job API, please use `job.set_io_values()`",
            ),
            DeprecationWarning,
            stacklevel=1,
        )
        if value_1 is None and value_2 is None:
            return

        job = self._strict_get_running_job()
        job.set_io_values(value_1, value_2)

    def get_io1_value(self) -> IoValue:
        """Deprecated - This method is going to be moved to the job API, please use `job.get_io_values()[0]`

        Gets the data stored in ``IO1``

        No inference is made on type.

        Returns:
            A dictionary with data stored in ``IO1``. (Data is in all
            three format: ``int``, ``float`` and ``bool``)
        """
        warnings.warn(
            deprecation_message(
                method="qm.get_io2_value",
                deprecated_in="1.2.0",
                removed_in="1.4.0",
                details="This method is going to be moved to the job API, please use `job.get_io_values()[0]`",
            ),
            DeprecationWarning,
            stacklevel=1,
        )
        return self.get_io_values()[0]

    def get_io2_value(self) -> IoValue:
        """Deprecated - This method is going to be moved to the job API, please use `job.get_io_values()[1]`

        Gets the data stored in ``IO2``

        No inference is made on type.

        Returns:
            A dictionary with data stored in ``IO2``. (Data is in all
            three format: ``int``, ``float`` and ``bool``)
        """
        warnings.warn(
            deprecation_message(
                method="qm.get_io2_value",
                deprecated_in="1.2.0",
                removed_in="1.4.0",
                details="This method is going to be moved to the job API, please use `job.get_io_values()[1]`",
            ),
            DeprecationWarning,
            stacklevel=1,
        )
        return self.get_io_values()[1]

    def get_io_values(self) -> List[IoValue]:
        """Deprecated - This method is going to be moved to the job API, please use `job.get_io_values()`

        Gets the data stored in ``IO1`` & ``IO2``

        No inference is made on type.

        Returns:
            A dictionary with data stored in ``IO1`` & ``IO2`` (Data is in all
            three format: ``int``, ``float`` and ``bool``)
        """
        warnings.warn(
            deprecation_message(
                method="qm.get_io_values",
                deprecated_in="1.2.0",
                removed_in="1.4.0",
                details="This method is going to be moved to the job API, please use `job.get_io_values()`",
            ),
            DeprecationWarning,
            stacklevel=1,
        )
        running_job = self._strict_get_running_job()
        resp1, resp2 = running_job.get_io_values()
        return [
            {
                "io_number": 1,
                "int_value": resp1.int_value,
                "fixed_value": resp1.double_value,
                "boolean_value": resp1.boolean_value,
            },
            {
                "io_number": 2,
                "int_value": resp2.int_value,
                "fixed_value": resp2.double_value,
                "boolean_value": resp2.boolean_value,
            },
        ]

    def save_config_to_file(self, filename: PathLike) -> None:
        """Deprecated - This method is going to be removed.

        Saves the qm current config to a file

        Args:
            filename: The name of the file where the config will be saved
        """
        warnings.warn(
            deprecation_message(
                method="qm.save_config_to_file",
                deprecated_in="1.2.0",
                removed_in="1.4.0",
                details="This method is going to be removed.",
            ),
            DeprecationWarning,
            stacklevel=1,
        )
        with open(filename, "w") as writer:
            json.dump(self.get_config(), writer)

    def get_running_job(self) -> Optional[JobApiWithDeprecations]:
        """Deprecated - This method is going to be removed, please use `qm.get_jobs(status=['Running'])`

        Gets the currently running job. Returns None if there isn't one.
        """
        warnings.warn(
            deprecation_message(
                method="qm.get_running_job",
                deprecated_in="1.2.0",
                removed_in="1.4.0",
                details="This method is going to be removed, please use `qm.get_jobs(status=['Running'])`",
            ),
            DeprecationWarning,
            stacklevel=1,
        )
        return self._get_running_job()

    def _get_running_job(self) -> Optional[JobApiWithDeprecations]:
        jobs = self.get_jobs(status=["Running"])
        if jobs:
            return self._get_job(jobs[0].id)
        return None

    def _strict_get_running_job(self) -> JobApiWithDeprecations:
        job = self._get_running_job()
        if job is None:
            raise NoRunningQmJob("No running job found")
        return job

    def _get_output_port_from_element(self, element_name: str, port_name: str) -> QuaConfigAdcPortReference:
        element = self._get_elements_pb_config()[element_name]
        return element.multiple_outputs.port_references[port_name]

    def _get_input_ports_from_mixed_input_element(
        self, element_name: str
    ) -> Tuple[QuaConfigDacPortReference, QuaConfigDacPortReference]:
        element = self._get_elements_pb_config()[element_name]
        return element.mix_inputs.i, element.mix_inputs.q

    def _get_input_port_from_single_input_element(self, element_name: str) -> QuaConfigDacPortReference:
        element = self._get_elements_pb_config()[element_name]
        return element.single_input.port

    def _get_elements_pb_config(self) -> Dict[str, QuaConfigElementDec]:
        return get_logical_pb_config(self._get_pb_config()).elements

    @staticmethod
    def _create_config_for_input_dc_offset_setting(port: QuaConfigAdcPortReference, value: Number) -> FullQuaConfig:
        return {
            "controllers": {
                port.controller: {
                    "fems": {cast(FEM_IDX, port.fem): {"type": "LF", "analog_inputs": {port.number: {"offset": value}}}}
                }
            },
        }

    @staticmethod
    def _create_config_for_output_dc_offset_setting(port: QuaConfigDacPortReference, value: Number) -> FullQuaConfig:
        return {
            "controllers": {
                port.controller: {
                    "fems": {
                        cast(FEM_IDX, port.fem): {"type": "LF", "analog_outputs": {port.number: {"offset": value}}}
                    }
                }
            },
        }
