# These imports are maintained for backwards compatibility with the validation repository, despite the restriction on importing from "_dsl".
# We have to do this temporarily because our ci/cd pipeline runs the validation framework ('main' branch), so until the 'main' branch of the validation repository is updated to use the new imports, we need to keep these imports here.
# TODO: Remove these once the imports in the validation repository are corrected, which should be addressed as soon as possible.
from qm.qua._expressions import QuaVariable
from qm.qua._dsl.measure.measure_process_factories import time_tagging
from qm.qua._dsl.stream_processing.stream_processing import ResultStreamSource as _ResultSource
from qm.qua._dsl.amplitude import _PulseAmp  # This is being used by QUAM, check with Serwan before removing

_Variable = QuaVariable  # This alias is for supporting an import that appears in QUA-lang tools. TODO: Remove this alias once the import in QUA-lang tools is corrected.
