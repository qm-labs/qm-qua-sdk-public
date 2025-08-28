from typing import Union, Optional

from qm.api.models.capabilities import OPX_FEM_IDX
from qm.program._dict_to_pb_converter.base_converter import BaseDictToPbConverter
from qm.exceptions import InvalidOctaveParameter, ConfigValidationException, OctaveConnectionAmbiguity
from qm.type_hinting.config_types import (
    LoopbackType,
    StandardPort,
    OctaveConfigType,
    PortReferenceType,
    OctaveRFInputConfigType,
    OctaveRFOutputConfigType,
    OctaveIfOutputsConfigType,
    OctaveSingleIfOutputConfigType,
)
from qm.grpc.qua_config import (
    QuaConfigOctaveConfig,
    QuaConfigOctaveIfMode,
    QuaConfigOctaveLoopback,
    QuaConfigAdcPortReference,
    QuaConfigDacPortReference,
    QuaConfigOctaveLoopbackInput,
    QuaConfigOctaveLoSourceInput,
    QuaConfigOctaveRfInputConfig,
    QuaConfigOctaveRfOutputConfig,
    QuaConfigOctaveIfOutputsConfig,
    QuaConfigOctaveSynthesizerPort,
    QuaConfigOctaveOutputSwitchState,
    QuaConfigOctaveSingleIfOutputConfig,
    QuaConfigOctaveDownconverterRfSource,
    QuaConfigOctaveSynthesizerOutputName,
)

ALLOWED_GAINS = {x / 2 for x in range(-40, 41)}

IF_OUT1_DEFAULT = "out1"
IF_OUT2_DEFAULT = "out2"


class OctaveConverter(BaseDictToPbConverter[OctaveConfigType, QuaConfigOctaveConfig]):
    def convert(self, input_data: OctaveConfigType) -> QuaConfigOctaveConfig:
        return self.octave_to_pb(input_data)

    def deconvert(self, output_data: QuaConfigOctaveConfig) -> OctaveConfigType:
        raise NotImplementedError("Conversion of the octave configuration to dictionary is not available.")

    def octave_to_pb(self, data: OctaveConfigType) -> QuaConfigOctaveConfig:
        connectivity = data.get("connectivity", None)
        if isinstance(connectivity, str):
            connectivity = (connectivity, OPX_FEM_IDX)
        loopbacks = self.get_octave_loopbacks(data.get("loopbacks", []))
        rf_modules = {
            k: self.rf_module_to_pb(self.standardize_connectivity_for_if_in(v, connectivity, k))
            for k, v in data.get("RF_outputs", {}).items()
        }
        rf_inputs = {k: self.rf_input_to_pb(v, k) for k, v in data.get("RF_inputs", {}).items()}
        if_outputs = self._octave_if_outputs_to_pb(
            self.standardize_connectivity_for_if_out(data.get("IF_outputs", {}), connectivity)
        )
        return QuaConfigOctaveConfig(
            loopbacks=loopbacks,
            rf_outputs=rf_modules,
            rf_inputs=rf_inputs,
            if_outputs=if_outputs,
        )

    @staticmethod
    def get_octave_loopbacks(data: list[LoopbackType]) -> list[QuaConfigOctaveLoopback]:
        loopbacks = [
            QuaConfigOctaveLoopback(
                lo_source_input=QuaConfigOctaveLoopbackInput[loopback[1]],
                lo_source_generator=QuaConfigOctaveSynthesizerPort(
                    device_name=loopback[0][0],
                    port_name=QuaConfigOctaveSynthesizerOutputName[loopback[0][1].lower()],
                ),
            )
            for loopback in data
        ]
        return loopbacks

    @staticmethod
    def standardize_connectivity_for_if_in(
        data: OctaveRFOutputConfigType, controller_connectivity: Optional[tuple[str, int]], module_number: int
    ) -> OctaveRFOutputConfigType:
        if controller_connectivity is not None:
            if ("I_connection" in data) or ("Q_connection" in data):
                raise OctaveConnectionAmbiguity()

            data["I_connection"] = controller_connectivity + (2 * module_number - 1,)
            data["Q_connection"] = controller_connectivity + (2 * module_number,)
        return data

    @staticmethod
    def standardize_connectivity_for_if_out(
        data: OctaveIfOutputsConfigType, controller_connectivity: Optional[tuple[str, int]]
    ) -> OctaveIfOutputsConfigType:
        if controller_connectivity is not None:
            if "IF_out1" not in data:
                data["IF_out1"] = {"name": IF_OUT1_DEFAULT}
            if "IF_out2" not in data:
                data["IF_out2"] = {"name": IF_OUT2_DEFAULT}
            if ("port" in data["IF_out1"]) or ("port" in data["IF_out2"]):
                raise OctaveConnectionAmbiguity()
            data["IF_out1"]["port"] = controller_connectivity + (1,)
            data["IF_out2"]["port"] = controller_connectivity + (2,)
        return data

    @staticmethod
    def _get_lo_frequency(data: Union[OctaveRFOutputConfigType, OctaveRFInputConfigType]) -> float:
        if "LO_frequency" not in data:
            raise ConfigValidationException("No LO frequency was set for upconverter")
        lo_freq = data["LO_frequency"]
        if not 2e9 <= lo_freq <= 18e9:
            raise ConfigValidationException(f"LO frequency {lo_freq} is out of range")
        return lo_freq

    def rf_module_to_pb(self, data: OctaveRFOutputConfigType) -> QuaConfigOctaveRfOutputConfig:
        input_attenuators = data.get("input_attenuators", "OFF").upper()
        if input_attenuators not in {"ON", "OFF"}:
            raise ConfigValidationException("input_attenuators must be either ON or OFF")
        if "gain" not in data:
            raise ConfigValidationException("No gain was set for upconverter")
        gain = float(data["gain"])
        if gain not in ALLOWED_GAINS:
            raise ConfigValidationException(
                f"Gain should be an integer or half-integer between -20 and 20, got {gain})"
            )
        to_return = QuaConfigOctaveRfOutputConfig(
            lo_frequency=self._get_lo_frequency(data),
            lo_source=QuaConfigOctaveLoSourceInput[data.get("LO_source", "internal").lower()],
            output_mode=QuaConfigOctaveOutputSwitchState[data.get("output_mode", "always_off").lower()],
            gain=gain,
            input_attenuators=input_attenuators == "ON",
        )
        if "I_connection" in data:
            to_return.i_connection = dac_port_ref_to_pb(*_get_port_reference_with_fem(data["I_connection"]))
        if "Q_connection" in data:
            to_return.q_connection = dac_port_ref_to_pb(*_get_port_reference_with_fem(data["Q_connection"]))
        return to_return

    def rf_input_to_pb(self, data: OctaveRFInputConfigType, input_idx: int = 0) -> QuaConfigOctaveRfInputConfig:
        input_idx_to_default_lo_source = {0: "not_set", 1: "internal", 2: "external"}  # 0 here is just for the default
        rf_source = QuaConfigOctaveDownconverterRfSource[data.get("RF_source", "RF_in").lower()]  # type: ignore[valid-type]
        if input_idx == 1 and rf_source != QuaConfigOctaveDownconverterRfSource.rf_in:
            raise InvalidOctaveParameter("Downconverter 1 must be connected to RF-in")

        lo_source = QuaConfigOctaveLoSourceInput[data.get("LO_source", input_idx_to_default_lo_source[input_idx]).lower()]  # type: ignore[valid-type]
        if input_idx == 2 and lo_source == QuaConfigOctaveLoSourceInput.internal:
            raise InvalidOctaveParameter("Downconverter 2 does not have internal LO")

        to_return = QuaConfigOctaveRfInputConfig(
            rf_source=rf_source,
            lo_frequency=self._get_lo_frequency(data),
            lo_source=lo_source,
            if_mode_i=QuaConfigOctaveIfMode[data.get("IF_mode_I", "direct").lower()],
            if_mode_q=QuaConfigOctaveIfMode[data.get("IF_mode_Q", "direct").lower()],
        )
        return to_return

    @staticmethod
    def single_if_output_to_pb(data: OctaveSingleIfOutputConfigType) -> QuaConfigOctaveSingleIfOutputConfig:
        controller, fem, number = _get_port_reference_with_fem(data["port"])
        return QuaConfigOctaveSingleIfOutputConfig(
            port=QuaConfigAdcPortReference(controller=controller, fem=fem, number=number), name=data["name"]
        )

    def _octave_if_outputs_to_pb(self, data: OctaveIfOutputsConfigType) -> QuaConfigOctaveIfOutputsConfig:
        inst = QuaConfigOctaveIfOutputsConfig()
        if "IF_out1" in data:
            inst.if_out1 = self.single_if_output_to_pb(data["IF_out1"])
        if "IF_out2" in data:
            inst.if_out2 = self.single_if_output_to_pb(data["IF_out2"])
        return inst


def dac_port_ref_to_pb(controller: str, fem: int, number: int) -> QuaConfigDacPortReference:
    return QuaConfigDacPortReference(controller=controller, fem=fem, number=number)


def _get_port_reference_with_fem(reference: PortReferenceType) -> StandardPort:
    if len(reference) == 2:
        return reference[0], OPX_FEM_IDX, reference[1]
    else:
        return reference
