#!/usr/bin/env bash
# GoW init normally receives an already-existing socket mounted by Wolf. Supply
# an isolated init-only Unix socket fixture instead; the harness subsequently
# starts and probes REAL Sway parents before invoking the session supervisor.
# The fixture is never passed to session.py and never yields protocol results.
set -euo pipefail
install -d -m 0700 /run/wolf-lutris-harness-bootstrap
python3 - <<'PY'
import socket
with socket.socket(socket.AF_UNIX) as fixture:
    fixture.bind('/run/wolf-lutris-harness-bootstrap/wayland')
PY
export WOLF_LUTRIS_PARENT_WAYLAND=/run/wolf-lutris-harness-bootstrap/wayland
exec /entrypoint.sh "$@"
