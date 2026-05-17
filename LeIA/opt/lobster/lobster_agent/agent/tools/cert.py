from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from cryptography import x509
from cryptography.x509.oid import NameOID

from lobster_agent.domain.models import CertificateInfo


@runtime_checkable
class TLSSecretLister(Protocol):
    list_tls_secrets: Callable[[], Awaitable[list[object]]]


def parse_certificate_pem(
    pem_data: str | bytes,
    domain: str,
    source: str | None = None,
) -> CertificateInfo:
    pem_bytes = pem_data.encode() if isinstance(pem_data, str) else pem_data
    cert = x509.load_pem_x509_certificate(pem_bytes)
    expires_at = _certificate_not_valid_after(cert)
    days_until_expiration = int((expires_at - datetime.now(UTC)).total_seconds() // 86400)
    return CertificateInfo(
        domain=domain,
        issuer=_issuer_summary(cert),
        expires_at=expires_at,
        days_until_expiration=days_until_expiration,
        is_expired=expires_at <= datetime.now(UTC),
        source=source,
    )


async def list_certificates_from_tls_secrets(k8s_client: object) -> list[CertificateInfo]:
    if not isinstance(k8s_client, TLSSecretLister):
        # TODO: K8sClient does not expose list_tls_secrets yet. Add it in the certificate
        # integration block after the final Secret read contract is decided.
        return []

    certs: list[CertificateInfo] = []
    for secret in await k8s_client.list_tls_secrets():
        certs.extend(_certificates_from_secret(secret))
    return certs


def find_expiring_certs(certs: list[CertificateInfo], days: int = 30) -> list[CertificateInfo]:
    return [cert for cert in certs if cert.days_until_expiration <= days]


def get_cert_expiration(certs: list[CertificateInfo], domain: str) -> CertificateInfo | None:
    for cert in certs:
        if cert.domain == domain:
            return cert
    return None


def _certificate_not_valid_after(cert: x509.Certificate) -> datetime:
    expires_at = getattr(cert, "not_valid_after_utc", None)
    if isinstance(expires_at, datetime):
        return expires_at
    return cert.not_valid_after.replace(tzinfo=UTC)


def _issuer_summary(cert: x509.Certificate) -> str | None:
    attributes = cert.issuer.get_attributes_for_oid(NameOID.COMMON_NAME)
    if attributes:
        return str(attributes[0].value)
    return cert.issuer.rfc4514_string() or None


def _certificates_from_secret(secret: object) -> list[CertificateInfo]:
    # TODO: Parse Kubernetes Secret shape once K8sClient exposes read-only TLS Secret access.
    _ = secret
    return []
