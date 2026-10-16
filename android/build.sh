#!/usr/bin/env bash
# Build a debug-signed APK using only the Android SDK build-tools (no Gradle).
#
# The app has no third-party dependencies, so dependency resolution isn't needed:
#   aapt2 compile/link -> javac -> d8 -> zipalign -> apksigner
#
# Usage:  bash android/build.sh          (from the repo root or anywhere)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SDK="${ANDROID_HOME:-$LOCALAPPDATA/Android/Sdk}"
JAVA_HOME_DIR="${JAVA_HOME:-/c/Program Files/Android/Android Studio/jbr}"

# Pick the newest stable build-tools (skip -rc builds).
BT_DIR="$(ls -1d "$SDK"/build-tools/*/ | grep -v -- '-rc' | sort -V | tail -1)"
BT="${BT_DIR%/}"
PLATFORM="$(ls -1d "$SDK"/platforms/android-*/ | sort -V | tail -1)"
ANDROID_JAR="${PLATFORM%/}/android.jar"

AAPT2="$BT/aapt2.exe"
ZIPALIGN="$BT/zipalign.exe"
JAVA="$JAVA_HOME_DIR/bin/java.exe"
JAVAC="$JAVA_HOME_DIR/bin/javac.exe"
JAR="$JAVA_HOME_DIR/bin/jar.exe"
KEYTOOL="$JAVA_HOME_DIR/bin/keytool.exe"

# The SDK's d8.bat / apksigner.bat wrappers break on spaces in their own path, and
# d8 needs a modern JDK (the system java here is 8). Invoke the jars directly.
D8_JAR="$BT/lib/d8.jar"
APKSIGNER_JAR="$BT/lib/apksigner.jar"

OUT="$HERE/build"
KEYSTORE="$HERE/debug.keystore"
APK_UNSIGNED="$OUT/app-unsigned.apk"
APK_ALIGNED="$OUT/app-aligned.apk"
APK_FINAL="$HERE/fittrack.apk"

echo "SDK:           $SDK"
echo "build-tools:   $BT"
echo "platform jar:  $ANDROID_JAR"
echo

rm -rf "$OUT"
mkdir -p "$OUT/compiled" "$OUT/gen" "$OUT/classes"

# The CA is bundled as a trust anchor, so the APK must carry the current one.
CA_SRC="$HERE/../certs/ca.crt"
if [ -f "$CA_SRC" ]; then
  mkdir -p "$HERE/res/raw"
  cp "$CA_SRC" "$HERE/res/raw/fittrack_ca.crt"
  echo "bundling CA:   certs/ca.crt"
else
  echo "WARNING: certs/ca.crt not found — run 'py -3 scripts/make_certs.py' first."
  echo "         HTTPS will fail until the app is rebuilt with a CA."
fi
echo

echo "[1/6] aapt2 compile resources"
"$AAPT2" compile --dir "$HERE/res" -o "$OUT/compiled/res.zip"

echo "[2/6] aapt2 link"
"$AAPT2" link \
  -o "$APK_UNSIGNED" \
  -I "$ANDROID_JAR" \
  --manifest "$HERE/AndroidManifest.xml" \
  --java "$OUT/gen" \
  --min-sdk-version 24 \
  --target-sdk-version 36 \
  "$OUT/compiled/res.zip"

# Argfiles are read verbatim by the Windows JDK tools, so MSYS's automatic
# /c/... -> C:/... conversion doesn't apply. Convert and quote explicitly.
win_argfile() {
  local out="$1"; shift
  : > "$out"
  while read -r f; do
    printf '"%s"\n' "$(cygpath -m "$f")" >> "$out"
  done
}

echo "[3/6] javac"
find "$OUT/gen" "$HERE/src" -name '*.java' | win_argfile "$OUT/sources.txt"
"$JAVAC" -source 8 -target 8 -nowarn \
  -bootclasspath "$ANDROID_JAR" \
  -d "$OUT/classes" \
  @"$OUT/sources.txt"

echo "[4/6] d8 -> dex"
# d8 reads argfile lines verbatim (quotes included), so bundle the classes into a
# single jar and hand it over as one argument instead.
"$JAR" cf "$OUT/classes.jar" -C "$OUT/classes" .
"$JAVA" -cp "$(cygpath -m "$D8_JAR")" com.android.tools.r8.D8 \
  --min-api 24 --output "$OUT" --lib "$ANDROID_JAR" "$OUT/classes.jar"

echo "[5/6] package dex + zipalign"
( cd "$OUT" && "$ZIPALIGN" -h >/dev/null 2>&1 || true )
py -3 -c "
import zipfile, shutil, sys, os
src, dex, dst = sys.argv[1], sys.argv[2], sys.argv[3]
shutil.copy(src, dst)
with zipfile.ZipFile(dst, 'a', zipfile.ZIP_DEFLATED) as z:
    z.write(dex, 'classes.dex')
print('  added classes.dex')
" "$APK_UNSIGNED" "$OUT/classes.dex" "$OUT/app-withdex.apk"
"$ZIPALIGN" -f 4 "$OUT/app-withdex.apk" "$APK_ALIGNED"

echo "[6/6] sign"
if [ ! -f "$KEYSTORE" ]; then
  echo "  generating debug keystore"
  "$KEYTOOL" -genkeypair -v \
    -keystore "$KEYSTORE" \
    -storepass android -keypass android \
    -alias fittrack -keyalg RSA -keysize 2048 -validity 10000 \
    -dname "CN=FitTrack Debug, OU=Dev, O=FitTrack, L=., ST=., C=US" >/dev/null
fi
"$JAVA" -jar "$(cygpath -m "$APKSIGNER_JAR")" sign \
  --ks "$KEYSTORE" --ks-pass pass:android --key-pass pass:android \
  --out "$APK_FINAL" "$APK_ALIGNED"

"$JAVA" -jar "$(cygpath -m "$APKSIGNER_JAR")" verify --print-certs "$APK_FINAL" | head -3
echo
echo "APK: $APK_FINAL"
stat -c "size: %s bytes" "$APK_FINAL" 2>/dev/null \
  || wc -c < "$APK_FINAL" | awk '{print "size:", $1, "bytes"}'

# Publish to the static dir the server already exposes, so the phone's download
# link never serves a stale build. (Gitignored — it's a build artifact.)
STATIC_DIR="$HERE/../src/fitness/web/static"
if [ -d "$STATIC_DIR" ]; then
  cp "$APK_FINAL" "$STATIC_DIR/fittrack.apk"
  echo "published: src/fitness/web/static/fittrack.apk"
fi
echo
echo "Install over USB:   adb install -r \"$(cygpath -w "$APK_FINAL")\""
echo "Or over the LAN:    open /static/fittrack.apk on the phone, e.g."
echo "                    https://<your-ip>:8443/static/fittrack.apk"
echo "                    (the browser will warn about the cert — proceed to download;"
echo "                     only the app itself bundles the CA)"
