# Local AndroidWorld pilot setup

The pilot uses a dedicated emulator and can clear its app data and replace AndroidWorld snapshots. Keep personal phones out of this workflow. The scripts require the exact emulator serial and AVD name; do not run the setup while another experiment uses that emulator.

Prerequisites: an Android SDK with platform-tools and emulator, a rootable API 33 x86_64 system image, a Pixel 6 AVD named `ArtemisAndroidWorld`, and a pinned AndroidWorld checkout at revision `55ddaf5edc6f6c25673aed343907d5b9dca66f84` with its requirements installed in `.venv`. The upstream protobuf modules must be generated once with `cd ../android_world && .venv/bin/python setup.py generate_protos`. The system image must allow `adb root`; Google Play production images generally do not.

From the Artemis repository, start the AVD with console port 5554 and gRPC port 8554:

```bash
scripts/start_androidworld_emulator.sh
```

It enables token-authenticated gRPC and starts headless by default; pass `--window` to display it. Set `ANDROID_SDK_ROOT` if the SDK is not in `~/Android/Sdk`. Logs are written to `/tmp/artemis-androidworld-emulator.log`. If the selected serial is already running, the launcher verifies its AVD name. The setup and fixture bridge require a matching token-authenticated emulator discovery record for the specified console and gRPC ports.

Install and initialize the four pilot apps, after the emulator finishes booting:

```bash
PYTHONPATH=../android_world ../android_world/.venv/bin/python \
  scripts/setup_androidworld_apps.py \
  --adb "$HOME/Android/Sdk/platform-tools/adb" \
  --serial emulator-5554 --avd ArtemisAndroidWorld --grpc-port 8554
```

Use the actual SDK path for `--adb` if different. The script verifies the selected serial, AVD name, API level, upstream revision and root access before installing AndroidWorld, Pro Expense, Broccoli and Simple Calendar Pro. It uses upstream setup and creates app snapshots. First use downloads official AndroidWorld APKs into `/tmp/android_world/app_data`. AndroidEnv also downloads its accessibility-forwarder APK; when present at `/tmp/android_world/app_data/accessibility_forwarder.apk`, the setup and fixture bridge use that cached copy.

Set `ARTEMIS_ANDROIDWORLD_PATH` to the pinned checkout and `ARTEMIS_ANDROIDWORLD_PYTHON` to its Python if they differ from the workspace defaults. Ensure SDK `platform-tools` is on the Artemis server's `PATH`, and set `ARTEMIS_ANDROIDWORLD_GRPC_PORT=8554`. A successful setup does not establish pilot readiness: verify a control and fault fixture for each task, reconstruct the post-state oracle, and record human discoverability review before scoring. Do not run the 60-trial pilot until those checks pass.
