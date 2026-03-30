from qm.grpc.octave.v1 import api_pb2
from qm.octave_sdk._octave_client import OctaveClient


# This function is shared between the octave and the octave_conflicts module, so it moved to this shared location
def _get_synth_state(client: OctaveClient, synth_index: int) -> api_pb2.SynthUpdate:
    response = client.acquire_module(
        api_pb2.ModuleReference(type=api_pb2.OctaveModule.OCTAVE_MODULE_SYNTHESIZER, index=synth_index)
    )
    synth_state = response.synth
    if isinstance(synth_state, api_pb2.SynthUpdate):
        return synth_state
    else:
        raise Exception("could not get synth state")
