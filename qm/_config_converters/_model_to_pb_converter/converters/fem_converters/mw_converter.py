from typing import Mapping, cast

from qm import QopCaps
from qm.exceptions import ConfigValidationException
from qm.grpc.qm.pb.inc_qua_config_pb2 import QuaConfig
from qm.config._primitives import NOT_SET, ConfigOptional
from qm._config_converters.split_ports_by_fems import FemDataMicrowave
from qm._config_converters._model_to_pb_converter.converters.fem_converters.fem_to_pb_converter_base import (
    FemToPbConverter,
)
from qm.config._ports import (
    Band,
    MwFem,
    AnalogInputPortMicrowave,
    AnalogOutputPortMicrowave,
    DigitalInputPortMicrowave,
    DigitalOutputPortMicrowave,
)


class MwFemToPbConverter(FemToPbConverter[FemDataMicrowave, QuaConfig.MicrowaveFemDec]):
    def convert(self, input_data: FemDataMicrowave) -> QuaConfig.MicrowaveFemDec:
        cont = QuaConfig.MicrowaveFemDec()
        for analog_output in input_data.analog_outputs:
            int_k = analog_output.index
            cont.analogOutputs[int_k].CopyFrom(self._analog_output_to_pb(analog_output))

        for analog_input_data in input_data.analog_inputs:
            int_k = analog_input_data.index
            cont.analogInputs[int_k].CopyFrom(self._analog_input_port_to_pb(analog_input_data))

        self._set_digital_ports_in_config(cont, input_data)
        return cont

    def _analog_output_to_pb(
        self,
        data: AnalogOutputPortMicrowave,
    ) -> QuaConfig.MicrowaveAnalogOutputPortDec:
        if self._should_apply_defaults:
            item = QuaConfig.MicrowaveAnalogOutputPortDec(
                samplingRate=data.sampling_rate.get_value(),
                fullScalePowerDbm=data.full_scale_power_dbm.get_value(),
                delay=data.delay.get_value(),
                shareable=data.shareable.get_value(),
            )
        else:
            item = QuaConfig.MicrowaveAnalogOutputPortDec()
            if data.sampling_rate.is_set:
                item.samplingRate = data.sampling_rate.get_value()
            if data.full_scale_power_dbm.is_set:
                item.fullScalePowerDbm = data.full_scale_power_dbm.get_value()
            if data.delay.is_set:
                item.delay = data.delay.get_value()
            if data.shareable.is_set:
                item.shareable = data.shareable.get_value()
        if data.band.is_set:
            item.band = data.band.get_value()

        upconverters = self._get_upconverters(data)
        if upconverters is not None:
            self._set_pb_attr_config_v2(item, upconverters, "upconverters", "upconverters_v2")
        return item

    def _get_upconverters(self, data: AnalogOutputPortMicrowave) -> Mapping[int, QuaConfig.UpConverterConfigDec] | None:
        if data.upconverter1_frequency.is_set or data.upconverter2_frequency.is_set:
            upconverters: dict[int, QuaConfig.UpConverterConfigDec] = {}
            if data.upconverter1_frequency.is_set:
                upconverters[1] = QuaConfig.UpConverterConfigDec(frequency=data.upconverter1_frequency.get_value())
            if data.upconverter2_frequency.is_set:
                upconverters[2] = QuaConfig.UpConverterConfigDec(frequency=data.upconverter2_frequency.get_value())
            return upconverters
        if self._should_apply_defaults:
            return {}
        if not self._init_mode:
            return None
        raise ConfigValidationException("At least one upconverter should be set.")

    def _analog_input_port_to_pb(self, data: AnalogInputPortMicrowave) -> QuaConfig.MicrowaveAnalogInputPortDec:
        if self._should_apply_defaults:
            analog_input = QuaConfig.MicrowaveAnalogInputPortDec(
                samplingRate=data.sampling_rate.get_value(),
                gain_db=data.gain_db.get_value(),
                shareable=data.shareable.get_value(),
            )
        else:
            analog_input = QuaConfig.MicrowaveAnalogInputPortDec()
            if data.sampling_rate.is_set:
                analog_input.samplingRate = data.sampling_rate.get_value()
            if data.shareable.is_set:
                analog_input.shareable = data.shareable.get_value()
            if data.gain_db.is_set:
                analog_input.gain_db = data.gain_db.get_value()

        if data.band.is_set:
            analog_input.band = data.band.get_value()
        if data.downconverter_frequency.is_set:
            analog_input.downconverter.frequency = data.downconverter_frequency.get_value()

        if data.lo_mode.is_set:
            if self._capabilities.supports(QopCaps.lo_mode):
                lo_mode_value = data.lo_mode.get_value()
                analog_input.lo_mode = (
                    QuaConfig.MicrowaveAnalogInputPortDec.LoMode.ALWAYS_ON
                    if lo_mode_value == "always_on"
                    else QuaConfig.MicrowaveAnalogInputPortDec.LoMode.AUTO
                )
            else:
                raise ConfigValidationException("['lo_mode'] are supported only from QOP 3.7 and later")

        return analog_input

    def deconvert(self, output_data: QuaConfig.MicrowaveFemDec, fem: MwFem) -> FemDataMicrowave:  # type: ignore[override]
        """
        The deconvert function breaks liskov substitution ot simplify the interface,
        together with enjoying the goodies of the methods of the base converter
        """
        return FemDataMicrowave(
            analog_inputs=self._deconvert_analog_inputs(output_data.analogInputs, fem=fem),
            digital_inputs=self._deconvert_digital_inputs(output_data.digitalInputs, fem=fem),
            digital_outputs=self._deconvert_digital_outputs(output_data.digitalOutputs, fem=fem),
            analog_outputs=self._deconvert_analog_outputs(output_data.analogOutputs, fem=fem),
        )

    def _deconvert_analog_outputs(
        self,
        outputs: Mapping[int, QuaConfig.MicrowaveAnalogOutputPortDec],
        fem: MwFem,
    ) -> tuple[AnalogOutputPortMicrowave, ...]:
        return tuple(self._deconvert_analog_output(output, fem=fem, index=idx) for idx, output in outputs.items())

    def _deconvert_analog_output(
        self,
        data: QuaConfig.MicrowaveAnalogOutputPortDec,
        fem: MwFem,
        index: int,
    ) -> AnalogOutputPortMicrowave:
        upconverters = (
            data.upconverters_v2.value if self._capabilities.supports(QopCaps.config_v2) else data.upconverters
        )
        return AnalogOutputPortMicrowave(
            fem=fem,
            index=index,
            sampling_rate=data.samplingRate,
            full_scale_power_dbm=data.fullScalePowerDbm,
            band=cast(Band, data.band),
            delay=data.delay,
            shareable=data.shareable,
            upconverter1_frequency=upconverters[1].frequency if 1 in upconverters else NOT_SET,
            upconverter2_frequency=upconverters[2].frequency if 2 in upconverters else NOT_SET,
        )

    def _deconvert_analog_inputs(
        self,
        inputs: Mapping[int, QuaConfig.MicrowaveAnalogInputPortDec],
        fem: MwFem,
    ) -> tuple[AnalogInputPortMicrowave, ...]:
        return tuple(self._deconvert_analog_input(_input, fem=fem, index=idx) for idx, _input in inputs.items())

    @staticmethod
    def _deconvert_analog_input(
        data: QuaConfig.MicrowaveAnalogInputPortDec, fem: MwFem, index: int
    ) -> AnalogInputPortMicrowave:
        lo_mode: ConfigOptional[str] = NOT_SET
        if data.HasField("lo_mode"):
            lo_mode = QuaConfig.MicrowaveAnalogInputPortDec.LoMode.Name(data.lo_mode).lower()
        return AnalogInputPortMicrowave(
            fem=fem,
            index=index,
            band=cast(Band, data.band),
            shareable=data.shareable,
            sampling_rate=data.samplingRate,
            gain_db=data.gain_db,
            downconverter_frequency=data.downconverter.frequency,
            lo_mode=lo_mode,  # type: ignore[arg-type]
        )

    def _deconvert_digital_outputs(
        self,
        outputs: Mapping[int, QuaConfig.DigitalOutputPortDec],
        fem: MwFem,
    ) -> tuple[DigitalOutputPortMicrowave, ...]:
        return tuple(self._deconvert_mw_digital_output(data, fem=fem, index=idx) for idx, data in outputs.items())

    @staticmethod
    def _deconvert_mw_digital_output(
        data: QuaConfig.DigitalOutputPortDec, fem: MwFem, index: int
    ) -> DigitalOutputPortMicrowave:
        return DigitalOutputPortMicrowave(
            fem=fem,
            index=index,
            shareable=data.shareable,
            inverted=data.inverted,
        )

    def _deconvert_digital_inputs(
        self,
        inputs: Mapping[int, QuaConfig.DigitalInputPortDec],
        fem: MwFem,
    ) -> tuple[DigitalInputPortMicrowave, ...]:
        return tuple(self._deconvert_digital_input(data, fem=fem, index=idx) for idx, data in inputs.items())

    def _deconvert_digital_input(
        self, data: QuaConfig.DigitalInputPortDec, fem: MwFem, index: int
    ) -> DigitalInputPortMicrowave:
        return DigitalInputPortMicrowave(
            fem=fem,
            index=index,
            shareable=data.shareable,
            deadtime=data.deadtime,
            threshold=data.threshold,
            polarity=self._get_polarity(data),
        )
