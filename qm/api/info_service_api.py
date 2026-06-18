from typing import Type

from qm.api.base_api import BaseApi
from qm.grpc.io.qualang.api.v1 import info_service_pb2
from qm.api.models.info import QuaMachineInfo, ImplementationInfo
from qm.grpc.io.qualang.api.v1.info_service_pb2_grpc import InfoServiceStub


class InfoServiceApi(BaseApi[InfoServiceStub]):
    @property
    def _stub_class(self) -> Type[InfoServiceStub]:
        return InfoServiceStub

    def get_info(self) -> QuaMachineInfo:
        request = info_service_pb2.GetInfoRequest()
        response = self._run(self._stub.GetInfo, request, timeout=self._timeout)

        return QuaMachineInfo(
            capabilities=response.capabilities,
            implementation=ImplementationInfo(
                name=response.implementation.name,
                version=response.implementation.version,
                url=response.implementation.url,
                proto_version=response.implementation.proto_version
                if response.implementation.HasField("proto_version")
                else None,
            ),
        )
