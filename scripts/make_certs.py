"""Generate a local CA and a server certificate for LAN HTTPS.

Creates, under ``certs/``:
    ca.crt / ca.key        the local certificate authority
    server.crt / server.key  the cert uvicorn serves, signed by that CA

The server cert carries Subject Alternative Names for the LAN IP, localhost and
127.0.0.1 — browsers and Android require the name you connect to be in the SAN list,
and an IP must be an IPAddress entry (not a DNS one).

Usage:
    py -3 scripts/make_certs.py                 # auto-detects the LAN IP
    py -3 scripts/make_certs.py 192.168.1.100 fittrack.local
"""

from __future__ import annotations

import datetime as dt
import ipaddress
import socket
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

OUT = Path(__file__).resolve().parent.parent / "certs"
# Android rejects leaf certificates valid for more than 825 days.
SERVER_DAYS = 800
CA_DAYS = 3650


def _detect_lan_ip() -> str:
    """Find the IP this machine uses to reach the LAN (no traffic is actually sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()


def _write(path: Path, data: bytes, secret: bool = False) -> None:
    path.write_bytes(data)
    if secret:
        try:
            path.chmod(0o600)
        except OSError:
            pass  # best effort on Windows
    print(f"  {path.relative_to(OUT.parent)}")


def main(argv: list[str]) -> int:
    hosts = argv[1:] or [_detect_lan_ip()]
    OUT.mkdir(parents=True, exist_ok=True)

    now = dt.datetime.now(dt.timezone.utc)

    # --- CA ---
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
    ca_name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "FitTrack Local CA"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "FitTrack"),
    ])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=CA_DAYS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, key_cert_sign=True, crl_sign=True,
                content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=False,
                encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )

    # --- server cert ---
    san: list[x509.GeneralName] = [x509.DNSName("localhost")]
    seen_ips = set()
    for host in hosts:
        try:
            ip = ipaddress.ip_address(host)
            if ip not in seen_ips:
                san.append(x509.IPAddress(ip))
                seen_ips.add(ip)
        except ValueError:
            san.append(x509.DNSName(host))
    loopback = ipaddress.ip_address("127.0.0.1")
    if loopback not in seen_ips:
        san.append(x509.IPAddress(loopback))

    srv_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    srv_cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hosts[0])]))
        .issuer_name(ca_cert.subject)
        .public_key(srv_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=SERVER_DAYS))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )

    print("Writing certificates:")
    _write(OUT / "ca.crt", ca_cert.public_bytes(serialization.Encoding.PEM))
    _write(
        OUT / "ca.key",
        ca_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
        secret=True,
    )
    _write(OUT / "server.crt", srv_cert.public_bytes(serialization.Encoding.PEM))
    _write(
        OUT / "server.key",
        srv_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
        secret=True,
    )

    names = ", ".join(
        str(getattr(n, "value", n)) for n in san
    )
    print(f"\nValid for: {names}")
    print(f"Server cert expires: {srv_cert.not_valid_after_utc:%Y-%m-%d}")
    print(f"\nRun the server with TLS:")
    print(
        "  set PYTHONPATH=src && py -3 -B -m uvicorn fitness.web.app:create_app --factory "
        "--host 0.0.0.0 --port 8443 "
        "--ssl-keyfile certs/server.key --ssl-certfile certs/server.crt"
    )
    print(f"\nThen browse to: https://{hosts[0]}:8443/static/index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
