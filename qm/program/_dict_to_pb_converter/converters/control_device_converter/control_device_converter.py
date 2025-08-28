from collections.abc import Mapping
from typing import Dict, Type, Union, Literal, TypeVar, cast

import betterproto

from qm.exceptions import ConfigValidationException
from qm.api.models.capabilities import OPX_FEM_IDX, QopCaps, ServerCapabilities
from qm.program._dict_to_pb_converter.base_converter import BaseDictToPbConverter
from qm.program._dict_to_pb_converter.converters.element_converter import DEFAULT_DUC_IDX
from qm.program._dict_to_pb_converter.converters.control_device_converter.analog_output_filters_converter import (
    AnalogOutputFiltersConverter,
)
from qm.type_hinting.config_types import (
    FEM_IDX,
    Band,
    Upconverter,
    LfFemConfigType,
    MwFemConfigType,
    ControllerConfigType,
    MwUpconverterConfigType,
    AnalogInputPortConfigType,
    AnalogOutputPortConfigType,
    DigitalInputPortConfigType,
    DigitalOutputPortConfigType,
    OPX1000ControllerConfigType,
    MwFemAnalogInputPortConfigType,
    MwFemAnalogOutputPortConfigType,
    AnalogOutputPortConfigTypeOctoDac,
)
from qm.grpc.qua_config import (
    QuaConfigFemTypes,
    QuaConfigDeviceDec,
    QuaConfigVoltageLevel,
    QuaConfigControllerDec,
    QuaConfigOctoDacFemDec,
    QuaConfigMicrowaveFemDec,
    QuaConfigAnalogInputPortDec,
    QuaConfigAnalogOutputPortDec,
    QuaConfigDigitalInputPortDec,
    QuaConfigDigitalOutputPortDec,
    QuaConfigUpConverterConfigDec,
    QuaConfigOctoDacAnalogOutputPortDec,
    QuaConfigDigitalInputPortDecPolarity,
    QuaConfigMicrowaveAnalogInputPortDec,
    QuaConfigMicrowaveAnalogOutputPortDec,
    QuaConfigOctoDacAnalogOutputPortDecOutputMode,
    QuaConfigOctoDacAnalogOutputPortDecSamplingRate,
    QuaConfigOctoDacAnalogOutputPortDecSamplingRateMode,
)

AnalogOutputType = TypeVar("AnalogOutputType", QuaConfigAnalogOutputPortDec, QuaConfigOctoDacAnalogOutputPortDec)
ControllerConfigTypeVar = TypeVar(
    "ControllerConfigTypeVar", QuaConfigOctoDacFemDec, QuaConfigControllerDec, QuaConfigMicrowaveFemDec
)


class ControlDeviceConverter(
    BaseDictToPbConverter[Union[ControllerConfigType, OPX1000ControllerConfigType], QuaConfigDeviceDec]
):
    def __init__(self, capabilities: ServerCapabilities, init_mode: bool) -> None:
        super().__init__(capabilities, init_mode)
        self._filters_converter = AnalogOutputFiltersConverter(capabilities, init_mode)

    def convert(self, input_data: Union[ControllerConfigType, OPX1000ControllerConfigType]) -> QuaConfigDeviceDec:
        return self.controlling_devices_to_pb(input_data)

    def controlling_devices_to_pb(
        self, data: Union[ControllerConfigType, OPX1000ControllerConfigType]
    ) -> QuaConfigDeviceDec:
        fems: Dict[int, QuaConfigFemTypes] = {}

        if "fems" in data:
            data = cast(OPX1000ControllerConfigType, data)
            # Here we assume that we don't declare OPX as FEM
            if set(data) & {"analog", "analog_outputs", "digital_outputs", "digital_inputs"}:
                raise Exception(
                    "'analog', 'analog_outputs', 'digital_outputs' and 'digital_inputs' are not allowed when 'fems' is present"
                )
            for k, v in data["fems"].items():
                if v.get("type") == "MW":
                    fems[int(k)] = self._mw_fem_to_pb(cast(MwFemConfigType, v))
                else:
                    fems[int(k)] = self._fem_to_pb(cast(LfFemConfigType, v))

        else:
            data = cast(ControllerConfigType, data)
            fems[OPX_FEM_IDX] = self._controller_to_pb(data)

        item = QuaConfigDeviceDec(fems=fems)
        return item

    def _controller_to_pb(self, data: ControllerConfigType) -> QuaConfigFemTypes:
        cont = QuaConfigControllerDec(type=data.get("type", "opx1"))
        cont = self._set_ports_in_config(cont, data)
        return QuaConfigFemTypes(opx=cont)

    def _fem_to_pb(self, data: LfFemConfigType) -> QuaConfigFemTypes:
        cont = QuaConfigOctoDacFemDec()
        cont = self._set_ports_in_config(cont, data)
        return QuaConfigFemTypes(octo_dac=cont)

    def _mw_fem_to_pb(self, data: MwFemConfigType) -> QuaConfigFemTypes:
        cont = QuaConfigMicrowaveFemDec()
        cont = self._set_ports_in_config(cont, data)
        return QuaConfigFemTypes(microwave=cont)

    def _set_ports_in_config(
        self,
        config: ControllerConfigTypeVar,
        data: Union[ControllerConfigType, LfFemConfigType, MwFemConfigType],
    ) -> ControllerConfigTypeVar:
        if "analog_outputs" in data:
            for analog_output_idx, analog_output_data in data["analog_outputs"].items():
                int_k = int(analog_output_idx)
                if isinstance(config, QuaConfigControllerDec):
                    analog_output_data = cast(AnalogOutputPortConfigType, analog_output_data)
                    config.analog_outputs[int_k] = self.analog_output_port_to_pb(
                        analog_output_data,
                        output_type=QuaConfigAnalogOutputPortDec,
                    )
                elif isinstance(config, QuaConfigOctoDacFemDec):
                    analog_output_data = cast(AnalogOutputPortConfigTypeOctoDac, analog_output_data)
                    config.analog_outputs[int_k] = self.opx_1000_analog_output_port_to_pb(analog_output_data)
                elif isinstance(config, QuaConfigMicrowaveFemDec):
                    analog_output_data = cast(MwFemAnalogOutputPortConfigType, analog_output_data)
                    config.analog_outputs[int_k] = self.mw_fem_analog_output_to_pb(analog_output_data)
                else:
                    raise ValueError(f"Unknown config type {type(config)}")

        if "analog_inputs" in data:
            if isinstance(config, (QuaConfigControllerDec, QuaConfigOctoDacFemDec)):
                for analog_input_idx, analog_input_data in data["analog_inputs"].items():
                    analog_input_data = cast(AnalogInputPortConfigType, analog_input_data)
                    config.analog_inputs[int(analog_input_idx)] = self.analog_input_port_to_pb(analog_input_data)
                    if isinstance(config, QuaConfigControllerDec):
                        sampling_rate = config.analog_inputs[int(analog_input_idx)].sampling_rate
                        if sampling_rate != 1e9:
                            raise ConfigValidationException(
                                f"Sampling rate of {sampling_rate} is not supported for OPX"
                            )
            elif isinstance(config, QuaConfigMicrowaveFemDec):
                for analog_input_idx, analog_input_data_mw in data["analog_inputs"].items():
                    analog_input_data_mw = cast(MwFemAnalogInputPortConfigType, analog_input_data_mw)
                    config.analog_inputs[int(analog_input_idx)] = self.mw_fem_analog_input_port_to_pb(
                        analog_input_data_mw
                    )
            else:
                raise ValueError(f"Unknown config type {type(config)}")

        if "digital_outputs" in data:
            for digital_output_idx, digital_output_data in data["digital_outputs"].items():
                config.digital_outputs[int(digital_output_idx)] = self.digital_output_port_to_pb(digital_output_data)

        if "digital_inputs" in data:
            for digital_input_idx, digital_input_data in data["digital_inputs"].items():
                config.digital_inputs[int(digital_input_idx)] = self.digital_input_port_to_pb(digital_input_data)

        return config

    def analog_input_port_to_pb(self, data: AnalogInputPortConfigType) -> QuaConfigAnalogInputPortDec:
        default_schema: AnalogInputPortConfigType = {
            "offset": 0.0,
            "shareable": False,
            "gain_db": 0,
            "sampling_rate": 1e9,
        }
        data_with_defaults = self._apply_defaults(data, default_schema=default_schema)
        analog_input = QuaConfigAnalogInputPortDec(
            offset=data_with_defaults.get("offset"),
            shareable=data_with_defaults.get("shareable"),
            gain_db=data_with_defaults.get("gain_db"),
            sampling_rate=data_with_defaults.get("sampling_rate"),
        )
        return analog_input

    def mw_fem_analog_input_port_to_pb(
        self, data: MwFemAnalogInputPortConfigType
    ) -> QuaConfigMicrowaveAnalogInputPortDec:
        if self._init_mode:
            self._validate_required_fields(data, ["band", "downconverter_frequency"], "microwave analog input port")

        default_schema: MwFemAnalogInputPortConfigType = {"sampling_rate": 1e9, "gain_db": 0, "shareable": False}
        data_with_defaults = self._apply_defaults(data, default_schema)

        analog_input = QuaConfigMicrowaveAnalogInputPortDec(
            sampling_rate=data_with_defaults.get("sampling_rate"),
            gain_db=data_with_defaults.get("gain_db"),
            shareable=data_with_defaults.get("shareable"),
            band=data_with_defaults.get("band"),
        )
        if "downconverter_frequency" in data_with_defaults:
            analog_input.downconverter.frequency = data_with_defaults["downconverter_frequency"]

        return analog_input

    def _validate_invalid_sampling_rate_and_upsampling_mode(self, data: AnalogOutputPortConfigTypeOctoDac) -> None:
        # We check that a user explicitly tried to put upsampling mode (not the default value) with a non-compatible sampling rate
        if "upsampling_mode" in data and "sampling_rate" in data and data["sampling_rate"] != 1e9:
            raise ConfigValidationException("'upsampling_mode' is only relevant for 'sampling_rate' of 1GHz.")

        # A sampling rate of 1GHZ goes hand in hand with an upsampling mode, so when updating one of these values,
        # it has to be compatible with the other.
        if not self._init_mode:
            if "sampling_rate" in data and data["sampling_rate"] == 1e9 and "upsampling_mode" not in data:
                raise ConfigValidationException(
                    "'upsampling_mode' should be provided when updating 'sampling_rate' to 1GHZ."
                )

            if "upsampling_mode" in data and "sampling_rate" not in data:
                raise ConfigValidationException(
                    "'sampling_rate' of 1GHZ should be provided when updating 'upsampling_mode'."
                )

    def analog_output_port_to_pb(
        self,
        data: AnalogOutputPortConfigType,
        output_type: Type[AnalogOutputType],
    ) -> AnalogOutputType:
        default_schema: AnalogOutputPortConfigType = {"shareable": False, "offset": 0.0, "delay": 0}
        data_with_defaults = self._apply_defaults(data, default_schema)

        analog_output = output_type(
            shareable=data_with_defaults.get("shareable"), offset=data_with_defaults.get("offset")
        )

        delay = data_with_defaults.get("delay")
        if delay is not None and delay < 0:
            raise ConfigValidationException(f"analog output delay cannot be a negative value, given value: {delay}")
        analog_output.delay = delay

        if "filter" in data_with_defaults:
            analog_output.filter = self._filters_converter.convert(data_with_defaults["filter"])

        if "crosstalk" in data_with_defaults:
            if self._capabilities.supports(QopCaps.config_v2) and isinstance(
                analog_output, QuaConfigOctoDacAnalogOutputPortDec
            ):
                crosstalk_in_pb = analog_output.crosstalk_v2.value
            else:
                crosstalk_in_pb = analog_output.crosstalk

            for k, v in data_with_defaults["crosstalk"].items():
                crosstalk_in_pb[int(k)] = v

        return analog_output

    def opx_1000_analog_output_port_to_pb(
        self,
        data: AnalogOutputPortConfigTypeOctoDac,
    ) -> QuaConfigOctoDacAnalogOutputPortDec:
        item = self.analog_output_port_to_pb(data, output_type=QuaConfigOctoDacAnalogOutputPortDec)
        self._validate_invalid_sampling_rate_and_upsampling_mode(data)

        default_schema: AnalogOutputPortConfigTypeOctoDac = {
            "sampling_rate": 1e9,
            "upsampling_mode": "mw",
            "output_mode": "direct",
        }
        data_with_defaults = self._apply_defaults(data, default_schema)

        self.update_sampling_rate_enum(item, data_with_defaults)

        if "output_mode" in data_with_defaults:
            item.output_mode = QuaConfigOctoDacAnalogOutputPortDecOutputMode[data_with_defaults.get("output_mode")]

        return item

    @staticmethod
    def update_sampling_rate_enum(
        item: QuaConfigOctoDacAnalogOutputPortDec, data_with_defaults: AnalogOutputPortConfigTypeOctoDac
    ) -> None:
        """Also update the upsampling mode, as its value is tightly correlated to the sampling rate."""
        sampling_rate = data_with_defaults.get("sampling_rate")
        if sampling_rate is not None:
            if sampling_rate == 1e9:
                item.sampling_rate = QuaConfigOctoDacAnalogOutputPortDecSamplingRate.GSPS1  # type: ignore[assignment]
                item.upsampling_mode = QuaConfigOctoDacAnalogOutputPortDecSamplingRateMode[
                    data_with_defaults["upsampling_mode"]
                ]

            elif sampling_rate == 2e9:
                item.sampling_rate = QuaConfigOctoDacAnalogOutputPortDecSamplingRate.GSPS2  # type: ignore[assignment]
                item.upsampling_mode = QuaConfigOctoDacAnalogOutputPortDecSamplingRateMode.unset  # type: ignore[assignment]

            else:
                raise ValueError("Sampling rate should be either 1e9 or 2e9")

    def get_upconverters(
        self, data: MwFemAnalogOutputPortConfigType, data_with_defaults: MwFemAnalogOutputPortConfigType
    ) -> Union[None, Dict[int, QuaConfigUpConverterConfigDec]]:
        upconverters = cast(Dict[int, QuaConfigUpConverterConfigDec], data_with_defaults.get("upconverters"))
        if "upconverter_frequency" in data and "upconverters" in data:
            raise ConfigValidationException("Use either 'upconverter_frequency' or 'upconverters' but not both")
        if "upconverter_frequency" in data:
            upconverters = {DEFAULT_DUC_IDX: QuaConfigUpConverterConfigDec(data["upconverter_frequency"])}
        else:
            if upconverters is not None:
                upconverters = {k: self.upconverter_config_dec_to_pb(v) for k, v in upconverters.items()}
            elif upconverters is None and self._init_mode:
                raise ConfigValidationException("You should declare at least one upconverter.")

        return cast(Union[None, Dict[int, QuaConfigUpConverterConfigDec]], upconverters)

    def mw_fem_analog_output_to_pb(
        self,
        data: MwFemAnalogOutputPortConfigType,
    ) -> QuaConfigMicrowaveAnalogOutputPortDec:
        if self._init_mode:
            self._validate_required_fields(data, ["band"], "microwave analog output port")

        default_schema: MwFemAnalogOutputPortConfigType = {
            "sampling_rate": 1e9,
            "full_scale_power_dbm": -11,
            "delay": 0,
            "shareable": False,
            "upconverters": {},
        }
        data_with_defaults = self._apply_defaults(data, default_schema)

        item = QuaConfigMicrowaveAnalogOutputPortDec(
            sampling_rate=data_with_defaults.get("sampling_rate"),
            full_scale_power_dbm=data_with_defaults.get("full_scale_power_dbm"),
            band=data_with_defaults.get("band"),
            delay=data_with_defaults.get("delay"),
            shareable=data_with_defaults.get("shareable"),
        )

        upconverters = self.get_upconverters(data, data_with_defaults)
        self._set_pb_attr_config_v2(item, upconverters, "upconverters", "upconverters_v2")

        return item

    def digital_input_port_to_pb(self, data: DigitalInputPortConfigType) -> QuaConfigDigitalInputPortDec:
        if self._init_mode:
            self._validate_required_fields(data, ["threshold", "polarity", "deadtime"], "digital input port")

        default_schema: DigitalInputPortConfigType = {"shareable": False}
        data_with_defaults = self._apply_defaults(data, default_schema=default_schema)

        digital_input = QuaConfigDigitalInputPortDec(
            shareable=data_with_defaults.get("shareable"),
            threshold=data_with_defaults.get("threshold"),
            level=QuaConfigVoltageLevel.LVTTL,  # type: ignore[arg-type]
            # The user is not supposed to edit this anymore, it should always be LVTTL. Up until now the gateway just always
            # put LVTTL here, but we are moving it here because the SDK is in charge of supplying defaults.
        )

        if "polarity" in data_with_defaults:
            if data_with_defaults["polarity"].upper() == "RISING":
                digital_input.polarity = QuaConfigDigitalInputPortDecPolarity.RISING  # type: ignore[assignment]
            elif data_with_defaults["polarity"].upper() == "FALLING":
                digital_input.polarity = QuaConfigDigitalInputPortDecPolarity.FALLING  # type: ignore[assignment]
            else:
                raise ConfigValidationException(f"Invalid polarity: {data_with_defaults['polarity']}")

        if "deadtime" in data_with_defaults:
            digital_input.deadtime = data_with_defaults["deadtime"]

        return digital_input

    def digital_output_port_to_pb(self, data: DigitalOutputPortConfigType) -> QuaConfigDigitalOutputPortDec:
        default_schema: DigitalOutputPortConfigType = {"shareable": False, "inverted": False}
        data_with_defaults = self._apply_defaults(data, default_schema)

        digital_output = QuaConfigDigitalOutputPortDec(
            shareable=data_with_defaults.get("shareable"),
            inverted=data_with_defaults.get("inverted"),
            # The only currently supported level is LVTTL, so we set it always
            level=QuaConfigVoltageLevel.LVTTL,  # type: ignore[arg-type]
        )

        return digital_output

    @staticmethod
    def upconverter_config_dec_to_pb(
        data: Union[MwUpconverterConfigType, QuaConfigUpConverterConfigDec]
    ) -> QuaConfigUpConverterConfigDec:
        if isinstance(data, QuaConfigUpConverterConfigDec):
            return data
        return QuaConfigUpConverterConfigDec(frequency=data["frequency"])

    def deconvert(self, output_data: QuaConfigDeviceDec) -> Union[ControllerConfigType, OPX1000ControllerConfigType]:

        if len(output_data.fems) == 1 and 1 in output_data.fems:
            _, opx = betterproto.which_one_of(output_data.fems[1], "fem_type_one_of")
            if isinstance(opx, QuaConfigControllerDec):
                return self._deconvert_controller(opx)

        return {
            "type": "opx1000",
            "fems": {cast(FEM_IDX, fem_idx): self._deconvert_fem(fem) for fem_idx, fem in output_data.fems.items()},
        }

    def _deconvert_controller(self, data: QuaConfigControllerDec) -> ControllerConfigType:
        return {
            "type": cast(Literal["opx", "opx1"], data.type),
            "analog_outputs": self._deconvert_controller_analog_outputs(data.analog_outputs),
            "analog_inputs": _deconvert_controller_analog_inputs(data.analog_inputs),
            "digital_outputs": _deconvert_controller_digital_outputs(data.digital_outputs),
            "digital_inputs": _deconvert_controller_digital_inputs(data.digital_inputs),
        }

    def _deconvert_fem(self, data: QuaConfigFemTypes) -> Union[LfFemConfigType, MwFemConfigType]:
        _, fem_config = betterproto.which_one_of(data, "fem_type_one_of")
        if isinstance(fem_config, QuaConfigOctoDacFemDec):
            return self._deconvert_octo_dac(fem_config)
        elif isinstance(fem_config, QuaConfigMicrowaveFemDec):
            return self._deconvert_mw_fem(fem_config)
        else:
            raise ValueError(f"Unknown FEM type - {fem_config}")

    def _deconvert_mw_fem(self, data: QuaConfigMicrowaveFemDec) -> MwFemConfigType:
        ret: MwFemConfigType = {"type": "MW"}
        if data.analog_outputs:
            ret["analog_outputs"] = self._deconvert_mw_analog_outputs(data.analog_outputs)
        if data.analog_inputs:
            ret["analog_inputs"] = _deconvert_mw_analog_inputs(data.analog_inputs)
        if data.digital_outputs:
            ret["digital_outputs"] = _deconvert_controller_digital_outputs(data.digital_outputs)
        if data.digital_inputs:
            ret["digital_inputs"] = _deconvert_controller_digital_inputs(data.digital_inputs)
        return ret

    def _deconvert_controller_analog_outputs(
        self, outputs: dict[int, QuaConfigAnalogOutputPortDec]
    ) -> Mapping[Union[int, str], AnalogOutputPortConfigType]:
        ret: Mapping[Union[int, str], AnalogOutputPortConfigType] = {
            int(name): self._deconvert_single_analog_output(data) for name, data in outputs.items()
        }
        return ret

    def _deconvert_single_analog_output(self, data: QuaConfigAnalogOutputPortDec) -> AnalogOutputPortConfigType:
        ret = cast(
            AnalogOutputPortConfigType,
            {
                "offset": data.offset,
                "delay": data.delay,
                "shareable": data.shareable,
                "filter": self._filters_converter.deconvert(data.filter),
                "crosstalk": data.crosstalk,
            },
        )
        return ret

    def _deconvert_mw_analog_outputs(
        self,
        outputs: Dict[int, QuaConfigMicrowaveAnalogOutputPortDec],
    ) -> Mapping[Union[int, str], MwFemAnalogOutputPortConfigType]:
        return {idx: self._deconvert_single_mw_analog_output(output) for idx, output in outputs.items()}

    def _deconvert_octo_dac(self, data: QuaConfigOctoDacFemDec) -> LfFemConfigType:
        ret: LfFemConfigType = {"type": "LF"}
        if data.analog_outputs:
            ret["analog_outputs"] = self._deconvert_octo_dac_fem_analog_outputs(data.analog_outputs)
        if data.analog_inputs:
            ret["analog_inputs"] = _deconvert_controller_analog_inputs(data.analog_inputs)
        if data.digital_outputs:
            ret["digital_outputs"] = _deconvert_controller_digital_outputs(data.digital_outputs)
        if data.digital_inputs:
            ret["digital_inputs"] = _deconvert_controller_digital_inputs(data.digital_inputs)
        return ret

    def _deconvert_single_octo_dac_fem_analog_output(
        self,
        data: QuaConfigOctoDacAnalogOutputPortDec,
    ) -> AnalogOutputPortConfigTypeOctoDac:
        ret = cast(
            AnalogOutputPortConfigTypeOctoDac,
            {
                "offset": data.offset,
                "delay": data.delay,
                "shareable": data.shareable,
                "filter": self._filters_converter.deconvert(data.filter),
                "crosstalk": data.crosstalk_v2.value
                if self._capabilities.supports(QopCaps.config_v2)
                else data.crosstalk,
            },
        )
        if data.sampling_rate:
            ret["sampling_rate"] = {1: 1e9, 2: 2e9}[data.sampling_rate]
        if data.upsampling_mode:
            ret["upsampling_mode"] = cast(
                Literal["mw", "pulse"], QuaConfigOctoDacAnalogOutputPortDecSamplingRateMode(data.upsampling_mode).name
            )
        if data.output_mode is not None:  # We check for "is not None" because the 0 value is valid
            ret["output_mode"] = cast(
                Literal["direct", "amplified"], QuaConfigOctoDacAnalogOutputPortDecOutputMode(data.output_mode).name
            )
        return ret

    def _deconvert_octo_dac_fem_analog_outputs(
        self,
        outputs: Dict[int, QuaConfigOctoDacAnalogOutputPortDec],
    ) -> Mapping[Union[int, str], AnalogOutputPortConfigTypeOctoDac]:
        ret: Mapping[Union[int, str], AnalogOutputPortConfigTypeOctoDac] = {
            int(name): self._deconvert_single_octo_dac_fem_analog_output(data) for name, data in outputs.items()
        }
        return ret

    def _deconvert_single_mw_analog_output(
        self, data: QuaConfigMicrowaveAnalogOutputPortDec
    ) -> MwFemAnalogOutputPortConfigType:
        upconverters = (
            data.upconverters_v2.value if self._capabilities.supports(QopCaps.config_v2) else data.upconverters
        )
        ret = cast(
            MwFemAnalogOutputPortConfigType,
            {
                "sampling_rate": data.sampling_rate,
                "full_scale_power_dbm": data.full_scale_power_dbm,
                "band": cast(Band, data.band),
                "delay": data.delay,
                "shareable": data.shareable,
                "upconverters": {cast(Upconverter, k): {"frequency": v.frequency} for k, v in upconverters.items()},
            },
        )
        return ret


def _deconvert_controller_analog_inputs(
    inputs: Mapping[int, QuaConfigAnalogInputPortDec]
) -> Mapping[Union[int, str], AnalogInputPortConfigType]:
    ret: Mapping[Union[int, str], AnalogInputPortConfigType] = {
        idx: _deconvert_controller_analog_input(data) for idx, data in inputs.items()
    }
    return ret


def _deconvert_controller_analog_input(data: QuaConfigAnalogInputPortDec) -> AnalogInputPortConfigType:
    ret = cast(
        AnalogInputPortConfigType,
        {
            "offset": data.offset,
            "gain_db": data.gain_db if data.gain_db is not None else 0,
            "shareable": data.shareable,
            "sampling_rate": 1e9,  # The only allowed value (the get_config always returns 0, but we know it is 1e9)
        },
    )
    return ret


def _deconvert_controller_digital_outputs(
    outputs: Dict[int, QuaConfigDigitalOutputPortDec]
) -> Mapping[Union[int, str], DigitalOutputPortConfigType]:
    return {idx: _deconvert_controller_digital_output(data) for idx, data in outputs.items()}


def _deconvert_controller_digital_output(data: QuaConfigDigitalOutputPortDec) -> DigitalOutputPortConfigType:
    to_return = cast(
        DigitalOutputPortConfigType,
        {
            "shareable": data.shareable,
            "inverted": data.inverted,
        },
    )
    return to_return


def _deconvert_controller_digital_inputs(
    inputs: Dict[int, QuaConfigDigitalInputPortDec]
) -> Mapping[Union[int, str], DigitalInputPortConfigType]:
    return {idx: _deconvert_digital_input(data) for idx, data in inputs.items()}


def _deconvert_digital_input(data: QuaConfigDigitalInputPortDec) -> DigitalInputPortConfigType:
    to_return = cast(
        DigitalInputPortConfigType,
        {
            "deadtime": data.deadtime,
            "threshold": data.threshold,
            "shareable": data.shareable,
        },
    )
    if data.polarity is not None:
        to_return["polarity"] = cast(
            Literal["RISING", "FALLING"], QuaConfigDigitalInputPortDecPolarity(data.polarity).name
        )

    return to_return


def _deconvert_mw_analog_inputs(
    inputs: Dict[int, QuaConfigMicrowaveAnalogInputPortDec]
) -> Mapping[Union[int, str], MwFemAnalogInputPortConfigType]:
    return {idx: _deconvert_single_mw_analog_input(_input) for idx, _input in inputs.items()}


def _deconvert_single_mw_analog_input(data: QuaConfigMicrowaveAnalogInputPortDec) -> MwFemAnalogInputPortConfigType:
    return cast(
        MwFemAnalogInputPortConfigType,
        {
            "band": cast(Literal[1, 2, 3], data.band),
            "shareable": data.shareable,
            "gain_db": data.gain_db,
            "sampling_rate": data.sampling_rate,
            "downconverter_frequency": data.downconverter.frequency,
        },
    )
