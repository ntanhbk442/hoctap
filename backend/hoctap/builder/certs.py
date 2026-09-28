"""`hoctap certs`: an mkcert-signed certificate for the PC's LAN IP.

`generate()` never invokes `mkcert` directly in a way tests cannot intercept: the
subprocess runner and the `PATH` lookup are both injectable. No automatic renewal, no
ACME/Let's Encrypt — mkcert only, per architecture AD-12.
"""

from __future__ import annotations

import ipaddress
import re
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

MKCERT_INSTALL_URL = "https://github.com/FiloSottile/mkcert#installation"
CERT_FILENAME = "cert.pem"
KEY_FILENAME = "key.pem"

_HOSTNAME_RE = re.compile(
    r"^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$"
)

RunFunc = Callable[..., "subprocess.CompletedProcess[str]"]
WhichFunc = Callable[[str], "str | None"]


class CertsError(Exception):
    """A `certs` failure. `code` is the CLI exit code; `message` is already bilingual."""

    def __init__(self, message: str, code: int) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class MkcertNotFound(CertsError):
    def __init__(self, executable: str = "mkcert") -> None:
        super().__init__(
            f"Không tìm thấy lệnh `{executable}` (mkcert) trong PATH / `{executable}` "
            f"(mkcert) is not on PATH. Cài đặt mkcert trước / install mkcert first: "
            f"{MKCERT_INSTALL_URL}",
            code=2,
        )


class InvalidIp(CertsError):
    def __init__(self, ip: str) -> None:
        super().__init__(
            f"VALIDATION_ERROR: --ip không hợp lệ / --ip is not a valid IPv4 address: {ip!r}",
            code=2,
        )


class InvalidHostname(CertsError):
    def __init__(self, hostname: str) -> None:
        super().__init__(
            f"VALIDATION_ERROR: --hostname không hợp lệ / --hostname is not a valid "
            f"hostname: {hostname!r}",
            code=2,
        )


class CertsExist(CertsError):
    def __init__(self, cert_dir: Path) -> None:
        super().__init__(
            f"Đã có chứng chỉ tại {cert_dir} / certificate files already exist at "
            f"{cert_dir}; dùng --force để ghi đè / use --force to overwrite. "
            "Nothing was overwritten.",
            code=1,
        )


class MkcertFailed(CertsError):
    def __init__(self, command: Sequence[str], detail: str) -> None:
        super().__init__(
            f"Lỗi khi chạy mkcert / mkcert failed ({' '.join(command)}): {detail}",
            code=1,
        )


class CertDirError(CertsError):
    def __init__(self, cert_dir: Path, detail: str) -> None:
        super().__init__(
            f"Không tạo được thư mục {cert_dir} / could not create directory "
            f"{cert_dir}: {detail}",
            code=1,
        )


@dataclass(frozen=True)
class CertPaths:
    cert_file: Path
    key_file: Path


def validate_ipv4(ip: str) -> str:
    """Raises `InvalidIp` unless `ip` is a syntactically valid IPv4 address."""
    try:
        ipaddress.IPv4Address(ip)
    except ValueError as exc:
        raise InvalidIp(ip) from exc
    return ip


def validate_hostname(hostname: str) -> str:
    """Raises `InvalidHostname` unless `hostname` looks like a syntactically valid one."""
    if not _HOSTNAME_RE.match(hostname):
        raise InvalidHostname(hostname)
    return hostname


def _run_mkcert(command: list[str], run: RunFunc) -> None:
    try:
        result = run(command, capture_output=True, text=True)
    except OSError as exc:
        raise MkcertFailed(command, str(exc)) from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip() or f"exit code {result.returncode}"
        raise MkcertFailed(command, detail)


def generate(
    ip: str,
    hostname: str | None,
    cert_dir: Path,
    force: bool,
    *,
    mkcert_executable: str = "mkcert",
    run: RunFunc = subprocess.run,
    which: WhichFunc = shutil.which,
) -> CertPaths:
    """Generates `cert_dir/cert.pem` and `cert_dir/key.pem` for `ip` (and `hostname`).

    Validates `ip` before shelling out. Requires `mkcert_executable` on PATH (checked with
    `which`, injectable for tests). Refuses to overwrite existing files unless `force`.
    Runs `mkcert -install` (idempotent) then the certificate generation, both through `run`
    (injectable; never the real `mkcert` in tests).
    """
    validate_ipv4(ip)
    if hostname:
        validate_hostname(hostname)
    if which(mkcert_executable) is None:
        raise MkcertNotFound(mkcert_executable)

    cert_file = cert_dir / CERT_FILENAME
    key_file = cert_dir / KEY_FILENAME
    if not force and (cert_file.exists() or key_file.exists()):
        raise CertsExist(cert_dir)

    try:
        cert_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise CertDirError(cert_dir, str(exc)) from exc
    _run_mkcert([mkcert_executable, "-install"], run)

    names = [ip, *([hostname] if hostname else []), "localhost", "127.0.0.1"]
    _run_mkcert(
        [mkcert_executable, "-cert-file", str(cert_file), "-key-file", str(key_file), *names],
        run,
    )
    return CertPaths(cert_file=cert_file, key_file=key_file)
