from qm.config._ports._analog_output import OutputMode
from qm.grpc.qm.pb.inc_qua_config_pb2 import QuaConfig
from qm._config_converters.split_ports_by_fems import FemDataOctoDac
from qm.config._primitives import NOT_SET, ConfigValue, ConfigOptional
from qm.config._ports import (
    LfFem,
    AnalogInputPortLf,
    AnalogOutputPortLf,
    DigitalInputPortLf,
    DigitalOutputPortLf,
)
from qm._config_converters._model_to_pb_converter.converters.fem_converters.analog_fem_converter_base import (
    AnalogFemToPbConverter,
)


class LfFemToPbConverter(AnalogFemToPbConverter[FemDataOctoDac, QuaConfig.OctoDacFemDec]):
    @property
    def _fem_pb_cls(self) -> type[QuaConfig.OctoDacFemDec]:
        return QuaConfig.OctoDacFemDec

    @property
    def _fem_data_cls(self) -> type[FemDataOctoDac]:
        return FemDataOctoDac

    @property
    def _analog_input_cls(self) -> type[AnalogInputPortLf]:
        return AnalogInputPortLf

    @property
    def _digital_output_cls(self) -> type[DigitalOutputPortLf]:
        return DigitalOutputPortLf

    @property
    def _digital_input_cls(self) -> type[DigitalInputPortLf]:
        return DigitalInputPortLf

    def _construct_analog_output(self, data: AnalogOutputPortLf) -> QuaConfig.OctoDacAnalogOutputPortDec:
        if self._should_apply_defaults:
            analog_output = QuaConfig.OctoDacAnalogOutputPortDec(
                shareable=data.shareable.get_value(),
                offset=data.offset.get_value(),
                delay=data.delay.get_value(),
                output_mode=self._output_mode_to_pb(data.output_mode),
            )
        else:
            analog_output = QuaConfig.OctoDacAnalogOutputPortDec(
                offset=data.offset.get_value(True),
                delay=data.delay.get_value(True),
            )
            if data.shareable.is_set:
                analog_output.shareable = data.shareable.get_value()

            if data.output_mode.is_set:
                analog_output.output_mode = self._output_mode_to_pb(data.output_mode)
        return analog_output

    @staticmethod
    def _output_mode_to_pb(data: ConfigValue[OutputMode]) -> QuaConfig.OctoDacAnalogOutputPortDec.OutputMode:
        if data.get_value() == "direct":
            return QuaConfig.OctoDacAnalogOutputPortDec.OutputMode.direct
        return QuaConfig.OctoDacAnalogOutputPortDec.OutputMode.amplified

    def _deconvert_analog_output(
        self,
        data: QuaConfig.OctoDacAnalogOutputPortDec,
        fem: LfFem,
        index: int,
    ) -> AnalogOutputPortLf:
        output_mode: ConfigOptional[OutputMode] = NOT_SET
        if data.HasField("output_mode"):
            if data.output_mode == QuaConfig.OctoDacAnalogOutputPortDec.OutputMode.direct:
                output_mode = "direct"
            elif data.output_mode == QuaConfig.OctoDacAnalogOutputPortDec.OutputMode.amplified:
                output_mode = "amplified"

        min_voltage_limit, max_voltage_limit = self._deconvert_voltage_limits(data)

        return AnalogOutputPortLf(
            fem=fem,
            index=index,
            offset=data.offset,
            delay=data.delay,
            shareable=data.shareable,
            crosstalk=self._deconvert_crosstalk(data),
            filter_feedforward=self._deconvert_feedforward_filter(data.filter) if data.HasField("filter") else NOT_SET,
            filter_feedback=self._deconvert_feedback_filter(data.filter) if data.HasField("filter") else NOT_SET,
            sampling_rate=self._deconvert_sampling_rate(data),
            upsampling_mode=self._deconvert_upsampling_mode(data),
            output_mode=output_mode,
            min_voltage_limit=min_voltage_limit,
            max_voltage_limit=max_voltage_limit,
        )
