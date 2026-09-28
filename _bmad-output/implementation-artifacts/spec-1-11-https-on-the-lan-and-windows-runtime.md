---
title: 'Story 1.11: HTTPS on the LAN and Windows runtime'
type: 'feature'
created: '2026-09-28'
status: 'done'
baseline_commit: 'tree:3842221672bda57ac06cd53380b595fbfb992a6d'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The tablet needs HTTPS to reach the app over the home LAN for full PWA features (service worker, install), and the server needs to run on Anh's Windows PC, not only in WSL (AD-12, AD-13).

**Approach:** A `hoctap certs` command generates an mkcert-signed certificate for the PC's LAN IP; `hoctap serve` uses it when present (falling back to plain HTTP otherwise). A `hoctap install-windows` command adds a Windows Firewall rule for the port. Documentation walks Anh through: installing mkcert, reserving the PC's LAN IP on the router, running `certs`/`install-windows`, and installing the mkcert CA on iPad/Android.

## Boundaries & Constraints

**Always:**
- **`hoctap certs --ip <ip> [--hostname <name>]`**:
  - Requires the `mkcert` executable on PATH; if missing, exits 2 with install instructions (link to mkcert's install docs) rather than a raw error.
  - Runs `mkcert -install` once (idempotent — mkcert itself no-ops if the local CA already exists) then `mkcert -cert-file data/certs/cert.pem -key-file data/certs/key.pem <ip> [<hostname>] localhost 127.0.0.1`.
  - Refuses to overwrite existing cert/key files without `--force`.
  - `--ip` is validated as a syntactically valid IPv4 address before shelling out.
- **`hoctap serve` TLS behaviour**:
  - If `data/certs/cert.pem` and `data/certs/key.pem` both exist, `serve` passes them to uvicorn's `ssl_certfile`/`ssl_keyfile` and binds the configured port (default 8443 when TLS is active, else the existing default) — reuse the existing `Settings.port`/host config, adding `tls_port` (default 8443) used only when certs are present.
  - If either file is missing, `serve` starts plain HTTP exactly as today (no behaviour change), and logs one line noting HTTPS is off and how to enable it.
  - `serve` never generates certs itself — that's `hoctap certs`'s job only.
- **`hoctap install-windows`**:
  - Only runs its Windows-specific actions on `platform.system() == "Windows"`; on any other OS it prints what it *would* do (the exact `netsh advfirewall` command) and exits 0 without executing anything — so the story is buildable and testable on Linux/WSL.
  - On Windows, adds an inbound firewall rule (`netsh advfirewall firewall add rule name="Học Tập" dir=in action=allow protocol=TCP localport=<port> profile=private`) for the configured TLS port, idempotently (checks for an existing rule with the same name first via `netsh advfirewall firewall show rule name=...`, skips re-adding if found).
  - Requires no elevation-detection beyond letting `netsh` itself report a failure clearly (map its non-zero exit to a clear stderr message about needing an administrator prompt).
- **Documentation** (`docs/https-and-windows-setup.md`, linked from `README.md`):
  - Step-by-step: install mkcert, reserve the LAN IP on the router (generic instructions, since routers vary), run `hoctap certs --ip <ip>`, run `hoctap install-windows`, open `https://<ip>:8443` on the PC to confirm, then install the mkcert root CA on iPad (Settings > General > VPN & Device Management, then enable full trust under Certificate Trust Settings) and Android (Settings > Security > Install a certificate > CA certificate).
  - States plainly that without the CA installed on the tablet, the plain-HTTP URL still works for playing Sessions, just without install-to-home-screen or offline caching (AD-12) — this is the fallback the acceptance criteria requires.
- **Config**: add `tls_port` (default `8443`) and `tls_cert_dir` (default `data/certs`) to `Settings`/`hoctap.toml`, following the existing `[server]`/`[build]` pattern; validated the same way other paths/ports are.

**Never:**
- No automatic certificate renewal, no ACME/Let's Encrypt (mkcert only, per architecture AD-12).
- No changes to how the app behaves once served — this story only changes how the process starts and what port/protocol it listens on.
- `install-windows` never touches anything outside the one firewall rule; no service installation, no Task Scheduler autostart (explicitly deferred by AD-13).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| certs ok | mkcert on PATH, no existing cert | cert.pem + key.pem written to data/certs/ | N/A |
| certs, mkcert missing | mkcert not on PATH | exit 2, install-mkcert instructions printed | N/A |
| certs, invalid ip | `--ip not-an-ip` | exit 2, VALIDATION_ERROR-style message | N/A |
| certs, already exists | cert.pem exists, no --force | exit 1, "use --force to overwrite" | nothing overwritten |
| certs, --force | cert.pem exists, --force given | files overwritten | N/A |
| serve, certs present | cert.pem+key.pem exist | binds TLS on tls_port; log line confirms HTTPS on | N/A |
| serve, certs absent | no certs | binds plain HTTP as today; log line explains how to enable TLS | N/A |
| serve, one file missing | only cert.pem exists | treated as absent (falls back to plain HTTP), with a warning naming the missing file | N/A |
| install-windows, non-Windows | any OS but Windows | prints the netsh command it would run, exits 0, adds nothing | N/A |
| install-windows, Windows, rule absent | (unit-testable via a mocked platform+subprocess) | adds the rule | N/A |
| install-windows, Windows, rule exists | rule already present | skips re-adding, reports "already present" | N/A |
| install-windows, netsh fails | non-zero exit from netsh | exit 1, message suggests running as Administrator | N/A |

</frozen-after-approval>

## Code Map

- `backend/hoctap/cli.py` -- the existing `build_parser()`/subcommand pattern (`_serve`, `_export_openapi`, etc.) and `_run_build`'s style of clear bilingual error printing. Add `certs` and `install-windows` alongside these, not inside the `build` subgroup.
- `backend/hoctap/config.py` -- `Settings`, the `[server]` table pattern, and its validation helpers (`_port`, path validators) to extend for `tls_port`/`tls_cert_dir`.
- `backend/hoctap/app.py` / `cli.py::_serve` -- where uvicorn is invoked today; add the conditional `ssl_certfile`/`ssl_keyfile` kwargs here.
- `hoctap.toml.example` -- document the two new settings alongside the existing ones.
- `README.md` -- add a short pointer to the new doc, matching how other setup docs are linked.

## Tasks & Acceptance

**Execution:**
- [ ] `backend/hoctap/builder/certs.py` (new) -- `generate(ip, hostname, cert_dir, force) -> CertPaths` wrapping the `mkcert` calls; raises a typed error the CLI turns into the right exit code/message.
- [ ] `backend/hoctap/cli.py` -- `hoctap certs --ip --hostname --force`; wire TLS into `_serve`/the uvicorn invocation; new `hoctap install-windows`.
- [ ] `backend/hoctap/config.py` -- `tls_port`, `tls_cert_dir` settings + validation + `hoctap.toml.example` entries.
- [ ] `backend/hoctap/builder/winfw.py` (new) -- the firewall-rule logic, platform-gated, with the command construction unit-testable independent of the actual OS (inject a `platform_name` and a `run` callable so tests can simulate both branches on Linux).
- [ ] `docs/https-and-windows-setup.md` (new) + a link from `README.md`.
- [ ] `backend/tests/test_certs.py`, `backend/tests/test_winfw.py`, and CLI/serve tests in the existing test-file pattern -- every matrix row, mocking `mkcert`/`netsh` subprocess calls (never actually invoking them).

**Acceptance Criteria:**
- Given `mkcert` is mocked as present, when `hoctap certs --ip 192.168.1.50` runs, then `data/certs/cert.pem` and `key.pem` exist and a subsequent `hoctap serve` (with mocked uvicorn.run) is called with `ssl_certfile`/`ssl_keyfile` set to those paths.
- Given no certs exist, when `hoctap serve` runs, then uvicorn.run is called with no `ssl_*` kwargs (unchanged from today), and the log clearly states HTTPS is off.
- Given the current OS is not Windows, when `hoctap install-windows` runs, then it exits 0 having executed no `netsh` command and having printed the exact command it would run on Windows.

## Implementation Notes

## Spec Change Log

## Review Triage Log

| # | Finding | Verdict | Evidence / route |
|---|---|---|---|
| 1 | Doc/example never set host=0.0.0.0; default 127.0.0.1 means the tablet can never reach the server even after certs+firewall are set up | high | confirmed: hoctap.toml.example:10 still 127.0.0.1, doc never mentions it -> patch (doc step + toml.example comment) |
| 2 | winfw idempotency check only matches rule NAME, not port; changing tls_port later leaves the old port open and the new one closed, silently reported "already present" | high | confirmed functional gap -> patch (compare the existing rule's port, re-add/update if it differs) |
| 3 | cert_dir.mkdir() and winfw's run() calls are not wrapped in try/except OSError, so a rare OSError escapes as a raw traceback instead of the promised typed error | medium | confirmed unguarded in both files -> patch (wrap both, raise CertsError/FirewallError) |
| 4 | test_generate_force_overwrites doesn't distinguish setup-created files from freshly-written ones (fake run() never writes) | medium | confirmed, weak test -> patch: assert generate() was actually invoked with --force reflected, e.g. via a spy call count, not just file existence |
| 5 | README documents HOCTAP_TLS_PORT but omits HOCTAP_TLS_CERT_DIR | low | -> patch |
| 6 | netsh rule has no remoteip=LocalSubnet scoping; opens the port to any network the Private profile matches | medium | worth tightening for a "home LAN only" feature -> patch: add remoteip=LocalSubnet to add_rule_command |
| 7 | doc doesn't mention Windows network profile must be "Private" for the rule to apply | medium | -> patch (doc troubleshooting note) |
| 8 | _certs_cmd success prints are English-only, breaking the bilingual pattern used everywhere else in this story | low | -> patch |
| 9 | FirewallError/install-windows always exits 1; no distinct code for "not elevated" vs other netsh failures, unlike certs' typed codes | low | reject — spec doesn't require distinct codes here, and netsh's own stderr already names the cause; not worth the added surface |
| 10 | generate() doesn't validate hostname before passing to mkcert; a malformed hostname surfaces as a raw MkcertFailed instead of a friendly VALIDATION_ERROR | low | -> patch (basic hostname sanity check, reuse a simple regex) |
| 11 | no comment/handling of key.pem file permissions (0600) | low | reject — self-signed LAN-only mkcert output; mkcert itself doesn't guarantee this either, out of scope for this story |
| 12 | doc doesn't tie "cert error for wrong IP" symptom to "run certs --force again" fix when DHCP reservation IP drifts | low | -> patch (doc troubleshooting note) |
| 13 | no --check/status or uninstall path for certs/install-windows | low | reject — explicitly deferred scope; not requested by spec |
| 14 | generate() -> Path claim in spec's Code Map/Tasks section is stale prose (actual code correctly returns CertPaths, used consistently everywhere) | low | reject (false alarm) -> patch: fix the one stale line in the spec's own Tasks section wording only, no code change |

## Verification

**Commands:**
- `cd backend && uv run pytest -q && uv run ruff check .` -- expected: all pass
- Manual (owner, on Windows, not part of automated verification): run `hoctap certs --ip <reserved LAN IP>`, `hoctap install-windows`, open `https://<ip>:8443` from the PC browser, then from the tablet after installing the mkcert CA.
