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

### 2026-10-01: Fixed findings #15 (HIGH) and #16 (medium) from the orchestrator's audit

`cli.py::_serve` was rewritten so the plain-HTTP fallback actually keeps working once certs
exist, and a busy port fails with a friendly error instead of a traceback:

- **Dual bind (#15).** Instead of one `uvicorn.run(app, port=..., **ssl_kwargs)` call, `_serve`
  now builds a list of `uvicorn.Config`s (one plain HTTP on `settings.port` plus one TLS on
  `settings.tls_port` when certs exist and no explicit `--port` was given; a single config
  otherwise, matching the pre-existing `--port` override and no-certs behaviour exactly), binds
  a real socket per config up front with the new `_bind_socket()`, then hands each
  `(config, socket)` pair to its own `uvicorn.Server`. A separate `create_app(settings)` call is
  made per server (not one `FastAPI` app instance shared across servers): the app's lifespan
  owns `app.state.engine`/`app.state.run_manager`, and two concurrently running `Server`s
  sharing one app would double-run startup and have one's shutdown dispose the engine the
  other is still using. Two independent engines onto the same SQLite file is already the
  supported case (WAL mode + `db_lock`), exactly like running two separate `hoctap serve`
  processes.
  - The servers run concurrently via the new `_run_servers()`, one `uvicorn.Server.run()` per
    OS thread rather than `asyncio.gather`-ing `Server.serve()` calls in one loop: uvicorn's
    `Server.serve()` installs its own Ctrl-C/SIGTERM handler per call
    (`capture_signals()`), and two concurrent calls in one loop would have the second
    `with`-block clobber the first's handler (only one server would actually stop on a single
    Ctrl-C). `signal.signal()` only works from the interpreter's main thread, so each
    background-thread server's own handler install becomes a no-op (same guard uvicorn's own
    code uses); `_run_servers` installs exactly one SIGINT/SIGTERM handler, in the caller's
    thread, that flips `should_exit` on every server at once, so one Ctrl-C/SIGTERM stops both
    ports together.
- **Typed port-in-use error (#16).** `_bind_socket()` catches the `OSError` from
  `socket.create_server()` and raises a new `ServeError` (bilingual message naming the busy
  port, exit code 4) before any `uvicorn.Server` is even constructed — matching the
  `CertsError`/`FirewallError` pattern used elsewhere in this story. `_serve` catches it, closes
  any sockets already bound, prints the message to stderr and returns the exit code.
- **Tests.** `test_app.py`'s four existing serve tests were rewritten against a fake
  `_run_servers` (records each server's `uvicorn.Config` instead of starting a listener, so
  they stay fast) and now assert the actual set of bound ports instead of a single `uvicorn.run`
  call's kwargs. Two new tests were added: `test_serve_dual_port_both_reachable_end_to_end`
  runs the real `_serve`/`_run_servers` path with a real in-process self-signed cert
  (generated via `cryptography`, no `mkcert` binary needed) on two free ports, and makes real
  plain-HTTP and TLS client connections to both at once to confirm genuine reachability, then
  confirms both servers stop; `test_serve_port_in_use_raises_typed_error` occupies a real port
  with a blocking socket first and asserts the `ServeError` path (exit code 4, bilingual
  message, `_run_servers` never reached).
- **Not done:** no change to `docs/https-and-windows-setup.md` or the frozen spec's acceptance
  text was needed — the fix makes the code match what both already promised, rather than the
  other way around (the finding offered this as the alternative; the dual-bind fix was chosen
  as the one that actually preserves the documented no-install fallback for a tablet that
  hasn't had the mkcert CA installed yet).

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
| 15 | (2026-10-01, Orchestrator's Independent Audit) **The promised plain-HTTP fallback is broken once certs exist.** `cli.py::_serve`: when `cert.pem`/`key.pem` are both present, it makes ONE `uvicorn.run(..., port=settings.tls_port, ssl_certfile=..., ssl_keyfile=...)` call -- there is no second bind on `settings.port` (8000) for plain HTTP. Once `hoctap certs` has run, the process only ever listens on the TLS port. This directly contradicts both the frozen spec's own acceptance text ("the plain-HTTP URL still works for playing Sessions... this is the fallback the acceptance criteria requires") and the published `docs/https-and-windows-setup.md` ("`http://<reserved-ip>:8000/` keeps working for playing Sessions"). Concrete scenario: Anh runs `hoctap certs` then `hoctap serve` per the doc's own steps; the child's tablet hasn't had the mkcert CA installed yet; the doc says port 8000 should still work as a no-install fallback, but the connection is actually refused/times out -- not degraded gracefully, just gone. The only tests covering this (`test_app.py`) assert on `ssl_certfile` kwargs in the single `uvicorn.run` call, never that both ports are reachable, so the gap was never caught | high | confirmed by 1 reviewer via direct code read + cross-check against both the frozen spec text and the shipped doc -> patch: either run two uvicorn servers (one plain on `settings.port`, one TLS on `settings.tls_port`) when certs exist, or explicitly correct the spec's acceptance text and the doc to say the plain-HTTP fallback is only available before `hoctap certs` is first run -- implementer's call, but the current state (code silently diverges from both documents) must not stand -> **patched (2026-10-01)**: `_serve` now binds a real socket per port up front (`_bind_socket`) and runs one `uvicorn.Server` per bound port concurrently (one per OS thread, via the new `_run_servers`), so the default certs-present case keeps both `settings.tls_port` (HTTPS) and `settings.port` (plain-HTTP fallback) listening at once; `--port` still means "bind exactly this one port" (TLS only) as before. A single Ctrl-C/SIGTERM now stops every bound server together (one signal handler installed centrally, not uvicorn's own per-`Server` handler, which would otherwise clobber across servers). `test_app.py`'s serve tests were rewritten to assert the actual set of bound ports/TLS kwargs via a fake `_run_servers`, plus a new end-to-end test (`test_serve_dual_port_both_reachable_end_to_end`) that runs the real server with a real in-process self-signed cert and makes real plain-HTTP and TLS connections to both ports to confirm they are simultaneously reachable |
| 16 | (2026-10-01, Orchestrator's Independent Audit) `_serve` has no handling for "port already in use" -- `uvicorn.run(...)` is called with no try/except, and `main()` only catches `ConfigError`. Every OTHER failure mode in this story (missing mkcert, bad IP, existing cert without `--force`, netsh failure) gets a typed, bilingual error with a clear exit code; this one doesn't. A previous `hoctap serve` process not exiting cleanly, or another app bound to 8000/8443 (plausible on a shared family PC), surfaces as a raw Python traceback and an arbitrary exit code instead of a friendly message | medium | confirmed by 1 reviewer; not a security problem (fails closed), but inconsistent with the rest of the story's UX contract and would confuse a non-technical restart-the-PC troubleshooting flow; no test exercises it -> patch: catch the bind `OSError` around `uvicorn.run()` and surface a typed, bilingual "port already in use" error with a clear exit code, matching the pattern used for every other failure mode in this story -> **patched (2026-10-01)**: ports are now bound ourselves, before any `uvicorn.Server` is constructed, via `_bind_socket()`; an `OSError` there is caught and re-raised as the new typed `ServeError` (bilingual message, exit code 4), matching `CertsError`/`FirewallError`'s pattern. Covered by `test_serve_port_in_use_raises_typed_error`, which actually occupies a real port with a blocking socket first |

### 2026-10-01: Orchestrator's Independent Audit (post-foundation re-review)

Re-audited this story as part of Epic 1's full re-review (see spec-1-1's matching note for context). 3 parallel reviewers confirmed all prior HIGH findings are genuinely landed (host=0.0.0.0 doc, port-aware firewall idempotency, OSError-wrapped-as-typed-errors, `remoteip=LocalSubnet` scoping, hostname validation) and a reviewer independently re-ran the relevant test subset directly (143/143 passed, `ruff check` clean). **One new HIGH finding (#15) is the single most significant finding across all of Epic 1's re-audit: the documented plain-HTTP fallback does not actually work once TLS certs exist, contradicting both this spec's own acceptance criteria and the published setup doc.** This should be treated as a priority fix regardless of how the rest of the epic's findings are triaged, since it means a real family following the documented setup steps could end up with neither working connectivity (CA not installed on the tablet) nor the promised fallback. #16 (medium) is a secondary, lower-stakes gap in the same function.

## Verification

**Commands:**
- `cd backend && uv run pytest -q && uv run ruff check .` -- expected: all pass
- Manual (owner, on Windows, not part of automated verification): run `hoctap certs --ip <reserved LAN IP>`, `hoctap install-windows`, open `https://<ip>:8443` from the PC browser, then from the tablet after installing the mkcert CA.
