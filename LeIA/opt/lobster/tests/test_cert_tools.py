from datetime import UTC, datetime, timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from lobster_agent.agent.tools.cert import (
    find_expiring_certs,
    get_cert_expiration,
    list_certificates_from_tls_secrets,
    parse_certificate_pem,
)
from lobster_agent.domain.models import CertificateInfo


def build_self_signed_cert(common_name: str, expires_at: datetime) -> bytes:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = min(datetime.now(UTC), expires_at - timedelta(minutes=1))
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(expires_at)
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(common_name)]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM)


def test_parse_certificate_pem_parses_self_signed_certificate() -> None:
    expires_at = datetime.now(UTC) + timedelta(days=10)
    pem = build_self_signed_cert("example.test", expires_at)

    result = parse_certificate_pem(pem, domain="example.test", source="secret/example")

    assert result.domain == "example.test"
    assert result.issuer == "example.test"
    assert result.expires_at.tzinfo == UTC
    assert result.days_until_expiration in {9, 10}
    assert result.is_expired is False
    assert result.source == "secret/example"


def test_parse_certificate_pem_marks_expired_certificate() -> None:
    expires_at = datetime.now(UTC) - timedelta(days=1)
    pem = build_self_signed_cert("expired.test", expires_at)

    result = parse_certificate_pem(pem, domain="expired.test")

    assert result.is_expired is True
    assert result.days_until_expiration <= -1


def test_find_expiring_certs_filters_by_days() -> None:
    now = datetime.now(UTC)
    certs = [
        CertificateInfo(
            domain="soon.test",
            expires_at=now + timedelta(days=5),
            days_until_expiration=5,
        ),
        CertificateInfo(
            domain="later.test",
            expires_at=now + timedelta(days=60),
            days_until_expiration=60,
        ),
    ]

    assert [cert.domain for cert in find_expiring_certs(certs, days=30)] == ["soon.test"]


def test_get_cert_expiration_finds_domain() -> None:
    cert = CertificateInfo(
        domain="example.test",
        expires_at=datetime.now(UTC) + timedelta(days=30),
        days_until_expiration=30,
    )

    assert get_cert_expiration([cert], "example.test") == cert
    assert get_cert_expiration([cert], "missing.test") is None


async def test_list_certificates_from_tls_secrets_returns_empty_without_contract() -> None:
    assert await list_certificates_from_tls_secrets(object()) == []
