#!/usr/bin/env bash
# Usage: bash tests/run.sh TEST_IMAGE [--require-cadence]
# The test stage needs sway, pulseaudio, gcc and glibc-devel.i686.
# No host sockets/devices/profile mounts, privileged mode or added capabilities.
set -euo pipefail
image=${1:?Usage: bash tests/run.sh TEST_IMAGE [--require-cadence]}
shift
if [[ $# -gt 1 || ( $# -eq 1 && $1 != --require-cadence ) ]]; then
    printf 'Only --require-cadence is supported\n' >&2
    exit 2
fi
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
artifacts=${WOLF_LUTRIS_ARTIFACT_DIR:-"$root/artifacts"}
mkdir -p "$artifacts"
chmod 0777 "$artifacts"
artifacts=$(cd -- "$artifacts" && pwd)
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s "$root/tests" -p 'test_*.py' -v
docker image inspect "$image" --format 'Test image under test: {{.Id}}'
docker run --rm --network none --user 1000:1000 --entrypoint python3 \
    -e PYTHONDONTWRITEBYTECODE=1 -v "$root:/src:ro" "$image" \
    -m unittest discover -s /src/tests -p 'test_*.py' -v
# Do not bypass the GoW entrypoint: init must create the actual unprivileged user.
# Its command is a shell fragment, not an argv; the only optional arg is validated.
extra=${1:-}
docker run --rm --network none --shm-size 256m --entrypoint bash \
    -e PUID=1000 -e PGID=1000 -e UNAME=lutris -e HOME=/home/retro \
    -e PYTHONDONTWRITEBYTECODE=1 -e HARNESS_EXTRA="$extra" \
    -v "$root/tests:/tests:ro" -v "$artifacts:/artifacts" "$image" /tests/container-entrypoint.sh \
    'install -d -m 0700 -o 1000 -g 1000 /home/retro/.cache/wolf-lutris-tests; exec gosu "$UNAME" env TMPDIR=/home/retro/.cache/wolf-lutris-tests python3 /tests/headless.py ${HARNESS_EXTRA:+--require-cadence}'
python3 - "$artifacts/headless.json" <<'PY'
import json, sys
from pathlib import Path
report = json.loads(Path(sys.argv[1]).read_text())
assert report['status'] == 'pass', report
assert len(report['cases']) == 9, report
print('Verified headless artifact:', sys.argv[1])
PY
# Repeat with truly new containers and the SAME newly-created HOME volume.
volume=$(docker volume create)
trap 'docker volume rm "$volume" >/dev/null' EXIT
for phase in 1 2; do
    docker run --rm --network none --shm-size 256m --entrypoint bash \
        -e PUID=1000 -e PGID=1000 -e UNAME=lutris -e HOME=/home/retro \
        -e PYTHONDONTWRITEBYTECODE=1 -e HARNESS_PHASE="$phase" \
        -v "$volume:/home/retro" -v "$root/tests:/tests:ro" -v "$artifacts:/artifacts" "$image" /tests/container-entrypoint.sh \
        'install -d -m 0700 -o 1000 -g 1000 /home/retro/.cache/wolf-lutris-tests; exec gosu "$UNAME" env TMPDIR=/home/retro/.cache/wolf-lutris-tests python3 /tests/recreation.py "$HARNESS_PHASE"'
done
python3 - "$artifacts" <<'PY'
import json, sys
from pathlib import Path
for phase in (1, 2):
    data = json.loads((Path(sys.argv[1]) / f'recreation-{phase}.json').read_text())
    assert data['status'] == 'pass' and data['recreation_phase'] == phase
PY
