from typing import Optional

from qm.api.models.capabilities import QopCaps
from qm.qua._scope_management.scopes_manager import scopes_manager
from qm.qua._dsl.stream_processing.stream_processing import StreamType, ResultStreamSource, declare_stream


def _standardize_timestamp_label(timestamp_stream: Optional[StreamType]) -> Optional[str]:
    timestamp_label = None
    if isinstance(timestamp_stream, str):
        scope = scopes_manager.program_scope
        scope.add_used_capability(QopCaps.command_timestamps)
        timestamp_label = _declare_save(timestamp_stream).get_var_name()
    elif isinstance(timestamp_stream, ResultStreamSource):
        scopes_manager.program_scope.add_used_capability(QopCaps.command_timestamps)
        timestamp_label = timestamp_stream.get_var_name()
    return timestamp_label


def _declare_save(tag: str, add_legacy_timestamp: bool = False) -> ResultStreamSource:
    program_scope = scopes_manager.program_scope
    result_object = program_scope.declared_streams.get(tag, None)
    if result_object is None:
        result_object = declare_stream()
        program_scope.add_stream_declaration(tag, result_object)

        if add_legacy_timestamp:
            result_object.with_timestamps().save_all(tag)
        else:
            result_object.save_all(tag)
    return result_object
