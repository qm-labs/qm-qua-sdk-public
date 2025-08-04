from collections import defaultdict
from typing import Dict, List, Union, Optional, Sequence

import betterproto
from betterproto.lib.std.google.protobuf import Struct

from qm.api.v2.job_api import JobApi
from qm.utils.async_utils import run_async
from qm.waveform_report import WaveformReport
from qm.utils.config_utils import get_fem_config
from qm.grpc.frontend import SimulatedResponsePart
from qm.jobs.simulated_job import extract_struct_value
from qm.api.models.server_details import ConnectionDetails
from qm.api.v2.job_api.job_api import JobApiWithDeprecations
from qm.exceptions import QopResponseError, QMSimulationError
from qm.api.models.capabilities import QopCaps, ServerCapabilities
from qm._stream_results import SimulatorSamples, SimulatorControllerSamples
from qm.grpc.qua_config import (
    QuaConfigControllerDec,
    QuaConfigOctoDacFemDec,
    QuaConfigMicrowaveFemDec,
    QuaConfigAdcPortReference,
)
from qm.grpc.v2 import (
    PullSamplesRequest,
    GetWaveformReportRequest,
    PullSamplesResponsePullSamplesResponseSuccess,
    PullSamplesResponsePullSamplesResponseSuccessLf,
    PullSamplesResponsePullSamplesResponseSuccessMw,
    PullSamplesResponsePullSamplesResponseSuccessMode,
)


class SimulatedJobApi(JobApi):
    def __init__(
        self,
        connection_details: ConnectionDetails,
        job_id: str,
        simulated_response: Optional[SimulatedResponsePart],
        capabilities: ServerCapabilities,
    ) -> None:
        super().__init__(connection_details, job_id, capabilities)
        self._waveform_report = None

        # In QOP 3.2 and earlier, the waveform_report is included inside the simulated_response, which is provided
        # during the creation of the SimulatedJobApi. This if statement is checking this case.
        # TODO: Remove the support for this flow in QOP 3.6
        if not capabilities.supports(QopCaps.waveform_report_endpoint) and simulated_response:
            self._waveform_report = self._build_waveform_report(simulated_response.waveform_report)

    def _build_waveform_report(self, raw_waveform_report: Struct) -> WaveformReport:
        return WaveformReport.from_dict(extract_struct_value(raw_waveform_report), self.id)

    def _get_raw_waveform_report_from_api(self) -> Struct:
        request = GetWaveformReportRequest(self.id)
        try:
            response = self._run(self._stub.get_waveform_report(request, timeout=self._timeout))
        except QopResponseError as e:
            raise QMSimulationError("Error while getting waveform report from API. Error: " + str(e))

        return response.waveform_report

    def get_simulated_waveform_report(self) -> WaveformReport:
        if self._waveform_report is None:
            raw_waveform_report = self._get_raw_waveform_report_from_api()
            self._waveform_report = self._build_waveform_report(raw_waveform_report)

        return self._waveform_report

    async def _pull_simulator_samples(
        self, include_analog: bool, include_digital: bool
    ) -> Dict[str, List[PullSamplesResponsePullSamplesResponseSuccess]]:
        request = PullSamplesRequest(self._id, include_analog, include_digital)
        bare_results = defaultdict(list)
        async for result in self._run_async_iterator(self._stub.pull_samples, request, timeout=self._timeout):
            _, response = betterproto.which_one_of(result, "response_oneof")
            if isinstance(response, PullSamplesResponsePullSamplesResponseSuccess):
                bare_results[response.controller].append(response)
            else:
                raise QMSimulationError("Error while pulling samples")
        return dict(bare_results)

    def get_simulated_samples(self, include_analog: bool = True, include_digital: bool = True) -> SimulatorSamples:
        config = self._get_pb_config()

        results_by_controller = run_async(self._pull_simulator_samples(include_analog, include_digital))
        controller_to_samples = {}
        for controller, responses in results_by_controller.items():
            analog: Dict[str, Sequence[Union[float, complex]]] = {}
            digital = {}
            analog_sampling_rate = {}
            for response in responses:
                fem_config = get_fem_config(
                    config,
                    QuaConfigAdcPortReference(controller=controller, fem=response.fem_id, number=response.port_id),
                )
                key = f"{response.fem_id}-{response.port_id}"
                if response.mode == PullSamplesResponsePullSamplesResponseSuccessMode.ANALOG:
                    if isinstance(fem_config, QuaConfigControllerDec):
                        analog_sampling_rate[key] = 1e9
                    elif isinstance(fem_config, QuaConfigOctoDacFemDec):
                        analog_sampling_rate[key] = 2e9
                    elif isinstance(fem_config, QuaConfigMicrowaveFemDec):
                        sampling_rate = fem_config.analog_outputs[response.port_id].sampling_rate
                        assert (
                            sampling_rate is not None
                        )  # Mypy thinks it can be None, but it can't really (sampling_rate has a default value)
                        analog_sampling_rate[key + "-1"] = sampling_rate
                        analog_sampling_rate[key + "-2"] = sampling_rate
                    else:
                        raise QMSimulationError(f"Unknown FEM type: {fem_config}")

                    samples = response.double_data
                    _, data = betterproto.which_one_of(samples, "output")
                    if isinstance(data, PullSamplesResponsePullSamplesResponseSuccessMw):
                        analog[f"{key}-{data.duc_id}"] = [x + 1j * y for x, y in zip(data.i, data.q)]
                    elif isinstance(data, PullSamplesResponsePullSamplesResponseSuccessLf):
                        analog[key] = data.items
                else:
                    digital[key] = response.boolean_data.data[0].item
            controller_to_samples[controller] = SimulatorControllerSamples(
                analog, digital, analog_sampling_rate=analog_sampling_rate
            )
        return SimulatorSamples(controller_to_samples)

    def plot_waveform_report_with_simulated_samples(self) -> None:
        self.get_simulated_waveform_report().create_plot(self.get_simulated_samples())

    def plot_waveform_report_without_samples(self) -> None:
        self.get_simulated_waveform_report().create_plot()


class SimulatedJobApiWithDeprecations(JobApiWithDeprecations, SimulatedJobApi):
    pass
