"""Story 1.11: `hoctap certs` and the `generate()` it wraps.

`mkcert` is always mocked (a fake `run`/`which`) -- never invoked for real, so this runs
fine on Linux/WSL and CI.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from hoctap.builder.certs import (
    CertDirError,
    CertsExist,
    InvalidHostname,
    InvalidIp,
    MkcertFailed,
    MkcertNotFound,
    generate,
    validate_hostname,
    validate_ipv4,
)
from hoctap.cli import main as cli_main


def _ok(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")


def _which_present(_executable: str) -> str:
    return "/usr/bin/mkcert"


def _which_absent(_executable: str) -> None:
    return None


class _RecordingRun:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        self.calls.append(command)
        return _ok()


# --- validate_ipv4 ------------------------------------------------------------------


def test_validate_ipv4_ok() -> None:
    assert validate_ipv4("192.168.1.50") == "192.168.1.50"


@pytest.mark.parametrize("bad", ["not-an-ip", "999.1.1.1", "1.2.3", "", "192.168.1.1/24"])
def test_validate_ipv4_rejects(bad: str) -> None:
    with pytest.raises(InvalidIp):
        validate_ipv4(bad)


# --- validate_hostname ---------------------------------------------------------------


@pytest.mark.parametrize("good", ["hoctap.local", "pc1", "my-pc", "a.b.c"])
def test_validate_hostname_ok(good: str) -> None:
    assert validate_hostname(good) == good


@pytest.mark.parametrize("bad", ["", "has space", "bad/slash", "bad_underscore!", "-leading"])
def test_validate_hostname_rejects(bad: str) -> None:
    with pytest.raises(InvalidHostname):
        validate_hostname(bad)


# --- generate() ----------------------------------------------------------------------


def test_generate_ok_writes_cert_and_key(tmp_path: Path) -> None:
    cert_dir = tmp_path / "certs"
    run = _RecordingRun()
    paths = generate(
        "192.168.1.50", None, cert_dir, force=False, run=run, which=_which_present
    )
    assert paths.cert_file == cert_dir / "cert.pem"
    assert paths.key_file == cert_dir / "key.pem"
    # mkcert -install once, then the cert-generation call.
    assert run.calls[0] == ["mkcert", "-install"]
    gen_call = run.calls[1]
    assert gen_call[0] == "mkcert"
    assert "-cert-file" in gen_call and str(paths.cert_file) in gen_call
    assert "-key-file" in gen_call and str(paths.key_file) in gen_call
    assert "192.168.1.50" in gen_call
    assert "localhost" in gen_call and "127.0.0.1" in gen_call


def test_generate_includes_hostname(tmp_path: Path) -> None:
    run = _RecordingRun()
    generate(
        "192.168.1.50", "hoctap.local", tmp_path / "certs", force=False,
        run=run, which=_which_present,
    )
    assert "hoctap.local" in run.calls[1]


def test_generate_mkcert_missing(tmp_path: Path) -> None:
    with pytest.raises(MkcertNotFound):
        generate(
            "192.168.1.50", None, tmp_path / "certs", force=False,
            run=_RecordingRun(), which=_which_absent,
        )
    assert not (tmp_path / "certs").exists()


def test_generate_invalid_ip_never_shells_out(tmp_path: Path) -> None:
    run = _RecordingRun()
    with pytest.raises(InvalidIp):
        generate(
            "not-an-ip", None, tmp_path / "certs", force=False, run=run, which=_which_present
        )
    assert run.calls == []


def test_generate_invalid_hostname_never_shells_out(tmp_path: Path) -> None:
    run = _RecordingRun()
    with pytest.raises(InvalidHostname):
        generate(
            "192.168.1.50", "not a hostname", tmp_path / "certs", force=False,
            run=run, which=_which_present,
        )
    assert run.calls == []


def test_generate_mkdir_oserror_raises_cert_dir_error(tmp_path: Path) -> None:
    # A file where the cert directory should be: mkdir(parents=True) raises NotADirectoryError.
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    cert_dir = blocker / "certs"
    run = _RecordingRun()
    with pytest.raises(CertDirError):
        generate("192.168.1.50", None, cert_dir, force=False, run=run, which=_which_present)
    assert run.calls == []


def test_generate_refuses_to_overwrite(tmp_path: Path) -> None:
    cert_dir = tmp_path / "certs"
    cert_dir.mkdir()
    (cert_dir / "cert.pem").write_text("old", encoding="utf-8")
    run = _RecordingRun()
    with pytest.raises(CertsExist):
        generate(
            "192.168.1.50", None, cert_dir, force=False, run=run, which=_which_present
        )
    assert run.calls == []
    assert (cert_dir / "cert.pem").read_text(encoding="utf-8") == "old"


def test_generate_force_overwrites(tmp_path: Path) -> None:
    """--force must still invoke mkcert to regenerate, unlike the non-force refusal above
    (which never calls `run` at all -- see `test_generate_refuses_to_overwrite`)."""
    cert_dir = tmp_path / "certs"
    cert_dir.mkdir()
    (cert_dir / "cert.pem").write_text("old", encoding="utf-8")
    (cert_dir / "key.pem").write_text("old", encoding="utf-8")
    run = _RecordingRun()
    paths = generate(
        "192.168.1.50", None, cert_dir, force=True, run=run, which=_which_present
    )
    # mkcert -install, then the actual cert-generation call naming these exact paths --
    # proves --force reached the shell-out that the non-force path (CertsExist) never does.
    assert run.calls[0] == ["mkcert", "-install"]
    gen_call = run.calls[1]
    assert "-cert-file" in gen_call and str(paths.cert_file) in gen_call
    assert "-key-file" in gen_call and str(paths.key_file) in gen_call
    assert "192.168.1.50" in gen_call
    assert len(run.calls) == 2


def test_generate_mkcert_oserror_raises_mkcert_failed(tmp_path: Path) -> None:
    def broken_run(_command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise OSError("mkcert not executable")

    with pytest.raises(MkcertFailed):
        generate(
            "192.168.1.50", None, tmp_path / "certs", force=False,
            run=broken_run, which=_which_present,
        )


def test_generate_mkcert_nonzero_exit_raises(tmp_path: Path) -> None:
    def failing_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if command[1] == "-install":
            return _ok()
        return subprocess.CompletedProcess(
            args=command, returncode=1, stdout="", stderr="boom"
        )

    with pytest.raises(MkcertFailed):
        generate(
            "192.168.1.50", None, tmp_path / "certs", force=False,
            run=failing_run, which=_which_present,
        )


# --- CLI ------------------------------------------------------------------------------


@pytest.fixture
def cli_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("HOCTAP_CONFIG", str(tmp_path / "hoctap.toml"))
    (tmp_path / "hoctap.toml").write_text("", encoding="utf-8")
    monkeypatch.setenv("HOCTAP_DATA_DIR", str(tmp_path / "cli-data"))
    # tls_cert_dir is independent of data_dir; pin it into tmp_path too, or the CLI would
    # default to the real repo's data/certs/.
    monkeypatch.setenv("HOCTAP_TLS_CERT_DIR", str(tmp_path / "cli-data" / "certs"))
    return tmp_path


def test_cli_certs_ok(cli_env: Path, monkeypatch: pytest.MonkeyPatch,
                       capsys: pytest.CaptureFixture[str]) -> None:
    import hoctap.builder.certs as certs_mod

    def fake_generate(ip, hostname, cert_dir, force, **_kwargs):  # noqa: ANN001
        cert_dir.mkdir(parents=True, exist_ok=True)
        cert_file, key_file = cert_dir / "cert.pem", cert_dir / "key.pem"
        cert_file.write_text("cert", encoding="utf-8")
        key_file.write_text("key", encoding="utf-8")
        return certs_mod.CertPaths(cert_file=cert_file, key_file=key_file)

    monkeypatch.setattr(certs_mod, "generate", fake_generate)
    assert cli_main(["certs", "--ip", "192.168.1.50"]) == 0
    out = capsys.readouterr().out
    assert "cert.pem" in out and "key.pem" in out
    cert_dir = cli_env / "cli-data" / "certs"
    assert (cert_dir / "cert.pem").is_file()
    assert (cert_dir / "key.pem").is_file()


def test_cli_certs_mkcert_missing_exit_2(
    cli_env: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import hoctap.builder.certs as certs_mod

    def fake_generate(*_args, **_kwargs):  # noqa: ANN001
        raise MkcertNotFound()

    monkeypatch.setattr(certs_mod, "generate", fake_generate)
    assert cli_main(["certs", "--ip", "192.168.1.50"]) == 2
    err = capsys.readouterr().err
    assert "mkcert" in err and "install" in err.lower()


def test_cli_certs_invalid_ip_exit_2(
    cli_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli_main(["certs", "--ip", "not-an-ip"]) == 2
    err = capsys.readouterr().err
    assert "VALIDATION_ERROR" in err


def test_cli_certs_already_exists_exit_1(
    cli_env: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import hoctap.builder.certs as certs_mod

    def fake_generate(*_args, **_kwargs):  # noqa: ANN001
        raise CertsExist(cli_env / "cli-data" / "certs")

    monkeypatch.setattr(certs_mod, "generate", fake_generate)
    assert cli_main(["certs", "--ip", "192.168.1.50"]) == 1
    err = capsys.readouterr().err
    assert "--force" in err


def test_cli_certs_force_overwrites(
    cli_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hoctap.builder.certs as certs_mod

    calls: list[bool] = []

    def fake_generate(ip, hostname, cert_dir, force, **_kwargs):  # noqa: ANN001
        calls.append(force)
        cert_dir.mkdir(parents=True, exist_ok=True)
        cert_file, key_file = cert_dir / "cert.pem", cert_dir / "key.pem"
        cert_file.write_text("x", encoding="utf-8")
        key_file.write_text("x", encoding="utf-8")
        return certs_mod.CertPaths(cert_file=cert_file, key_file=key_file)

    monkeypatch.setattr(certs_mod, "generate", fake_generate)
    assert cli_main(["certs", "--ip", "192.168.1.50", "--force"]) == 0
    assert calls == [True]
