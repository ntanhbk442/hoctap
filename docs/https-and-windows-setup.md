# HTTPS on the LAN and the Windows runtime

Story 1.11. This gets the tablet talking to the server over HTTPS on the home LAN (needed
for the service worker and "install to home screen"), and gets the server running natively
on Anh's Windows PC instead of only inside WSL.

Without HTTPS the app still works over plain HTTP — you can play Sessions from the tablet
today — you just don't get install-to-home-screen or offline caching (AD-12). Treat
everything below as optional polish, not a blocker.

## 1. Install mkcert

mkcert makes locally-trusted certificates without a real certificate authority or
Let's Encrypt. On the Windows PC (PowerShell, with
[Chocolatey](https://chocolatey.org/install) or [Scoop](https://scoop.sh/) already
installed):

```powershell
choco install mkcert
# or
scoop install mkcert
```

See mkcert's own install docs for other options:
https://github.com/FiloSottile/mkcert#installation

## 2. Reserve the PC's LAN IP on the router

Routers vary, but the idea is always the same: give the PC's network adapter a fixed IP
address so it never changes and the certificate keeps matching it.

1. Find the PC's current LAN IP (`ipconfig` on Windows, look for "IPv4 Address").
2. Find the PC's MAC address (`ipconfig /all`, "Physical Address" for the same adapter).
3. Open the router's admin page (often `192.168.0.1` or `192.168.1.1`) and find
   DHCP reservation / static lease / address reservation settings.
4. Reserve the PC's current IP for its MAC address, so DHCP always hands out the same one.
5. Reboot the PC (or renew its DHCP lease) and confirm with `ipconfig` that the IP didn't
   change.

Write this IP down — it's what you pass to `hoctap certs --ip`.

## 3. Bind the server to the LAN, not just this PC

By default `host = "127.0.0.1"`, which only accepts connections from the PC itself — the
tablet can never reach it, no matter what you do in the later steps. Copy
`hoctap.toml.example` to `hoctap.toml` (if you haven't already) and set:

```toml
[server]
host = "0.0.0.0"
```

(or set the environment variable `HOCTAP_HOST=0.0.0.0` instead, if you'd rather not edit
the file). This makes `hoctap serve` listen on every network interface on the PC, including
the LAN one, while still only being reachable from your own home network.

## 4. Generate the certificate

From `backend/`, with `mkcert` on PATH:

```sh
uv run hoctap certs --ip 192.168.1.50
```

This runs `mkcert -install` (installs mkcert's local certificate authority into your
system and browser trust stores — a no-op if it's already installed) and then writes
`data/certs/cert.pem` and `data/certs/key.pem` for that IP (plus `localhost` and
`127.0.0.1`, so it also works from the PC itself). Add `--hostname <name>` if you also want
a friendly hostname in the certificate, and `--force` to regenerate over an existing pair.

If `mkcert` isn't on PATH, the command exits with instructions instead of a raw error.

## 5. Add the Windows Firewall rule

Still from `backend/`, on the Windows PC:

```sh
uv run hoctap install-windows
```

This adds one inbound rule ("Học Tập") for the TLS port, restricted to the Private network
profile and to your local subnet (`remoteip=LocalSubnet`) — nothing outside the home LAN
can reach it. Run it as Administrator if it reports a `netsh` failure. On any OS other than
Windows it only prints the command it would run and does nothing — safe to run from WSL
while developing.

## 6. Start the server and confirm from the PC

```sh
uv run hoctap serve
```

`serve` looks for `data/certs/cert.pem` and `data/certs/key.pem`. When both exist it
starts on HTTPS (port 8443 by default — see `tls_port` in `hoctap.toml.example`); otherwise
it falls back to plain HTTP exactly as before, with a line explaining how to turn HTTPS on.

From the PC's own browser, open `https://<reserved-ip>:8443/` and confirm it loads without
a certificate warning (mkcert's CA is already trusted on this PC from step 1).

## 7. Trust the certificate on the tablet

The tablet doesn't have mkcert's CA installed yet, so it will show a certificate warning
until you add it.

**iPad:**

1. Get `$(mkcert -CAROOT)/rootCA.pem` onto the iPad (AirDrop, email to yourself, or a USB
   cable) and open it — iOS installs it as a configuration profile.
2. Settings > General > VPN & Device Management > (the mkcert profile) > Install.
3. Settings > General > About > Certificate Trust Settings > turn on full trust for the
   mkcert root certificate.

**Android:**

1. Copy `rootCA.pem` onto the device.
2. Settings > Security (or Security & privacy) > More security settings > Install a
   certificate > CA certificate.
3. Confirm the security warning and select the file.

Once installed, open `https://<reserved-ip>:8443/` on the tablet — it should load with no
warning, and the PWA install prompt / offline caching should now be available.

If you'd rather skip all of this for now, `http://<reserved-ip>:8000/` keeps working for
playing Sessions; you only lose install-to-home-screen and offline caching until the CA is
installed.

## Troubleshooting

- **The tablet can't reach the server at all** (times out, not just a certificate warning):
  check that `host = "0.0.0.0"` (step 3) actually took effect — `127.0.0.1` is the default
  and it silently refuses every connection that isn't from the PC itself.
- **`hoctap install-windows` added the rule but the tablet still can't connect**: Windows
  Firewall only applies a "Private" profile rule when it classifies the current network as
  Private. Check Settings > Network & Internet > (your Wi-Fi/Ethernet network) > Network
  profile type, and switch it to "Private" if it says "Public".
- **The browser shows a certificate error for the wrong IP address**: the reserved LAN IP
  changed (a new router, a DHCP reservation that didn't stick, etc.) — re-run
  `hoctap certs --ip <new-ip> --force` for the new address, then reload.
