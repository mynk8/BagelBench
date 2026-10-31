#!/usr/bin/env python3
"""Set up the four AndroidWorld pilot apps on an explicitly named emulator.

Run with the pinned AndroidWorld Python environment and its checkout on
PYTHONPATH. This clears app data and replaces app snapshots on the selected
emulator. Stop all other use of that emulator first. No physical device is
accepted. Example:

 PYTHONPATH=../android_world ../android_world/.venv/bin/python \
   scripts/setup_androidworld_apps.py --adb /path/to/adb \
   --serial emulator-5554 --avd ArtemisAndroidWorld --grpc-port 8554
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

PIN = "55ddaf5edc6f6c25673aed343907d5b9dca66f84"


def adb_command(adb, serial, *args, timeout=30):
    return subprocess.run(
        [adb, "-s", serial, *args], check=True, capture_output=True, text=True, timeout=timeout
    ).stdout.strip()


def preflight(adb, serial, avd):
    if not re.fullmatch(r"emulator-\d+", serial):
        raise ValueError("Only an explicitly selected emulator serial is allowed")
    port = int(serial.removeprefix("emulator-"))
    if port < 5554 or port > 5682 or port % 2:
        raise ValueError("Invalid emulator console port")
    if adb_command(adb, serial, "get-state") != "device":
        raise ValueError("Selected emulator is not ready")
    actual_avd = adb_command(adb, serial, "emu", "avd", "name").splitlines()[0].strip()
    if actual_avd != avd:
        raise ValueError(f"AVD mismatch: expected {avd!r}, got {actual_avd!r}")
    if adb_command(adb, serial, "shell", "getprop", "sys.boot_completed") != "1":
        raise ValueError("Emulator has not finished booting")
    if adb_command(adb, serial, "shell", "getprop", "ro.build.version.sdk") != "33":
        raise ValueError("AndroidWorld pilot requires API 33")
    return port


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", required=True, help="Absolute path to Android SDK adb")
    parser.add_argument(
        "--serial", required=True, help="Dedicated emulator serial, e.g. emulator-5554"
    )
    parser.add_argument(
        "--avd",
        default=os.environ.get("BAGEL_ANDROID_AVD", "ArtemisAndroidWorld"),
        help="Exact AVD name to verify before setup",
    )
    parser.add_argument("--grpc-port", type=int, default=8554)
    args = parser.parse_args()
    if not Path(args.adb).is_absolute() or not Path(args.adb).is_file():
        parser.error("--adb must be the absolute path to an existing adb executable")
    if not 1 <= args.grpc_port <= 65535:
        parser.error("Invalid gRPC port")
    try:
        import android_world

        root = Path(android_world.__file__).resolve().parent.parent
        revision = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        if revision != PIN:
            raise ValueError("Unexpected AndroidWorld revision")
        port = preflight(args.adb, args.serial, args.avd)
        print(
            f"Preflight passed for {args.serial}, AVD {args.avd}, AndroidWorld {revision}",
            flush=True,
        )
        # Both commands are serial-qualified. Root is needed for app snapshots.
        adb_command(args.adb, args.serial, "root")
        adb_command(args.adb, args.serial, "wait-for-device", timeout=60)
        if adb_command(args.adb, args.serial, "shell", "id", "-u") != "0":
            raise ValueError("ADB root unavailable; use a rootable API 33 emulator image")
        from absl import logging

        # AndroidEnv logs its full inherited environment at INFO.
        logging.set_verbosity(logging.WARNING)
        # Avoid repeated unbounded downloads by using the locally cached upstream APK.
        from android_env.wrappers import a11y_grpc_wrapper

        forwarder = Path("/tmp/android_world/app_data/accessibility_forwarder.apk")
        if forwarder.is_file():
            a11y_grpc_wrapper._get_accessibility_forwarder_apk = forwarder.read_bytes
        from android_world.env import env_launcher, adb_utils
        from android_world.env.setup_device import apps, setup
        from android_world.utils import app_snapshot

        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/androidworld"))
        from androidworld_grpc import configure_token_auth

        configure_token_auth(port, args.grpc_port)
        env = env_launcher.load_and_setup_env(
            console_port=port,
            adb_path=args.adb,
            grpc_port=args.grpc_port,
            emulator_setup=False,
            freeze_datetime=False,
        )
        try:
            adb_utils.press_home_button(env.controller)
            for app in (
                apps.AndroidWorldApp,
                apps.ExpenseApp,
                apps.RecipeApp,
                apps.SimpleCalendarProApp,
            ):
                print(f"Installing and configuring {app.app_name}", flush=True)
                setup.maybe_install_app(app, env)
                # Do not use setup.setup_app: it suppresses setup failures.
                app.setup(env)
                app_snapshot.save_snapshot(app.app_name, env.controller)
                if not setup.is_package_installed(app.package_name(), env):
                    raise RuntimeError(f"Package missing after installation: {app.package_name()}")
            print("Setup complete; four apps installed and snapshots saved.", flush=True)
        finally:
            env.close()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"Setup failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
