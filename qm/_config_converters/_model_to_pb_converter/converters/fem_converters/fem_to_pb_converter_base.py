from abc import ABC
from typing import Literal, TypeVar, Sequence

from qm import QopCaps
from qm.exceptions import ConfigValidationException
from qm.grpc.qm.pb.inc_qua_config_pb2 import QuaConfig
from qm.config._primitives import NOT_SET, ConfigOptional
from qm.config._ports import DigitalInputPort, AnalogInputPortLf, DigitalOutputPort
from qm._config_converters._model_to_pb_converter.base_converter import BaseModelToPbConverter
from qm._config_converters.split_ports_by_fems import AllFems, FemDataOpx, FemDataOctoDac, FemDataMicrowave

ControllerConfigTypeVar = TypeVar(
    "ControllerConfigTypeVar", QuaConfig.OctoDacFemDec, QuaConfig.ControllerDec, QuaConfig.MicrowaveFemDec
)
FemDataT = TypeVar("FemDataT", FemDataOpx, FemDataOctoDac, FemDataMicrowave)
FemPbT = TypeVar("FemPbT", QuaConfig.ControllerDec, QuaConfig, QuaConfig.OctoDacFemDec, QuaConfig.MicrowaveFemDec)


class FemToPbConverter(BaseModelToPbConverter[FemDataT, FemPbT], ABC):
    def _set_digital_ports_in_config(
        self,
        config: ControllerConfigTypeVar,
        data: AllFems,
    ) -> None:
        for digital_output in data.digital_outputs:
            config.digitalOutputs[digital_output.index].CopyFrom(self._digital_output_port_to_pb(digital_output))

        for digital_input in data.digital_inputs:
            config.digitalInputs[digital_input.index].CopyFrom(self._digital_input_port_to_pb(digital_input))

    def _digital_output_port_to_pb(self, data: DigitalOutputPort) -> QuaConfig.DigitalOutputPortDec:
        if self._should_apply_defaults:
            digital_output = QuaConfig.DigitalOutputPortDec(
                shareable=data.shareable.get_value(),
                inverted=data.inverted.get_value(),
                # The only currently supported level is LVTTL, so we set it always
                level=QuaConfig.VoltageLevel.LVTTL,
            )
        else:
            digital_output = QuaConfig.DigitalOutputPortDec(
                # The only currently supported level is LVTTL, so we set it always
                level=QuaConfig.VoltageLevel.LVTTL,
            )
            if data.shareable.is_set:
                digital_output.shareable = data.shareable.get_value()
            if data.inverted.is_set:
                digital_output.inverted = data.inverted.get_value()
        return digital_output

    def _digital_input_port_to_pb(self, data: DigitalInputPort) -> QuaConfig.DigitalInputPortDec:
        if self._init_mode:
            if not all(x.is_set for x in (data.deadtime, data.polarity, data.threshold)):
                raise ConfigValidationException("The fields `deadtime`, `polarity`, `threshold` must all be set.")

        digital_input = QuaConfig.DigitalInputPortDec(
            level=QuaConfig.VoltageLevel.LVTTL,
            # The user is not supposed to edit this anymore, it should always be LVTTL. Up until now the gateway just always
            # put LVTTL here, but we are moving it here because the SDK is in charge of supplying defaults.
        )
        if self._should_apply_defaults or data.threshold.is_set:
            digital_input.shareable = data.shareable.get_value()

        if data.threshold.is_set:
            digital_input.threshold = data.threshold.get_value()

        if data.polarity.is_set:
            if data.polarity.get_value() == "RISING":
                digital_input.polarity = QuaConfig.DigitalInputPortDec.Polarity.RISING
            elif data.polarity.get_value() == "FALLING":
                digital_input.polarity = QuaConfig.DigitalInputPortDec.Polarity.FALLING
            else:
                raise ConfigValidationException(f"Invalid polarity: {data.polarity.get_value()}")

        if data.deadtime.is_set:
            digital_input.deadtime = data.deadtime.get_value()

        return digital_input

    def _lf_analog_input_port_to_pb(self, data: AnalogInputPortLf) -> QuaConfig.AnalogInputPortDec:
        if self._should_apply_defaults:
            analog_input = QuaConfig.AnalogInputPortDec(
                offset=data.offset.get_value(),
                shareable=data.shareable.get_value(),
                samplingRate=data.sampling_rate.get_value(),
            )
            analog_input.gainDb.value = data.gain_db.get_value()
        else:
            analog_input = QuaConfig.AnalogInputPortDec()
            if data.offset.is_set:
                analog_input.offset = data.offset.get_value()
            if data.sampling_rate.is_set:
                analog_input.samplingRate = data.sampling_rate.get_value()
            if data.shareable.is_set:
                analog_input.shareable = data.shareable.get_value()
            if data.gain_db.is_set:
                analog_input.gainDb.value = data.gain_db.get_value()
        return analog_input

    def _deconvert_feedforward_filter(self, data: QuaConfig.AnalogOutputPortFilter) -> Sequence[float]:
        return data.feedforward_v2.value if self._capabilities.supports(QopCaps.config_v2) else data.feedforward

    @staticmethod
    def _get_polarity(data: QuaConfig.DigitalInputPortDec) -> ConfigOptional[Literal["RISING", "FALLING"]]:
        if data.HasField("polarity"):
            if data.polarity == QuaConfig.DigitalInputPortDec.Polarity.RISING:
                return "RISING"
            if data.polarity == QuaConfig.DigitalInputPortDec.Polarity.FALLING:
                return "FALLING"
        return NOT_SET
