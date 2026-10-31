"""Add local emulator-token authentication to AndroidEnv without logging it."""

import os
from pathlib import Path


def configure_token_auth(console_port, grpc_port):
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
    matches = []
    for file in (runtime / "avd" / "running").glob("*.ini"):
        try:
            values = dict(
                line.split("=", 1) for line in file.read_text().splitlines() if "=" in line
            )
        except (OSError, ValueError):
            continue
        if values.get("grpc.port") == str(grpc_port) and values.get("port.serial") == str(
            console_port
        ):
            matches.append(values)
    if len(matches) != 1 or not matches[0].get("grpc.token"):
        raise RuntimeError(
            "No unique token-authenticated emulator discovery record for the selected ports"
        )
    token = matches[0]["grpc.token"]
    import grpc
    from android_env.components.simulators.emulator import emulator_simulator
    from android_env.proto import emulator_controller_pb2_grpc, snapshot_service_pb2_grpc

    def connect(self, port, timeout_sec=100):
        if port != grpc_port:
            raise RuntimeError("Unexpected emulator gRPC port")

        def metadata(_context, callback):
            callback((("authorization", "Bearer " + token),), None)

        credentials = grpc.composite_channel_credentials(
            grpc.local_channel_credentials(), grpc.metadata_call_credentials(metadata)
        )
        options = [("grpc.max_send_message_length", -1), ("grpc.max_receive_message_length", -1)]
        self._channel = grpc.secure_channel(f"localhost:{port}", credentials, options=options)
        grpc.channel_ready_future(self._channel).result(timeout=timeout_sec)
        return emulator_controller_pb2_grpc.EmulatorControllerStub(
            self._channel
        ), snapshot_service_pb2_grpc.SnapshotServiceStub(self._channel)

    emulator_simulator.EmulatorSimulator._connect_to_emulator = connect
