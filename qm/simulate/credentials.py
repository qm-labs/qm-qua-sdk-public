import ssl
from typing import Optional
from dataclasses import field, dataclass

from qm.type_hinting.general import PathLike
from qm.exceptions import InvalidCredentialsError


@dataclass(frozen=True)
class CredentialOverrides:
    certificate_path: PathLike = field(default="")
    client_cert_path: PathLike = field(default="")
    client_key_path: PathLike = field(default="")
    verify_mode: ssl.VerifyMode = field(default=ssl.CERT_REQUIRED)
    check_hostname: bool = field(default=True)


def validate_client_cert_pair(client_cert_path: Optional[PathLike], client_key_path: Optional[PathLike]) -> None:
    if bool(client_cert_path) != bool(client_key_path):
        missing = "client_key_path" if client_cert_path else "client_cert_path"
        raise InvalidCredentialsError(
            f"Mutual TLS requires both 'client_cert_path' and 'client_key_path', "
            f"but '{missing}' is missing. Provide both or neither."
        )


def create_credentials(credentials_override: Optional[CredentialOverrides] = None) -> ssl.SSLContext:
    import certifi

    context = ssl.create_default_context(
        purpose=ssl.Purpose.SERVER_AUTH,
        cafile=certifi.where(),
    )
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.set_ciphers("ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20")
    context.set_alpn_protocols(["h2"])
    if ssl.HAS_NPN:
        context.set_npn_protocols(["h2"])

    if credentials_override:
        if credentials_override.certificate_path:
            context.load_verify_locations(credentials_override.certificate_path)
        if credentials_override.client_cert_path and credentials_override.client_key_path:
            context.load_cert_chain(
                certfile=credentials_override.client_cert_path,
                keyfile=credentials_override.client_key_path,
            )
        context.verify_mode = credentials_override.verify_mode
        context.check_hostname = credentials_override.check_hostname

    return context


__all__ = ["create_credentials", "CredentialOverrides"]
