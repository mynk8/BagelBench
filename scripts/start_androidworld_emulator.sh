#!/usr/bin/env bash
# Start only the dedicated AndroidWorld AVD. Never selects a physical device.
set -euo pipefail
sdk="${ANDROID_SDK_ROOT:-$HOME/Android/Sdk}"
adb="$sdk/platform-tools/adb"
emulator="$sdk/emulator/emulator"
avd=ArtemisAndroidWorld
serial=emulator-5554
console=5554
grpc=8554
window=(-no-window)
if [[ ${1:-} == --window ]]; then window=(); shift; fi
if [[ $# -ne 0 ]]; then echo 'Usage: start_androidworld_emulator.sh [--window]' >&2; exit 2; fi
if [[ ! -x "$adb" || ! -x "$emulator" ]]; then echo "Android SDK adb or emulator missing under $sdk" >&2; exit 1; fi
if ! "$emulator" -list-avds | grep -Fxq "$avd"; then echo "Dedicated AVD $avd does not exist." >&2; exit 1; fi
if [[ "$("$adb" -s "$serial" get-state 2>/dev/null || true)" == device ]]; then
  actual=$("$adb" -s "$serial" emu avd name | head -n 1 | tr -d '\r')
  if [[ "$actual" != "$avd" ]]; then echo "$serial belongs to $actual, not $avd; refusing to use it." >&2; exit 1; fi
  echo "$serial already runs $avd."
else
  if ss -H -ltn "sport = :$console or sport = :$((console+1)) or sport = :$grpc" | grep -q .; then
    echo 'Emulator console, ADB or gRPC port is already occupied.' >&2; exit 1
  fi
  nohup setsid "$emulator" -avd "$avd" -port "$console" -grpc "$grpc" -grpc-use-token -no-audio -no-snapshot -no-boot-anim -memory 2048 -cores 2 -gpu swiftshader_indirect "${window[@]}" > /tmp/artemis-androidworld-emulator.log 2>&1 </dev/null &
  pid=$!
  echo "Starting $avd (PID $pid); log: /tmp/artemis-androidworld-emulator.log"
fi
for ((i=0; i<180; i++)); do
  if [[ "$("$adb" -s "$serial" get-state 2>/dev/null || true)" == device ]] && [[ "$("$adb" -s "$serial" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" == 1 ]]; then
    actual=$("$adb" -s "$serial" emu avd name | head -n 1 | tr -d '\r')
    [[ "$actual" == "$avd" ]] || { echo "Unexpected AVD $actual; refusing to continue." >&2; exit 1; }
    echo "Ready: $serial ($avd), gRPC $grpc"
    exit 0
  fi
  if [[ -n ${pid:-} ]] && ! kill -0 "$pid" 2>/dev/null; then echo 'Emulator exited; inspect the log.' >&2; exit 1; fi
  sleep 2
done
echo 'Emulator did not finish booting within six minutes; inspect the log.' >&2
exit 1
