import warnings
from typing import Union, cast

from qm.grpc.qm.pb import inc_qua_config_pb2
from qm.api.models.capabilities import QopCaps
from qm.utils.protobuf_utils import proto_repeated_to_list
from qm.program._dict_to_pb_converter.base_converter import BaseDictToPbConverter
from qm.type_hinting.config_types import (
    AnalogOutputFilterConfigType,
    AnalogOutputFilterConfigTypeQop33,
    AnalogOutputFilterConfigTypeQop35,
)


class AnalogOutputFiltersConverter(
    BaseDictToPbConverter[
        Union[AnalogOutputFilterConfigType, AnalogOutputFilterConfigTypeQop33, AnalogOutputFilterConfigTypeQop35],
        inc_qua_config_pb2.QuaConfig.AnalogOutputPortFilter,
    ]
):
    def convert(
        self,
        input_data: Union[
            AnalogOutputFilterConfigType, AnalogOutputFilterConfigTypeQop33, AnalogOutputFilterConfigTypeQop35
        ],
    ) -> inc_qua_config_pb2.QuaConfig.AnalogOutputPortFilter:
        return self._analog_output_port_filters_to_pb(input_data)

    @staticmethod
    def _validate_high_pass_param_in_qop35(data: AnalogOutputFilterConfigTypeQop35) -> None:
        if data.get("high_pass") is not None and data.get("exponential_dc_gain") is None:
            value = cast(AnalogOutputFilterConfigTypeQop33, data)["high_pass"]
            warnings.warn(
                f"Setting the `high_pass` to {value} is equivalent to setting the `exponential_dc_gain` field "
                f"to 0 and adding an exponential filter of (1, {value}). The `high_pass` field will be deprecated in QUA 2.0.",
                DeprecationWarning,
            )

    def _set_exponential_param(
        self,
        item: inc_qua_config_pb2.QuaConfig.AnalogOutputPortFilter,
        data_with_defaults: Union[AnalogOutputFilterConfigTypeQop33, AnalogOutputFilterConfigTypeQop35],
    ) -> None:
        if "exponential" in data_with_defaults:
            exponential = [
                inc_qua_config_pb2.QuaConfig.ExponentialParameters(amplitude=exp_params[0], time_constant=exp_params[1])
                for exp_params in data_with_defaults["exponential"]
            ]
            self._set_pb_attr_config_v2(item.iir, exponential, "exponential", "exponential_v2")

    def _set_high_pass_param(
        self,
        item: inc_qua_config_pb2.QuaConfig.AnalogOutputPortFilter,
        data_with_defaults: AnalogOutputFilterConfigTypeQop33,
    ) -> None:
        if "high_pass" in data_with_defaults:
            self._set_pb_attr_config_v2(
                item.iir,
                data_with_defaults["high_pass"],
                "high_pass",
                "high_pass_v2",
                allow_nones=True,
                create_container=inc_qua_config_pb2.QuaConfig.IirFilter.HighPassContainer,
            )

    def _analog_output_port_filters_qop33_to_pb(
        self,
        data: Union[AnalogOutputFilterConfigTypeQop33, AnalogOutputFilterConfigTypeQop35],
    ) -> inc_qua_config_pb2.QuaConfig.AnalogOutputPortFilter:
        default_schema: AnalogOutputFilterConfigTypeQop33 = {"feedforward": [], "exponential": [], "high_pass": None}
        data_with_defaults = self._apply_defaults(
            cast(AnalogOutputFilterConfigTypeQop33, data), default_schema=default_schema
        )

        item = inc_qua_config_pb2.QuaConfig.AnalogOutputPortFilter()
        self._set_pb_attr_config_v2(item, data_with_defaults.get("feedforward"), "feedforward", "feedforward_v2")
        self._set_exponential_param(item, data_with_defaults)
        self._set_high_pass_param(item, data_with_defaults)

        if self._capabilities.supports(QopCaps.exponential_dc_gain_filter):
            data_with_defaults_35 = self._apply_defaults(
                cast(AnalogOutputFilterConfigTypeQop35, data_with_defaults),
                default_schema={"exponential_dc_gain": None},
            )
            data_with_defaults_35 = cast(  # For mypy, we already did cast in the previous line
                AnalogOutputFilterConfigTypeQop35, data_with_defaults_35
            )
            self._validate_high_pass_param_in_qop35(data_with_defaults_35)
            self._set_exponential_dc_gain_param(item, data_with_defaults_35)
        else:
            self._validate_unsupported_params(
                data_with_defaults,
                unsupported_params=["exponential_dc_gain"],
                supported_params=["high_pass"],
                supported_from=QopCaps.exponential_dc_gain_filter.from_qop_version,
            )

        return item

    @staticmethod
    def _set_exponential_dc_gain_param(
        item: inc_qua_config_pb2.QuaConfig.AnalogOutputPortFilter,
        data_with_defaults: AnalogOutputFilterConfigTypeQop35,
    ) -> None:
        if "exponential_dc_gain" in data_with_defaults:
            exponential_dc_gain = data_with_defaults.get("exponential_dc_gain")
            item.iir.exponential_dc_gain.CopyFrom(
                inc_qua_config_pb2.QuaConfig.IirFilter.ExponentialDcGainContainer(value=exponential_dc_gain)
            )

    def _analog_output_port_filters_to_pb(
        self,
        data: Union[AnalogOutputFilterConfigType, AnalogOutputFilterConfigTypeQop33, AnalogOutputFilterConfigTypeQop35],
    ) -> inc_qua_config_pb2.QuaConfig.AnalogOutputPortFilter:

        if self._capabilities.supports(QopCaps.exponential_iir_filter):
            self._validate_unsupported_params(
                data,
                unsupported_params=["feedback"],
                supported_params=["high_pass", "exponential"],
                supported_until=QopCaps.exponential_iir_filter.from_qop_version,
            )
            return self._analog_output_port_filters_qop33_to_pb(cast(AnalogOutputFilterConfigTypeQop33, data))
        else:
            self._validate_unsupported_params(
                data,
                unsupported_params=["exponential", "high_pass"],
                supported_params=["feedback"],
                supported_from=QopCaps.exponential_iir_filter.from_qop_version,
            )

            data = cast(AnalogOutputFilterConfigType, data)
            return inc_qua_config_pb2.QuaConfig.AnalogOutputPortFilter(
                feedforward=data.get("feedforward", []), feedback=data.get("feedback", [])
            )

    def deconvert(
        self, output_data: inc_qua_config_pb2.QuaConfig.AnalogOutputPortFilter
    ) -> Union[AnalogOutputFilterConfigTypeQop35, AnalogOutputFilterConfigTypeQop33, AnalogOutputFilterConfigType]:
        if self._capabilities.supports(QopCaps.exponential_iir_filter):
            raw_exponential = (
                output_data.iir.exponential_v2.value
                if self._capabilities.supports(QopCaps.config_v2)
                else output_data.iir.exponential
            )
            exponential = [(exp_params.amplitude, exp_params.time_constant) for exp_params in raw_exponential]
            feedforward = (
                output_data.feedforward_v2.value
                if self._capabilities.supports(QopCaps.config_v2)
                else output_data.feedforward
            )

            ret33: AnalogOutputFilterConfigTypeQop33 = {
                "feedforward": proto_repeated_to_list(feedforward),
                "exponential": exponential,
            }

            if self._capabilities.supports(QopCaps.config_v2):
                # We handle both cases: the container being None (as likely returned by the Gateway),
                # and an initialized container with value=None.
                ret33["high_pass"] = (
                    output_data.iir.high_pass_v2.value if output_data.iir.HasField("high_pass_v2") else None
                )
            else:
                ret33["high_pass"] = output_data.iir.high_pass if output_data.iir.HasField("high_pass") else None

            if self._capabilities.supports(QopCaps.exponential_dc_gain_filter):
                exponential_dc_gain = (
                    output_data.iir.exponential_dc_gain.value
                    if output_data.iir.HasField("exponential_dc_gain")
                    and output_data.iir.exponential_dc_gain.HasField("value")
                    else None
                )
                ret35 = cast(AnalogOutputFilterConfigTypeQop35, {**ret33, "exponential_dc_gain": exponential_dc_gain})
                return ret35

            return ret33
        else:
            ret: AnalogOutputFilterConfigType = {
                "feedforward": proto_repeated_to_list(output_data.feedforward),
                "feedback": proto_repeated_to_list(output_data.feedback),
            }
            return ret
