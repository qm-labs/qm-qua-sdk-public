import dataclasses
from typing import Optional

MAX_MESSAGE_SIZE = 1024 * 1024 * 100  # 100 mb in bytes
BASE_TIMEOUT = 60


@dataclasses.dataclass
class ConnectionDetails:
    host: str
    port: int
    credentials: Optional[str] = dataclasses.field(default=None)
    max_message_size: int = dataclasses.field(default=MAX_MESSAGE_SIZE)
    timeout: float = dataclasses.field(default=BASE_TIMEOUT)
