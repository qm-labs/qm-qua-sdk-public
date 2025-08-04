import warnings
import dataclasses
from typing import Set, Optional, FrozenSet, Collection

from qm.api.models.info import QuaMachineInfo
from qm.exceptions import UnsupportedCapabilitiesError


@dataclasses.dataclass(frozen=True)
class Capability:
    qop_name: str
    from_qop_version: Optional[str] = None
    name_in_exception: Optional[str] = None

    @property
    def unsupported_exception_message(self) -> str:
        if self.name_in_exception:
            capability_name = self.name_in_exception
        else:
            capability_name = self.qop_name.replace("qm.", "")
            capability_name = capability_name.replace("_", " ")

        if self.from_qop_version is None:
            return f"{capability_name} is not supported in the installed QOP version."
        else:
            return f"{capability_name} is supported from QOP {self.from_qop_version} and above."


class QopCaps:
    job_streaming_state = Capability("qm.job_streaming_state")
    multiple_inputs_for_element = Capability("qm.multiple_inputs_for_element")
    analog_delay = Capability("qm.analog_delay")
    shared_oscillators = Capability("qm.shared_oscillators")
    crosstalk = Capability("qm.crosstalk")
    shared_ports = Capability("qm.shared_ports")
    input_stream = Capability("qm.input_stream")
    new_grpc_structure = Capability("qm.new_grpc_structure")
    double_frequency = Capability("qm.double_frequency")
    command_timestamps = Capability("qm.play_tag", "2.2", "timestamping commands")
    inverted_digital_output = Capability("qm.inverted_digital_output")
    sticky_elements = Capability("qm.sticky_elements")
    octave_reset = Capability("qm.octave_reset")
    fast_frame_rotation = Capability("qm.fast_frame_rotation", "2.2")
    keeping_dc_offsets = Capability("qm.keep_dc_offsets_when_closing")
    octave_management = Capability("support_octave_mgmnt", "2.5")

    # QOP3
    qop3 = Capability("__qop3", "3.0")
    opx1000_fems_return_1_based = Capability("1_based_fem", "3.0")
    waveform_report_endpoint = Capability("qm.waveform_report_endpoint", "3.3")
    exponential_iir_filter = Capability("qm.exponential_iir_filter", "3.3")
    broadcast = Capability("qm.broadcast", "3.3")
    chunk_streaming = Capability("qm.chunk_streaming", "3.3")
    fast_frame_rotation_deprecated = Capability("qm.fast_frame_rotation_deprecated", "3.3")
    config_v2 = Capability("qm.config_v2", "3.5")
    waveform_array = Capability("qm.waveform_array", "3.5")
    exponential_dc_gain_filter = Capability("qm.exponential_dc_gain_filter", "3.5")
    multiple_streams_fetching = Capability("qm.multiple_streams_fetching", "3.5")
    external_stream = Capability("qm.external_stream", "3.5", name_in_exception="declaring an external stream")

    @staticmethod
    def get_all() -> Set[Capability]:
        # Some built in methods are also in the class dictionary, so the 'if isinstance' filters them out
        return set(cap for cap in QopCaps.__dict__.values() if isinstance(cap, Capability))

    @staticmethod
    def qop2_caps() -> Set[Capability]:
        return set(cap for cap in QopCaps.get_all() if not cap.from_qop_version or float(cap.from_qop_version) < 3)


OPX_FEM_IDX = 1


class ServerCapabilities:
    def __init__(self, supported_capabilities: Collection[Capability]) -> None:
        self._supported_capabilities = frozenset(supported_capabilities)

    # These properties exist because the previous implementation of ServerCapabilities (used until this refactor in Jan 2025)
    # included a separate property for each capability. While most usages have been updated to call the 'supports'
    # function, these specific properties are still widely used in multiple places. To avoid extensive changes, their
    # usage was retained.
    supports_double_frequency = property(lambda self: self.supports(QopCaps.double_frequency))
    supports_sticky_elements = property(lambda self: self.supports(QopCaps.sticky_elements))

    @property
    def supported_capabilities(self) -> FrozenSet[Capability]:
        return self._supported_capabilities

    # This property is defined as a function to explicitly specify a return type, ensuring compatibility with mypy.
    @property
    def fem_number_in_simulator(self) -> int:
        return OPX_FEM_IDX if self.supports(QopCaps.qop3) else 0

    def supports(self, capability: Capability) -> bool:
        return capability in self._supported_capabilities

    def validate(self, capabilities: Collection[Capability]) -> None:
        """
        Validates if the capabilities passed are supported by the server.
        Raises an UnsupportedCapabilityError for the capabilities which are not supported.
        """
        if self.supports(QopCaps.fast_frame_rotation_deprecated) and QopCaps.fast_frame_rotation in capabilities:
            warnings.warn(
                "The fast_frame_rotation is deprecated as it is no longer faster than frame_rotation_2pi "
                "(and in fact, it is less efficient). It will be removed in future versions.",
                DeprecationWarning,
            )

        unsupported_capabilities = set(capabilities) - self._supported_capabilities
        if unsupported_capabilities:
            exception_message = "\nAlso: ".join(
                [capability.unsupported_exception_message for capability in unsupported_capabilities]
            )
            raise UnsupportedCapabilitiesError(exception_message)

    @classmethod
    def build(cls, qua_implementation: Optional[QuaMachineInfo] = None) -> "ServerCapabilities":
        qop_caps = qua_implementation.capabilities if qua_implementation is not None else list()
        supported_capabilities = set(cap for cap in QopCaps.get_all() if cap.qop_name in qop_caps)

        if QopCaps.qop3.qop_name in qop_caps:
            # Doing this in case all the QOP2 caps are not added by default when it is a QOP3 machine
            supported_capabilities.update(QopCaps.qop2_caps())

        return cls(supported_capabilities)
