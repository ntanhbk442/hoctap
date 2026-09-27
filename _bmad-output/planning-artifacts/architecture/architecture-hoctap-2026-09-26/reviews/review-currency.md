---
review: currency
target: ../ARCHITECTURE-SPINE.md
lens: "Every committed decision web-researched / reality-checked; versions current; named tech exists and fits; starter live defaults"
date: 2026-09-26
verdict: needs-revision
---

# Currency Review — Học Tập Architecture Spine

**Verdict:** Needs revision. Most of the Stack rows match the live registries today. The problems are about how the pieces fit together, which nobody checked: the starter template, TypeScript 7 and the tooling that relies on the TypeScript API. On top of that, three committed choices are already stale: the `anthropic` SDK major version, the extraction model, and Python 3.12.

Method: PyPI JSON API, npm registry (`/latest` plus peerDependencies/engines), the `@vite-pwa/create-pwa@1.1.0` tarball (unpacked and read), the nodejs/Release schedule.json, endoflife.date, the GitHub API (mkcert, KaTeX), Claude Platform docs (models overview, pricing, deprecations, structured outputs), Microsoft Learn WSL networking, the anthropic 1.8.0 wheel source, and local checks on this machine (`python3`, `node`, `.wslconfig`, `sqlite3.Connection.backup`).

## Findings

### F1 — HIGH — TypeScript 7.0.2 breaks the lint and codegen toolchain (Stack: TypeScript; AD-1 "generated TS types"; Conventions: `npm run gen:api`)
- `typescript@7.0.2` exists (GA 2026-07-08; the Go-native compiler). But 7.0 ships **without a stable programmatic API**. The TS team says a new API lands in 7.1, targeted for autumn 2026.
- `typescript-eslint@8.70.1` (latest) has peer `typescript: >=4.8.4 <6.1.0`. The starter template ships typescript-eslint, so `npm install` gives ERESOLVE, or type-aware lint breaks (typescript-eslint issue #12518).
- `openapi-typescript@7.13.0`, the obvious generator for AD-1's "TS types generated from OpenAPI", has peer `typescript: ^5.x`. `@hey-api/openapi-ts@0.99.0` accepts `>=5.5.3` but runs on the TS API.
- The memlog verified only that the version *exists*, not that it works with the rest of the stack.
- **Fix:** pin `typescript` **6.0.3** (latest 6.x, 2026-04-16) for the toolchain. Optionally add TS 7 (`tsc`/tsgo) as a fast type-check-only step. Revisit when 7.1 and a typescript-eslint release that supports it both ship. Name the OpenAPI generator in the Stack table and check its TS peer.

### F2 — HIGH — The starter does not produce the Stack table (Stack: Starter; also Vite, TS, Workbox rows)
`@vite-pwa/create-pwa` latest is **1.1.0 (2025-11-27)**. Its `template-react-ts/package.json` pins:

| Dep | Starter pins | Spine table |
| --- | --- | --- |
| vite | `^7.1.9` | 8.3.1 |
| typescript | `~5.9.3` | 7.0.2 |
| @vitejs/plugin-react | `^5.0.4` | — (latest 6.1.1 requires `vite ^8`) |
| vite-plugin-pwa | `^1.1.0` | 1.3.0 |
| workbox-core / -window | `^7.3.0` | 7.4.1 |
| eslint | `^9.37.0` | — (latest 10.11.0) |
| react / react-dom | `^19.2.0` | 19.3.0 (satisfied by caret) |

- The starter has no React Router or TanStack Query. Those are added by hand.
- Nothing in the spine says a post-scaffold bump is needed. An agent that runs the starter as written will get Vite 7 / TS 5.9, and table-driven checks will then flag drift.
- **Fix:** add a Starter note: "scaffold, then bump to the table: `vite@8`, `@vitejs/plugin-react@6`, `vite-plugin-pwa@1.3`, `workbox-*@7.4.1`, TS per F1; add react-router@8, @tanstack/react-query@5, katex". Or drop the generator and hand-write a minimal `vite.config.ts` with `VitePWA()`. Also note that React Router 8.4 needs Node `>=22.22.0` (Node 24 is fine), and that Vitest 5.0.2 accepts Vite 8.

### F3 — HIGH — The `anthropic` SDK is no longer 0.x (Stack: "anthropic (Python SDK) — latest 0.x at scaffold time")
- PyPI `anthropic` latest is **1.8.0 (2026-09-22)**. 1.0.0 shipped 2026-08-20, and the last 0.x is 0.125.0.
- "Latest 0.x" would deliberately pin a superseded major. It was not checked against the registry, and the memlog version line doesn't list it.
- **Fix:** pin `anthropic>=1.8,<2`.

### F4 — MEDIUM — The extraction model default is a legacy model that costs more (AD-7; Deferred; memlog cost assumption)
- The Claude models overview lists **Claude Opus 5.5 (`claude-opus-5-5`)** as the current recommended model. `claude-opus-5` is under "Legacy models (still available)", retiring not sooner than 2027-07-24.
- Pricing: Opus 5.5 is $4/$20 per MTok (batch $2/$10). Opus 5 is $5/$25 (batch $2.50/$12.50). Sonnet 5 is $2/$10; its introductory price became permanent, and the planned increase to $3/$15 will not happen.
- So the default in AD-7 is both older and about 20% dearer. The ~$300 / ~$120 estimates in the memlog should be redone.
- Adaptive thinking is valid: it is always on for Opus 5.5 (default effort `medium`) and adaptive on Sonnet 5.
- **Fix:** AD-7 and Deferred should default to `claude-opus-5-5`, with `claude-sonnet-5` as the pilot alternative.

### F5 — MEDIUM — "The model's JSON Schema as `output_config.format`" will 400 if sent raw (AD-1)
- Pydantic discriminated unions emit `oneOf` plus `discriminator` and leave out `additionalProperties: false`. The structured-outputs spec supports `anyOf`/`allOf`/`$ref`/`const`, requires `additionalProperties: false`, and says unsupported features return a 400.
- The Python SDK's `transform_schema()` does rewrite `oneOf` to `anyOf` (checked in the anthropic 1.8.0 source, `lib/_parse/_transform.py`). But `messages.parse()` applies it automatically only on the synchronous path. **Batch requests must call `anthropic.transform_schema(ProblemDoc)` explicitly.**
- There are also hard complexity limits per request: **24 optional parameters**, **16 union-typed parameters** (`anyOf` or `["x","null"]`), plus a "Schema is too complex" 400 and a 180 s compile timeout. A ProblemDoc with around 10 Part variants and optional fields could hit these.
- Batch plus structured outputs is confirmed compatible.
- **Fix:** amend AD-1 to say "`transform_schema(ProblemDoc)`". Add a pilot check that the schema compiles, and keep optional/nullable fields to a minimum.

### F6 — MEDIUM — The firewall step for WSL2 mirrored mode is wrong or incomplete (Deployment diagram "Firewall rule :8443")
- Microsoft Learn confirms that mirrored mode (Windows 11 22H2+) allows "Connect to WSL directly from your local area network (LAN)".
- Inbound traffic is controlled by the **Hyper-V firewall**, which is on by default since WSL 2.0.9. It needs `New-NetFirewallHyperVRule ... -VMCreatorId '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}' -LocalPorts 8443` (or `Set-NetFirewallHyperVVMSetting -DefaultInboundAction Allow`). An ordinary Windows Defender inbound rule is not enough.
- This host is Windows build 26200, so mirrored mode is available. But `wslinfo --networking-mode` reports **`nat`** today, and `.wslconfig` has no `networkingMode` line.
- The distro also runs `tailscale0`, `wg0` and `docker0`. Mirrored mode changes how those behave (Docker and VPN interplay is a known source of WSL issues), and switching affects the whole machine.
- **Fix:** name the Hyper-V rule. Record that switching to mirrored mode is a one-time, machine-wide change to test against the existing Tailscale/WireGuard/Docker setup. Keep `netsh portproxy` as the fallback; it works in NAT mode but must be re-pointed when the WSL IP changes.

### F7 — MEDIUM — iOS/iPadOS service worker behaviour with a local CA is unconfirmed (AD-11)
- Confirmed:
  - Apple requires TLS leaf certificates chaining to non-system (user-installed) roots to be valid **≤825 days**. mkcert's default (about 2y3m) sits at that limit.
  - The 200-day public-CA rule (from 2026-03-15) does not apply to private roots.
  - The CA must be installed as a profile **and** enabled under Settings > General > About > Certificate Trust Settings.
- Not confirmed: that Safari and a home-screen web app register and keep a service worker for an origin signed by a user-installed root. Web sources conflict, and one 2026 guide claims it doesn't work.
- Separately:
  - The certificate SAN pins the PC's LAN IP, so it needs a **DHCP reservation**.
  - `hoctap.local` needs an mDNS responder. Windows doesn't publish arbitrary names, and Avahi inside WSL needs mirrored multicast. On Android, `.local` resolves only on Android 12+ via the DNS resolver module.
- **Fix:** make an early spike story that installs the CA on the actual tablet, installs the PWA, goes offline and checks the service worker and IndexedDB. Add the DHCP reservation and decide on mDNS, or use the IP only.

### F8 — LOW — Python 3.12 is not the sensible pin in late 2026 (Stack: Python)
- From endoflife.date:
  - 3.12 has been security-only since 2025-04, with EOL 2028-10.
  - 3.13's bugfix support ends 2026-10-01.
  - **3.14** is the current bugfix line (3.14.7, EOL 2030-10).
  - 3.15 is due in October 2026.
- Every backend dependency supports 3.14: the classifiers go up to 3.14/3.15, and PyMuPDF 1.28.2 ships `cp310-abi3`/`cp313-abi3` wheels.
- The host is Ubuntu 22.04 with Python 3.11.4, so 3.12 isn't native there either. It would be installed via uv or deadsnakes regardless.
- **Fix:** pin Python 3.14, installed via `uv`.

### F9 — LOW — Minor currency items
- **Node.js 24 LTS:** correct today. v24 is Active LTS until **2026-10-20**, then Maintenance until 2028-04-30. v26 becomes LTS on 2026-10-28. Keeping 24 is fine; note the date. Local node is v24.11.1, latest 24.x is 24.21.0.
- **KaTeX "latest at scaffold time":** the latest is **0.18.9 (2026-09-23)**, still 0.x. Minor versions can change output, so pin it (`katex@0.18.9`).
- **mkcert "latest":** v1.4.4 (2022-04-26), last commit 2024-04-18. Not archived but inactive. It still works, and its 825-day leaf default fits Apple's rule. Pin v1.4.4 and note that it is inactive (alternatives: `step-ca`, a hand-rolled OpenSSL CA).
- **SQLite online backup (NFR-7):** verified. `sqlite3.Connection.backup(target, pages=...)` works locally (SQLite 3.41.2) and has been in the stdlib since 3.7. Correct.

## Verified as current (no action)
All of these were rechecked against the registries on 2026-09-26 and match the table: FastAPI 0.141.1, Uvicorn 0.54.0, Pydantic 2.13.5, SQLAlchemy 2.1.1 (needs Python ≥3.11), Alembic 1.20.0, PyMuPDF 1.28.2, React 19.3.0, Vite 8.3.1 (Node ^20.19 / ≥22.12), vite-plugin-pwa 1.3.0 (peer vite ≤^8, workbox ^7.4.1), Workbox 7.4.1, TanStack Query 5.104.0 (react ^18/^19), React Router 8.4.0.
The Message Batches API supports structured outputs and vision, with a 50% discount.

## Suggested spine edits (for the author; spine not modified)
1. Stack: TypeScript → 6.0.3 (F1); anthropic → `>=1.8,<2` (F3); Python → 3.14 (F8); KaTeX → 0.18.9; mkcert → v1.4.4; add OpenAPI TS generator row.
2. Stack: add a Starter note listing the post-scaffold bumps (F2).
3. AD-7 / Deferred: `claude-opus-5-5` default, `claude-sonnet-5` alternative (F4).
4. AD-1: send `transform_schema(ProblemDoc)`, and respect the schema complexity limits (F5).
5. Deployment: Hyper-V firewall rule; mirrored-mode switch is a machine-wide change to test (F6).
6. AD-11: device spike; DHCP reservation; mDNS decision (F7).
