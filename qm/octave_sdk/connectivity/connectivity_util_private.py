from enum import Enum
from collections.abc import Collection
from typing import Union, Mapping, Optional, cast

from qm.grpc.octave.v1 import api_pb2
from qm.exceptions import QmQuaException
from qm.utils.protobuf_utils import which_one_of
from qm.octave_sdk.connectivity.connectivity_util import RFInputRFSource
from qm.octave_sdk.connectivity.exceptions import (
    ConnectivityException,
    RfSourceTypeException,
    InvalidIdentityException,
    ExternalInputTypeException,
)


# Convert gRPC RfSource oneof to local enum
class RfSourceType(str, Enum):
    rf_up_conv_output = "rf_up_conv_output"
    synth_output = "synth_output"
    external_input = "external_input"
    constant_source = "constant_source"


# Convert gRPC IfSource oneof to local enum
class IfSourceType(str, Enum):
    rf_downconv_if_source = "rf_downconv_if_source"
    if_downconv_if_source = "if_downconv_if_source"
    external_if_input = "external_if_input"
    constant_source = "constant_source"


def get_rf_source_type(rf_source: api_pb2.RFSource) -> str:
    one_of, _ = which_one_of(rf_source, "source")
    return one_of


def get_if_source_type(if_source: api_pb2.IFSource) -> str:
    one_of, _ = which_one_of(if_source, "source")
    return one_of


def validate_rf_source_type(
    rf_source: api_pb2.RFSource, rf_source_types: Collection[str], message: Optional[str]
) -> None:
    one_of, value = which_one_of(rf_source, "source")
    if one_of not in rf_source_types:
        raise InvalidIdentityException(f"{message} - {one_of}")


def get_rf_source_name(rf_source: api_pb2.RFSource) -> RFInputRFSource:
    name, value = which_one_of(rf_source, "source")
    if value is None:
        raise QmQuaException("source is not valid")

    if name == "rf_up_conv_output":
        try:
            return RFInputRFSource(cast(api_pb2.UpConvRFOutput, value).index)
        except KeyError:
            raise ConnectivityException("up converter index is not valid")
    elif name == "external_input":
        external_one_of, external_value = which_one_of(value, "input")
        if external_one_of == "rf_in_index":
            assert external_value is not None
            return RFInputRFSource.RF_in
        else:
            raise ExternalInputTypeException("external input is not valid")
    elif name == "constant_source":
        return RFInputRFSource.Off
    else:
        # "synth_output" not supported
        raise RfSourceTypeException("rf source is not supported")


def get_rf_source_from_synth_panel_output(rf_source: api_pb2.RFSource) -> api_pb2.SynthRFOutput:
    one_of, value = which_one_of(rf_source, "source")

    if isinstance(value, api_pb2.SynthRFOutput):
        return value
    else:
        # "rf_up_conv_output" and "constant_source"
        # and "external_input" are not supported
        raise RfSourceTypeException("rf source is not supported")


identity_object_to_module_ref_type_mapping: Mapping[  # type: ignore[name-defined]
    Union[
        type[api_pb2.RFUpConvIdentity],
        type[api_pb2.RFDownConvIdentity],
        type[api_pb2.IFDownConvIdentity],
        type[api_pb2.SynthIdentity],
    ],
    api_pb2.OctaveModule.ValueType,
] = {
    api_pb2.RFUpConvIdentity: api_pb2.OctaveModule.OCTAVE_MODULE_RF_UPCONVERTER,
    api_pb2.RFDownConvIdentity: api_pb2.OctaveModule.OCTAVE_MODULE_RF_DOWNCONVERTER,
    api_pb2.IFDownConvIdentity: api_pb2.OctaveModule.OCTAVE_MODULE_IF_DOWNCONVERTER,
    api_pb2.SynthIdentity: api_pb2.OctaveModule.OCTAVE_MODULE_SYNTHESIZER,
}
