import dataclasses
from typing import List, Optional


@dataclasses.dataclass
class ImplementationInfo:
    name: str
    version: str
    url: str
    proto_version: Optional[str] = None


@dataclasses.dataclass
class QuaMachineInfo:
    capabilities: List[str]
    implementation: ImplementationInfo
