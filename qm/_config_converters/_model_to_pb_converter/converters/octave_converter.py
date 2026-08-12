from dataclasses import dataclass
from collections.abc import Mapping, Collection

from qm.config._ports._port_base import Port
from qm.grpc.qm.pb.inc_qua_config_pb2 import QuaConfig
from qm._config_converters._model_to_pb_converter.base_converter import BaseModelToPbConverter
from qm.config._octave._octave import Loopback, OctaveRfPort, OctaveRfInput, OctaveRfOutput, OctaveConnectivity


@dataclass
class OctaveDeviceData:
    rf_outputs: Collection[OctaveRfOutput]
    rf_inputs: Collection[OctaveRfInput]
    connectivity: OctaveConnectivity


class OctaveConverter(BaseModelToPbConverter[Collection[OctaveRfPort], Mapping[str, QuaConfig.Octave.Config]]):
    """
    This is a temporary converter, since octave is not needed in the proto, and we can use the model to configure octave
    """

    def convert(self, input_data: Collection[OctaveRfPort]) -> Mapping[str, QuaConfig.Octave.Config]:
        device_to_data = self._split_to_devices(input_data)
        return {name: self.octave_to_pb(data) for name, data in device_to_data.items()}

    def deconvert(self, output_data: Mapping[str, QuaConfig.Octave.Config]) -> Collection[OctaveRfPort]:
        raise NotImplementedError("Conversion of the octave configuration to dictionary is not available.")

    @staticmethod
    def _split_to_devices(ports: Collection[OctaveRfPort]) -> Mapping[str, OctaveDeviceData]:
        """
        A function that takes the collection of ports and splits it according to the devices.
        The connectivity is taken from one of the ports assuming they are all pointing to the same connectivity object.
        """
        rf_outputs_by_device: dict[str, list[OctaveRfOutput]] = {}
        rf_inputs_by_device: dict[str, list[OctaveRfInput]] = {}
        connectivity_by_device: dict[str, OctaveConnectivity] = {}
        for port in ports:
            device_name = port.device.device_name
            connectivity_by_device.setdefault(device_name, port.device)
            if isinstance(port, OctaveRfOutput):
                rf_outputs_by_device.setdefault(device_name, []).append(port)
            elif isinstance(port, OctaveRfInput):
                rf_inputs_by_device.setdefault(device_name, []).append(port)
        return {
            device_name: OctaveDeviceData(
                rf_outputs=rf_outputs_by_device.get(device_name, []),
                rf_inputs=rf_inputs_by_device.get(device_name, []),
                connectivity=connectivity,
            )
            for device_name, connectivity in connectivity_by_device.items()
        }

    def octave_to_pb(self, data: OctaveDeviceData) -> QuaConfig.Octave.Config:
        loopbacks = self.get_octave_loopbacks(data.connectivity.loopbacks)
        rf_modules = {rf_out.index: self.rf_module_to_pb(rf_out) for rf_out in data.rf_outputs}
        rf_inputs = {rf_in.index: self.rf_input_to_pb(rf_in) for rf_in in data.rf_inputs}
        if_outputs = self._octave_if_outputs_to_pb(data.connectivity)
        return QuaConfig.Octave.Config(
            loopbacks=loopbacks,
            rf_outputs=rf_modules,
            rf_inputs=rf_inputs,
            if_outputs=if_outputs,
        )

    @staticmethod
    def get_octave_loopbacks(data: Collection[Loopback]) -> list[QuaConfig.Octave.Loopback]:
        loopbacks = [
            QuaConfig.Octave.Loopback(
                lo_source_input=getattr(QuaConfig.Octave.LoopbackInput, loopback.lo_source_input),
                lo_source_generator=QuaConfig.Octave.SynthesizerPort(
                    device_name=loopback.lo_source_generator[0],
                    port_name=getattr(QuaConfig.Octave.SynthesizerOutputName, loopback.lo_source_generator[1].lower()),
                ),
            )
            for loopback in data
        ]
        return loopbacks

    @staticmethod
    def rf_module_to_pb(data: OctaveRfOutput) -> QuaConfig.Octave.RFOutputConfig:
        output_mode = getattr(QuaConfig.Octave.OutputSwitchState, data.output_mode.lower())
        lo_source = getattr(QuaConfig.Octave.LOSourceInput, data.lo_source.lower())
        to_return = QuaConfig.Octave.RFOutputConfig(
            LO_frequency=data.lo_frequency,
            LO_source=lo_source,
            output_mode=output_mode,
            gain=data.gain,
            input_attenuators=data.input_attenuators == "ON",
        )
        to_return.I_connection.CopyFrom(dac_port_ref_to_pb(data.i_connection))
        to_return.Q_connection.CopyFrom(dac_port_ref_to_pb(data.q_connection))
        return to_return

    @staticmethod
    def rf_input_to_pb(data: OctaveRfInput) -> QuaConfig.Octave.RFInputConfig:
        rf_source = getattr(QuaConfig.Octave.DownconverterRFSource, data.rf_source.lower())
        lo_source = getattr(QuaConfig.Octave.LOSourceInput, data.lo_source.lower())
        to_return = QuaConfig.Octave.RFInputConfig(
            RF_source=rf_source,
            LO_frequency=data.lo_frequency,
            LO_source=lo_source,
            IF_mode_I=getattr(QuaConfig.Octave.IFMode, data.if_mode_i.lower()),
            IF_mode_Q=getattr(QuaConfig.Octave.IFMode, data.if_mode_q.lower()),
        )
        return to_return

    @staticmethod
    def single_if_output_to_pb(data: Port) -> QuaConfig.Octave.SingleIFOutputConfig:
        return QuaConfig.Octave.SingleIFOutputConfig(
            port=QuaConfig.AdcPortReference(
                controller=data.controller_name, fem=data.fem_1_based, number=data.index_1_based
            ),
        )

    def _octave_if_outputs_to_pb(self, data: OctaveConnectivity) -> QuaConfig.Octave.IFOutputsConfig:
        inst = QuaConfig.Octave.IFOutputsConfig()
        if 1 in data.outputs:
            inst.IF_out1.CopyFrom(self.single_if_output_to_pb(data.outputs[1]))
        if 2 in data.outputs:
            inst.IF_out2.CopyFrom(self.single_if_output_to_pb(data.outputs[2]))
        return inst


def dac_port_ref_to_pb(port: Port) -> QuaConfig.DacPortReference:
    return QuaConfig.DacPortReference(controller=port.controller_name, fem=port.fem_1_based, number=port.index_1_based)
