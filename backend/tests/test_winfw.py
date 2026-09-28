"""Story 1.11: `hoctap install-windows` and the `install()` it wraps.

Both branches (Windows and not) are exercised from Linux by injecting `platform_name`
and a fake `run` -- `netsh` is never actually invoked.
"""

from __future__ import annotations

import subprocess

import pytest

from hoctap.builder.winfw import (
    RULE_NAME,
    FirewallError,
    add_rule_command,
    delete_rule_command,
    install,
    show_rule_command,
)
from hoctap.cli import main as cli_main


def _proc(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def _show_stdout(port: int) -> str:
    return f"Rule Name: {RULE_NAME}\n----------------------------------\nLocalPort: {port}\n"


class _ScriptedRun:
    """Returns pre-scripted results, keyed by whether the command is show/delete/add."""

    def __init__(
        self,
        show_result: subprocess.CompletedProcess[str],
        add_result: subprocess.CompletedProcess[str] | None = None,
        delete_result: subprocess.CompletedProcess[str] | None = None,
    ) -> None:
        self.show_result = show_result
        self.add_result = add_result
        self.delete_result = delete_result
        self.calls: list[list[str]] = []

    def __call__(self, command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        self.calls.append(command)
        if command == show_rule_command():
            return self.show_result
        if command == delete_rule_command():
            assert self.delete_result is not None
            return self.delete_result
        assert self.add_result is not None
        return self.add_result


# --- non-Windows ---------------------------------------------------------------------


def test_install_non_windows_prints_command_and_does_nothing() -> None:
    run = _ScriptedRun(_proc(0))
    result = install(8443, platform_name="Linux", run=run)
    assert result.executed is False
    assert result.added is False
    assert run.calls == []  # nothing was actually invoked
    assert " ".join(add_rule_command(8443)) in result.message
    assert "netsh" in result.message


@pytest.mark.parametrize("system", ["Linux", "Darwin"])
def test_install_any_non_windows_os(system: str) -> None:
    run = _ScriptedRun(_proc(0))
    result = install(8443, platform_name=system, run=run)
    assert result.executed is False
    assert run.calls == []


# --- Windows: rule absent --------------------------------------------------------------


def test_install_windows_rule_absent_adds_it() -> None:
    run = _ScriptedRun(show_result=_proc(1, stderr="No rules match."), add_result=_proc(0))
    result = install(8443, platform_name="Windows", run=run)
    assert result.executed is True
    assert result.added is True
    assert len(run.calls) == 2
    assert run.calls[0] == show_rule_command()
    assert run.calls[1] == add_rule_command(8443)
    assert RULE_NAME in " ".join(run.calls[1])


def test_add_rule_command_scopes_to_local_subnet() -> None:
    assert "remoteip=LocalSubnet" in add_rule_command(8443)


# --- Windows: rule present -------------------------------------------------------------


def test_install_windows_rule_present_skips_readd() -> None:
    run = _ScriptedRun(show_result=_proc(0, stdout=_show_stdout(8443)))
    result = install(8443, platform_name="Windows", run=run)
    assert result.executed is True
    assert result.added is False
    assert len(run.calls) == 1  # add was never called
    assert "already present" in result.message.lower() or "đã có" in result.message.lower()


def test_install_windows_rule_present_for_different_port_gets_updated() -> None:
    """A stale rule left over from an earlier tls_port setting is replaced, not skipped."""
    run = _ScriptedRun(
        show_result=_proc(0, stdout=_show_stdout(8443)),
        delete_result=_proc(0),
        add_result=_proc(0),
    )
    result = install(9443, platform_name="Windows", run=run)
    assert result.executed is True
    assert result.added is True
    assert run.calls == [show_rule_command(), delete_rule_command(), add_rule_command(9443)]
    assert "9443" in result.message


def test_install_windows_rule_present_unparsable_port_gets_updated() -> None:
    """When the existing rule's port can't be parsed, treat it as different and replace it."""
    run = _ScriptedRun(
        show_result=_proc(0, stdout=f"Rule Name: {RULE_NAME}\n"),  # no LocalPort line
        delete_result=_proc(0),
        add_result=_proc(0),
    )
    result = install(8443, platform_name="Windows", run=run)
    assert result.added is True
    assert run.calls == [show_rule_command(), delete_rule_command(), add_rule_command(8443)]


# --- Windows: netsh fails --------------------------------------------------------------


def test_install_windows_netsh_add_fails_raises() -> None:
    run = _ScriptedRun(
        show_result=_proc(1),
        add_result=_proc(1, stderr="Access is denied."),
    )
    with pytest.raises(FirewallError) as exc_info:
        install(8443, platform_name="Windows", run=run)
    assert "administrator" in str(exc_info.value).lower()


def test_install_windows_netsh_delete_fails_raises() -> None:
    run = _ScriptedRun(
        show_result=_proc(0, stdout=_show_stdout(8443)),
        delete_result=_proc(1, stderr="Access is denied."),
    )
    with pytest.raises(FirewallError) as exc_info:
        install(9443, platform_name="Windows", run=run)
    assert "administrator" in str(exc_info.value).lower()


def test_install_windows_netsh_oserror_raises_firewall_error() -> None:
    def broken_run(_command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise OSError("netsh not found")

    with pytest.raises(FirewallError):
        install(8443, platform_name="Windows", run=broken_run)


# --- CLI ------------------------------------------------------------------------------


@pytest.fixture
def cli_env(monkeypatch: pytest.MonkeyPatch, tmp_path):  # noqa: ANN001
    monkeypatch.setenv("HOCTAP_CONFIG", str(tmp_path / "hoctap.toml"))
    (tmp_path / "hoctap.toml").write_text("", encoding="utf-8")
    monkeypatch.setenv("HOCTAP_DATA_DIR", str(tmp_path / "cli-data"))
    return tmp_path


def test_cli_install_windows_non_windows_exit_0(
    cli_env, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]  # noqa: ANN001
) -> None:
    assert cli_main(["install-windows"]) == 0
    out = capsys.readouterr().out
    assert "netsh" in out


def test_cli_install_windows_reports_netsh_failure(
    cli_env, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]  # noqa: ANN001
) -> None:
    import hoctap.builder.winfw as winfw_mod

    def fake_install(*_args, **_kwargs):  # noqa: ANN001
        raise FirewallError("netsh failed; try running as Administrator.")

    monkeypatch.setattr(winfw_mod, "install", fake_install)
    assert cli_main(["install-windows"]) == 1
    err = capsys.readouterr().err
    assert "Administrator" in err
