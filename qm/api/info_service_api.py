from typing import Type

from qm.api.base_api import BaseApi
from qm.io.qualang.api.v1 import GetInfoRequest, InfoServiceStub
from qm.api.models.info import QuaMachineInfo, ImplementationInfo


class InfoServiceApi(BaseApi[InfoServiceStub]):
    @property
    def _stub_class(self) -> Type[InfoServiceStub]:
        return InfoServiceStub

    def get_info(self) -> QuaMachineInfo:
        request = GetInfoRequest()
        response = self._run(self._stub.get_info(request, timeout=self._timeout))

        return QuaMachineInfo(
            capabilities=response.capabilities,
            implementation=ImplementationInfo(
                name=response.implementation.name,
                version=response.implementation.version,
                url=response.implementation.url,
            ),
        )
