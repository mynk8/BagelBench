#!/bin/sh
# The trusted Android host grades its own record. Harbor only retrieves the reward.
set -eu
python3 - <<'PY'
import json
import os
from pathlib import Path
import urllib.request

request = urllib.request.Request(
    os.environ["BENCH_REWARD_URL"],
    headers={"Authorization": "Bearer " + os.environ["BENCH_VERIFIER_TOKEN"]},
)
with urllib.request.urlopen(request, timeout=30) as response:
    result = json.load(response)
output = Path("/logs/verifier/reward.json")
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(result), encoding="utf-8")
PY
