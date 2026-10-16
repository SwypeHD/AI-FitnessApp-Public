# FitTrack AI — Android app

A thin native shell (a single `WebView` activity) around the web app running on your
local network.

## Why this exists rather than a PWA

Chrome will only turn a site into a real installed app (a *WebAPK*) when it's served over
`https://`. On a plain-HTTP LAN address, "Install app" silently degrades to a bookmark
that opens in a browser tab — even with `chrome://flags` →
"Insecure origins treated as secure" enabled. That flag grants a secure *context* (enough
for a service worker to register), but Chrome enforces a separate, stricter check on the
URL scheme before minting an APK.

A native `WebView` has no secure-origin requirement, so this loads `http://` from your LAN
directly. No certificates, no tunnel, no flags.

## Building

Needs the Android SDK (build-tools + a platform) and a modern JDK. If you have Android
Studio installed, both are already present — the script finds them automatically.

```bash
bash android/build.sh
```

Output: `android/fittrack.apk` (debug-signed).

No Gradle. The app has zero third-party dependencies, so the build is just
`aapt2 compile` → `aapt2 link` → `javac` → `d8` → `zipalign` → `apksigner`. Override
`ANDROID_HOME` or `JAVA_HOME` if your install lives somewhere unusual.

## Installing on the phone

**Over the LAN (no cable needed):**

`build.sh` copies the APK into `src/fitness/web/static/` automatically, so the server
always offers the current build.

1. On the phone, open `https://<your-pc-ip>:8443/static/fittrack.apk` (or
   `http://<your-pc-ip>:8000/...` if you're not running TLS).
2. Over HTTPS the browser warns about the certificate — proceed anyway. Only the app
   bundles the CA; the browser doesn't have it unless you install `certs/ca.crt`.
3. Tap the download, then allow "install unknown apps" for your browser when prompted.

Installing over an existing copy keeps your data — it's the same signing key.

**Over USB:** enable Developer options → USB debugging on the phone, then:

```bash
adb install -r android/fittrack.apk
```

## HTTPS

The app defaults to `https://<ip>:8443`. Android has ignored user-installed CAs inside
apps since API 24, so the FitTrack CA is **bundled into the APK** as an explicit trust
anchor (`res/raw/fittrack_ca.crt`, wired up by `res/xml/network_security_config.xml`).
That means you don't install anything on the phone — and it's narrower than a
user-installed CA, which every app on the device would trust; this one is trusted only
here.

Because the certificate is baked in, **regenerating certificates means rebuilding and
reinstalling the APK.** `build.sh` copies the current `certs/ca.crt` in automatically.

Bad certificates are never silently accepted: `onReceivedSslError` cancels the load and
shows what was wrong (expired, wrong IP, untrusted) rather than calling `proceed()`.

Cleartext is still permitted, so an `http://` address typed into the setup screen keeps
working — useful before certificates exist, or if the server moves.

## Server address

Defaults to `https://192.168.1.100:8443/static/index.html` (see `DEFAULT_URL` in
`MainActivity.java`). You don't need to rebuild if your IP changes: when the app can't
reach the server it shows a native screen with an editable address field, and the value is
saved to `SharedPreferences`.

Worth setting a DHCP reservation for the PC on your router so the address stays put.

## Notes

- The server must be started with `--host 0.0.0.0` so it accepts LAN connections, and
  Windows Firewall must allow inbound TCP on the port.
- `usesCleartextTraffic="true"` is required, since the server is plain HTTP.
- The status bar follows the system light/dark setting (`values/` and `values-night/`) to
  match the web app's theme.
- `debug.keystore` is generated on first build and is gitignored. If you delete it, the
  next build is signed with a different key and Android will refuse to install over the
  existing app — uninstall first.
