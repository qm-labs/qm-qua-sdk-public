from qm.grpc.qm.pb import job_manager_pb2


class DeprecatedJobManagerServiceStub(object):
    def __init__(self, channel):
        """Constructor.

        Args:
            channel: A grpc.Channel.
        """
        self.GetElementCorrection = channel.unary_unary(
            "/qm.grpc.jobManager.JobManagerService/GetElementCorrection",
            request_serializer=job_manager_pb2.GetElementCorrectionRequest.SerializeToString,
            response_deserializer=job_manager_pb2.GetElementCorrectionResponse.FromString,
            _registered_method=True,
        )

        self.SetElementCorrection = channel.unary_unary(
            "/qm.grpc.jobManager.JobManagerService/SetElementCorrection",
            request_serializer=job_manager_pb2.SetElementCorrectionRequest.SerializeToString,
            response_deserializer=job_manager_pb2.SetElementCorrectionResponse.FromString,
            _registered_method=True,
        )

        self.InsertInputStream = channel.unary_unary(
            "/qm.grpc.jobManager.JobManagerService/InsertInputStream",
            request_serializer=job_manager_pb2.InsertInputStreamRequest.SerializeToString,
            response_deserializer=job_manager_pb2.InsertInputStreamResponse.FromString,
            _registered_method=True,
        )
