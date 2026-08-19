"""Issue the internal TLS material for the V1 POC host.

The applications refuse weak transport by design. The Management Register factory
requires `Encrypt=Strict` with certificate and hostname validation against
`sql-server`; each vault client requires its own CA bundle; and Control reaches
Review over HTTPS. None of that works without a trust anchor, so this issues one.

Scope is deliberately small. One offline certificate authority, valid only inside
this host, signs one server certificate per TLS listener. It is not a public CA,
it signs nothing outside the four declared names, and it grants no production,
source, model, or Pinecone authority.

Private keys are written under the ignored `var/` tree and are never printed,
logged, or recorded in the manifest. Only public material and fingerprints are.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

STAGING_ROOT = Path("var/tls")
MANIFEST_PATH = Path("infrastructure/poc/tls_material.json")
HOST_TRUST_DIRECTORY = "/etc/asklegal/tls"

_CA_COMMON_NAME = "AskLegal V1 POC Internal CA"
_CA_KEY_BITS = 4096
_SERVER_KEY_BITS = 2048
_CA_VALID_DAYS = 1825
_SERVER_VALID_DAYS = 397
# This host runs on local time east of UTC, so "today" locally can still be
# yesterday in UTC. Backdating the start absorbs that and any ordinary drift; a
# certificate that is not yet valid fails exactly as loudly as an expired one.
_CLOCK_SKEW_ALLOWANCE = dt.timedelta(days=1)

TLS_SERVICES: tuple[tuple[str, int], ...] = (
    ("sql-server", 10001),
    ("vault-primary", 3008),
    ("vault-recovery", 3009),
    ("review-api", 3007),
)


class CertificateError(RuntimeError):
    """One exact certificate-issuance failure carrying no key material."""


@dataclass(frozen=True, slots=True)
class IssuedCertificate:
    """Public facts about one issued certificate; never its private key."""

    name: str
    owner_uid: int
    subject_common_name: str
    serial_number: str
    not_before: str
    not_after: str
    sha256_fingerprint: str


def _validity_window(valid_days: int) -> tuple[dt.datetime, dt.datetime]:
    """Return a start backdated for clock skew and an exact expiry."""
    issued_at = dt.datetime.now(dt.UTC)
    return issued_at - _CLOCK_SKEW_ALLOWANCE, issued_at + dt.timedelta(days=valid_days)


def _private_key(bits: int) -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=bits)


def _write_private_key(path: Path, key: rsa.RSAPrivateKey) -> None:
    """Write one unencrypted PKCS#8 key readable only by its owner."""
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    path.chmod(0o600)


def _write_certificate(path: Path, certificate: x509.Certificate) -> None:
    path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    path.chmod(0o644)


def _fingerprint(certificate: x509.Certificate) -> str:
    return hashlib.sha256(certificate.public_bytes(serialization.Encoding.DER)).hexdigest()


def build_authority() -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
    """Create the offline internal authority that signs only V1 POC listeners."""
    key = _private_key(_CA_KEY_BITS)
    not_before, not_after = _validity_window(_CA_VALID_DAYS)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, _CA_COMMON_NAME)])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    return key, certificate


def build_server_certificate(
    name: str, authority_key: rsa.RSAPrivateKey, authority: x509.Certificate
) -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
    """Sign one server certificate valid only for the exact private service name."""
    key = _private_key(_SERVER_KEY_BITS)
    not_before, not_after = _validity_window(_SERVER_VALID_DAYS)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)]))
        .issuer_name(authority.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(name)]), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(authority_key.public_key()),
            critical=False,
        )
        .sign(authority_key, hashes.SHA256())
    )
    return key, certificate


def issue(root: Path) -> tuple[IssuedCertificate, ...]:
    """Issue the authority and every declared listener certificate into var/tls."""
    staging = root / STAGING_ROOT
    if staging.exists():
        message = f"{STAGING_ROOT} already exists; remove it before reissuing"
        raise CertificateError(message)
    staging.mkdir(parents=True)
    staging.chmod(0o700)

    authority_key, authority = build_authority()
    _write_private_key(staging / "internal-ca.key", authority_key)
    _write_certificate(staging / "internal-ca.crt", authority)

    issued: list[IssuedCertificate] = []
    for name, owner_uid in TLS_SERVICES:
        key, certificate = build_server_certificate(name, authority_key, authority)
        _write_private_key(staging / f"{name}.key", key)
        _write_certificate(staging / f"{name}.crt", certificate)
        issued.append(
            IssuedCertificate(
                name=name,
                owner_uid=owner_uid,
                subject_common_name=name,
                serial_number=f"{certificate.serial_number:x}",
                not_before=certificate.not_valid_before_utc.isoformat(),
                not_after=certificate.not_valid_after_utc.isoformat(),
                sha256_fingerprint=_fingerprint(certificate),
            )
        )
    _write_manifest(root, authority, issued)
    return tuple(issued)


def _write_manifest(
    root: Path, authority: x509.Certificate, issued: list[IssuedCertificate]
) -> None:
    document = {
        "schema_version": 1,
        "status": "INTERNAL_POC_TLS_ISSUED",
        "scope": "V1_POC_HOST_ONLY",
        "authority": {
            "common_name": _CA_COMMON_NAME,
            "serial_number": f"{authority.serial_number:x}",
            "not_before": authority.not_valid_before_utc.isoformat(),
            "not_after": authority.not_valid_after_utc.isoformat(),
            "sha256_fingerprint": _fingerprint(authority),
            "key_bits": _CA_KEY_BITS,
            "path_length": 0,
        },
        "host_trust_bundle": f"{HOST_TRUST_DIRECTORY}/internal-ca.crt",
        "staging_path": str(STAGING_ROOT),
        "private_keys_tracked_in_git": False,
        "public_trust_authority": False,
        "certificates": [
            {
                "name": item.name,
                "owner_uid": item.owner_uid,
                "subject_common_name": item.subject_common_name,
                "serial_number": item.serial_number,
                "not_before": item.not_before,
                "not_after": item.not_after,
                "sha256_fingerprint": item.sha256_fingerprint,
                "key_bits": _SERVER_KEY_BITS,
            }
            for item in issued
        ],
    }
    (root / MANIFEST_PATH).write_text(json.dumps(document, indent=2) + "\n")


def main() -> None:
    """Issue the internal TLS material and print only public facts."""
    argparse.ArgumentParser(description=__doc__).parse_args()
    root = Path(__file__).resolve().parents[1]
    for item in issue(root):
        print(f"{item.name} uid={item.owner_uid} sha256={item.sha256_fingerprint}")  # noqa: T201
    print(f"private keys staged under {STAGING_ROOT} and never printed")  # noqa: T201


if __name__ == "__main__":
    main()
