from typing import Dict, List, Tuple, Optional, MutableMapping

from qm.octave_sdk.octave import RFInput
from qm.api.frontend_api import FrontendApi
from qm.grpc.qm.pb import inc_qua_config_pb2
from qm.elements.element_inputs import MixInputs
from qm.utils.protobuf_utils import assign_repeated
from qm.api.models.capabilities import ServerCapabilities
from qm.octave import QmOctaveConfig, AbstractCalibrationDB
from qm.octave_sdk import Octave, OctaveOutput, OctaveLOSource
from qm.octave.octave_manager import logger, get_device, get_loopbacks_from_pb
from qm.elements.up_converted_input import UpconvertedInput, UpconvertedInputNewApi
from qm.exceptions import OctaveCableSwapError, OctaveConnectionError, ElementUpconverterDeclarationError
from qm.utils.config_utils import (
    get_fem_config,
    get_logical_pb_config,
    element_has_mix_inputs,
    get_controller_pb_config,
)

OptionalOctaveInputPort = Optional[Tuple[str, int]]


class OctavesContainer:
    def __init__(
        self,
        pb_config: inc_qua_config_pb2.QuaConfig,
        capabilities: ServerCapabilities,
        octave_config: Optional[QmOctaveConfig] = None,
    ):
        self._octaves_pb_config = get_controller_pb_config(pb_config).octaves
        self._octave_qm_config = octave_config or QmOctaveConfig()
        self._capabilities = capabilities

        _qua_config_opx_to_octave_i = {}
        _qua_config_opx_to_octave_q = {}
        for octave_name, octave_qua_config in self._octaves_pb_config.items():
            for rf_idx, rf_config in octave_qua_config.rf_outputs.items():
                i_connection, q_connection = rf_config.I_connection, rf_config.Q_connection
                _qua_config_opx_to_octave_i[(i_connection.controller, i_connection.fem, i_connection.number)] = (
                    octave_name,
                    rf_idx,
                )
                _qua_config_opx_to_octave_q[(q_connection.controller, q_connection.fem, q_connection.number)] = (
                    octave_name,
                    rf_idx,
                )
        self._qua_config_opx_to_octave_i = _qua_config_opx_to_octave_i
        self._qua_config_opx_to_octave_q = _qua_config_opx_to_octave_q

    def get_upconverter_port_ref(
        self, element_config: inc_qua_config_pb2.QuaConfig.ElementDec
    ) -> OptionalOctaveInputPort:
        if element_config.RFInputs:
            rf_input = list(element_config.RFInputs.values())[0]
            return rf_input.device_name, rf_input.port
        if not element_has_mix_inputs(element_config):
            return None

        mix_inputs = element_config.mixInputs
        element_i_port, element_q_port = mix_inputs.I, mix_inputs.Q

        key_i = (element_i_port.controller, element_i_port.fem, element_i_port.number)
        key_q = (element_q_port.controller, element_q_port.fem, element_q_port.number)
        i_conn = self._qua_config_opx_to_octave_i.get(key_i)
        q_conn = self._qua_config_opx_to_octave_q.get(key_q)
        if i_conn is None and q_conn is None:
            if (self._qua_config_opx_to_octave_i.get(key_q) is not None) or (
                self._qua_config_opx_to_octave_q.get(key_i) is not None
            ):
                raise OctaveCableSwapError()

            return self._octave_qm_config.get_octave_input_port(
                (element_i_port.controller, element_i_port.fem, element_i_port.number),
                (element_q_port.controller, element_q_port.fem, element_q_port.number),
            )
        if i_conn != q_conn:
            raise ElementUpconverterDeclarationError()
        return i_conn

    def _get_downconverter_client(
        self, outputs: MutableMapping[str, inc_qua_config_pb2.QuaConfig.GeneralPortReference]
    ) -> Optional[RFInput]:
        if not outputs:
            return None
        for _, port_ref in outputs.items():
            if port_ref.device_name in self._octaves_pb_config:
                client = self._get_octave_client(port_ref.device_name)
                return client.rf_inputs[port_ref.port]
        raise OctaveConnectionError("No downconverter found for the given outputs.")

    def _get_loopbacks(self, octave_name: str) -> Dict[OctaveLOSource, OctaveOutput]:
        if octave_name in self._octaves_pb_config:
            pb_loopbacks = self._octaves_pb_config[octave_name].loopbacks
            return get_loopbacks_from_pb(pb_loopbacks, octave_name)
        return self._octave_qm_config.get_lo_loopbacks_by_octave(octave_name)

    def create_mix_inputs(
        self,
        element_config: inc_qua_config_pb2.QuaConfig.ElementDec,
        name: str,
        frontend_api: FrontendApi,
        machine_id: str,
    ) -> MixInputs:
        port = self.get_upconverter_port_ref(element_config)
        if port is None:
            return MixInputs(
                name,
                element_config.mixInputs,
                frontend_api,
                machine_id,
                set_frequency_as_double=self._capabilities.supports_double_frequency,
            )

        octave_name, octave_port = port
        client = self._get_octave_client(octave_name)

        return UpconvertedInput(
            name,
            element_config.mixInputs,
            frontend_api,
            machine_id,
            client=client.rf_outputs[octave_port],
            port=port,
            calibration_db=self._octave_qm_config.calibration_db,
            set_frequency_as_double=self._capabilities.supports_double_frequency,
            gain=self._get_octave_gain(octave_name, octave_port),
            use_input_attenuators=self._get_octave_input_attenuators(octave_name, octave_port),
        )

    def create_new_api_upconverted_input(
        self,
        element_config: inc_qua_config_pb2.QuaConfig.ElementDec,
        name: str,
    ) -> Optional[UpconvertedInputNewApi]:
        port = self.get_upconverter_port_ref(element_config)
        if port is None:
            return None

        octave_name, octave_port = port
        client = self._get_octave_client(octave_name)
        gain = self._get_octave_gain(octave_name, octave_port)

        return UpconvertedInputNewApi(
            name,
            element_config.mixInputs,
            client=client.rf_outputs[octave_port],
            port=port,
            calibration_db=self._octave_qm_config.calibration_db,
            gain=gain,
            set_frequency_as_double=self._capabilities.supports_double_frequency,
            use_input_attenuators=self._get_octave_input_attenuators(octave_name, octave_port),
        )

    def _get_octave_gain(self, octave_name: str, port: int) -> Optional[float]:
        try:
            return self._octaves_pb_config[octave_name].rf_outputs[port].gain
        except KeyError:
            logger.warning(
                "No gain was specified. Setting gain to None. "
                "Please configure all the ports' gain values in the qua configuration"
            )
            return None

    def _get_octave_input_attenuators(self, octave_name: str, port: int) -> bool:
        try:
            return self._octaves_pb_config[octave_name].rf_outputs[port].input_attenuators
        except KeyError:
            return False

    def get_downconverter(
        self, outputs: MutableMapping[str, inc_qua_config_pb2.QuaConfig.GeneralPortReference]
    ) -> Optional[RFInput]:
        return self._get_downconverter_client(outputs)

    def _get_octave_client(self, device_name: str) -> Octave:
        device_connection_info = self._octave_qm_config.devices[device_name]
        loopbacks = self._get_loopbacks(device_name)
        return get_device(
            device_connection_info,
            loop_backs=loopbacks,
            octave_name=device_name,
            fan=self._octave_qm_config.fan,
        )


def load_config_from_calibration_db(
    pb_config: inc_qua_config_pb2.QuaConfig,
    calibration_db: AbstractCalibrationDB,
    octave_config: QmOctaveConfig,
    capabilities: ServerCapabilities,
) -> inc_qua_config_pb2.QuaConfig:
    controller_pb_config = get_controller_pb_config(pb_config)
    logical_pb_config = get_logical_pb_config(pb_config)

    octaves_container = OctavesContainer(pb_config, capabilities, octave_config)

    logger.debug("Loading mixer calibration data onto the config")

    for element_name, element in logical_pb_config.elements.items():
        if not element_has_mix_inputs(element):
            continue

        mix_inputs = element.mixInputs
        lo_freq = mix_inputs.loFrequency or mix_inputs.loFrequencyDouble
        if not lo_freq:
            logger.debug(f"Element '{element_name}' has no LO frequency specified")
            continue

        octave_channel = octaves_container.get_upconverter_port_ref(element)
        if octave_channel is None:
            logger.debug(f"Element '{element_name}' is not connected to Octave")
            continue

        try:
            output_gain = controller_pb_config.octaves[octave_channel[0]].rf_outputs[octave_channel[1]].gain
        except KeyError:
            logger.warning(
                "No gain was specified. Setting gain to None. "
                "Please configure all the ports' gain values in the qua configuration"
            )
            output_gain = None

        lo_cal = calibration_db.get_lo_cal(octave_channel, lo_freq, output_gain)
        if lo_cal is None:
            logger.debug(
                f"the calibration db has no LO cal for element '{element_name}' (lo_freq = {lo_freq / 1e9:0.3f} GHz)"
            )
            continue

        i_port, q_port = mix_inputs.I, mix_inputs.Q
        i_controller_config = get_fem_config(pb_config, i_port)
        if not isinstance(i_controller_config, inc_qua_config_pb2.QuaConfig.MicrowaveFemDec):
            i_controller_config.analogOutputs[i_port.number].offset = lo_cal.get_i0()
        q_controller_config = get_fem_config(pb_config, q_port)
        if not isinstance(q_controller_config, inc_qua_config_pb2.QuaConfig.MicrowaveFemDec):
            q_controller_config.analogOutputs[q_port.number].offset = lo_cal.get_q0()

        # This section is applicable only to OPX devices. The `controllers` attribute, which contains only OPX devices,
        # is not present in config v2. Therefore, this code is executed only for config v1.
        if isinstance(controller_pb_config, inc_qua_config_pb2.QuaConfig.QuaConfigV1):
            if i_port.controller in controller_pb_config.controllers:
                controller_pb_config.controllers[i_port.controller].analogOutputs[
                    i_port.number
                ].offset = lo_cal.get_i0()
            if q_port.controller in controller_pb_config.controllers:
                controller_pb_config.controllers[q_port.controller].analogOutputs[
                    q_port.number
                ].offset = lo_cal.get_q0()

        # Now we go over all the IF frequencies we find and set them. Not sure
        # when an IF frequency different from the element's 'intermediate_frequency'
        # will be used. Maybe when static frequency change happens, the gateway takes
        # the correction from this updated config.
        if_calibrations_for_curr_lo = calibration_db.get_all_if_cal_for_lo(octave_channel, lo_freq, output_gain)

        # We are expected to put all these calibrations in the element's mixer
        curr_mixer = mix_inputs.mixer

        if curr_mixer not in controller_pb_config.mixers:
            logger.debug(f"Element '{element_name}' is using mixer '{curr_mixer}' which is not found.")
            continue

        old_if_cals = controller_pb_config.mixers[curr_mixer]
        new_if_cals: List[inc_qua_config_pb2.QuaConfig.CorrectionEntry] = []
        frequency_idx = int(capabilities.supports_double_frequency)  # This is to shorten many if-else in the code using
        # a trinary expression
        for if_freq, if_cal in if_calibrations_for_curr_lo.items():
            curr_new_calibration = inc_qua_config_pb2.QuaConfig.CorrectionEntry(
                frequency=int(abs(if_freq)),
                frequencyDouble=[0.0, float(abs(if_freq))][frequency_idx],
                loFrequency=int(lo_freq),
                loFrequencyDouble=[0.0, float(lo_freq)][frequency_idx],
                correction=inc_qua_config_pb2.QuaConfig.Matrix(**if_cal.get_correction_args()),
                frequencyNegative=if_freq < 0,
            )
            new_if_cals.append(curr_new_calibration)

        for old_if_cal in old_if_cals.correction:
            if lo_freq not in {old_if_cal.loFrequency, old_if_cal.loFrequencyDouble}:
                continue

            assert (
                old_if_cal.frequencyNegative is not None
            )  # Mypy thinks it can be None, but it can't really (frequency_negative has a default value)
            sign = (-1) ** old_if_cal.frequencyNegative
            old_if_freq = (old_if_cal.frequency or old_if_cal.frequencyDouble) * sign
            if old_if_freq in if_calibrations_for_curr_lo:
                continue

            new_if_cals.append(old_if_cal)
            logger.debug(
                f"Could not find calibration value for LO frequency {lo_freq} and intermediate_frequency {old_if_freq}"
            )
        assign_repeated(controller_pb_config.mixers[curr_mixer].correction, new_if_cals)

    return pb_config
