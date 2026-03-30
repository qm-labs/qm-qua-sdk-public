from typing import Union, Optional

from qm.grpc.qm.pb import inc_qua_config_pb2
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

ALLOWED_GAINS = {x / 2 for x in range(-40, 41)}

IF_OUT1_DEFAULT = "out1"
IF_OUT2_DEFAULT = "out2"


class OctaveConverter(BaseDictToPbConverter[OctaveConfigType, inc_qua_config_pb2.QuaConfig.Octave.Config]):
    def convert(self, input_data: OctaveConfigType) -> inc_qua_config_pb2.QuaConfig.Octave.Config:
        return self.octave_to_pb(input_data)

    def deconvert(self, output_data: inc_qua_config_pb2.QuaConfig.Octave.Config) -> OctaveConfigType:
        raise NotImplementedError("Conversion of the octave configuration to dictionary is not available.")

    def octave_to_pb(self, data: OctaveConfigType) -> inc_qua_config_pb2.QuaConfig.Octave.Config:
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
        return inc_qua_config_pb2.QuaConfig.Octave.Config(
            loopbacks=loopbacks,
            rf_outputs=rf_modules,
            rf_inputs=rf_inputs,
            if_outputs=if_outputs,
        )

    @staticmethod
    def get_octave_loopbacks(data: list[LoopbackType]) -> list[inc_qua_config_pb2.QuaConfig.Octave.Loopback]:
        loopbacks = [
            inc_qua_config_pb2.QuaConfig.Octave.Loopback(
                lo_source_input=getattr(inc_qua_config_pb2.QuaConfig.Octave.LoopbackInput, loopback[1]),
                lo_source_generator=inc_qua_config_pb2.QuaConfig.Octave.SynthesizerPort(
                    device_name=loopback[0][0],
                    port_name=getattr(
                        inc_qua_config_pb2.QuaConfig.Octave.SynthesizerOutputName, loopback[0][1].lower()
                    ),
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

    def rf_module_to_pb(self, data: OctaveRFOutputConfigType) -> inc_qua_config_pb2.QuaConfig.Octave.RFOutputConfig:
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
        output_mode = getattr(
            inc_qua_config_pb2.QuaConfig.Octave.OutputSwitchState, data.get("output_mode", "always_off").lower()
        )
        lo_source = getattr(
            inc_qua_config_pb2.QuaConfig.Octave.LOSourceInput, data.get("LO_source", "internal").lower()
        )
        to_return = inc_qua_config_pb2.QuaConfig.Octave.RFOutputConfig(
            LO_frequency=self._get_lo_frequency(data),
            LO_source=lo_source,
            output_mode=output_mode,
            gain=gain,
            input_attenuators=input_attenuators == "ON",
        )
        if "I_connection" in data:
            to_return.I_connection.CopyFrom(dac_port_ref_to_pb(*_get_port_reference_with_fem(data["I_connection"])))
        if "Q_connection" in data:
            to_return.Q_connection.CopyFrom(dac_port_ref_to_pb(*_get_port_reference_with_fem(data["Q_connection"])))
        return to_return

    def rf_input_to_pb(
        self, data: OctaveRFInputConfigType, input_idx: int = 0
    ) -> inc_qua_config_pb2.QuaConfig.Octave.RFInputConfig:
        input_idx_to_default_lo_source = {0: "not_set", 1: "internal", 2: "external"}  # 0 here is just for the default
        rf_source = getattr(
            inc_qua_config_pb2.QuaConfig.Octave.DownconverterRFSource, data.get("RF_source", "RF_in").lower()
        )
        if input_idx == 1 and rf_source != inc_qua_config_pb2.QuaConfig.Octave.DownconverterRFSource.rf_in:
            raise InvalidOctaveParameter("Downconverter 1 must be connected to RF-in")

        lo_source = getattr(
            inc_qua_config_pb2.QuaConfig.Octave.LOSourceInput,
            data.get("LO_source", input_idx_to_default_lo_source[input_idx]).lower(),
        )
        if input_idx == 2 and lo_source == inc_qua_config_pb2.QuaConfig.Octave.LOSourceInput.internal:
            raise InvalidOctaveParameter("Downconverter 2 does not have internal LO")

        to_return = inc_qua_config_pb2.QuaConfig.Octave.RFInputConfig(
            RF_source=rf_source,
            LO_frequency=self._get_lo_frequency(data),
            LO_source=lo_source,
            IF_mode_I=getattr(inc_qua_config_pb2.QuaConfig.Octave.IFMode, data.get("IF_mode_I", "direct").lower()),
            IF_mode_Q=getattr(inc_qua_config_pb2.QuaConfig.Octave.IFMode, data.get("IF_mode_Q", "direct").lower()),
        )
        return to_return

    @staticmethod
    def single_if_output_to_pb(
        data: OctaveSingleIfOutputConfigType,
    ) -> inc_qua_config_pb2.QuaConfig.Octave.SingleIFOutputConfig:
        controller, fem, number = _get_port_reference_with_fem(data["port"])
        return inc_qua_config_pb2.QuaConfig.Octave.SingleIFOutputConfig(
            port=inc_qua_config_pb2.QuaConfig.AdcPortReference(controller=controller, fem=fem, number=number),
            name=data["name"],
        )

    def _octave_if_outputs_to_pb(
        self, data: OctaveIfOutputsConfigType
    ) -> inc_qua_config_pb2.QuaConfig.Octave.IFOutputsConfig:
        inst = inc_qua_config_pb2.QuaConfig.Octave.IFOutputsConfig()
        if "IF_out1" in data:
            inst.IF_out1.CopyFrom(self.single_if_output_to_pb(data["IF_out1"]))
        if "IF_out2" in data:
            inst.IF_out2.CopyFrom(self.single_if_output_to_pb(data["IF_out2"]))
        return inst


def dac_port_ref_to_pb(controller: str, fem: int, number: int) -> inc_qua_config_pb2.QuaConfig.DacPortReference:
    return inc_qua_config_pb2.QuaConfig.DacPortReference(controller=controller, fem=fem, number=number)


def _get_port_reference_with_fem(reference: PortReferenceType) -> StandardPort:
    if len(reference) == 2:
        return reference[0], OPX_FEM_IDX, reference[1]
    else:
        return reference
