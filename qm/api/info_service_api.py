from qm.utils.async_utils import run_async
from qm.api.models.server_details import ConnectionDetails
from qm.api.base_api import BaseApi, connection_error_handle
from qm.io.qualang.api.v1 import GetInfoRequest, InfoServiceStub
from qm.api.models.info import QuaMachineInfo, ImplementationInfo


@connection_error_handle()
class InfoServiceApi(BaseApi):
    def __init__(self, connection_details: ConnectionDetails):
        super().__init__(connection_details)
        self._stub = InfoServiceStub(self._channel)

    def get_info(self) -> QuaMachineInfo:
        request = GetInfoRequest()
        response = run_async(self._stub.get_info(request, timeout=self._timeout))

        return QuaMachineInfo(
            capabilities=response.capabilities,
            implementation=ImplementationInfo(
                name=response.implementation.name,
                version=response.implementation.version,
                url=response.implementation.url,
            ),
        )
