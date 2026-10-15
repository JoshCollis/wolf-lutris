#!/usr/bin/env bash
# Usage: bash tests/runtime-image.sh EXACT_RUNTIME_IMAGE
set -euo pipefail
image=${1:?Usage: bash tests/runtime-image.sh EXACT_RUNTIME_IMAGE}
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
docker image inspect "$image" --format 'Runtime under test: {{.Id}}'
docker run --rm --network none --entrypoint python3 \
    -e PYTHONDONTWRITEBYTECODE=1 -v "$root/tests:/tests:ro" -v "$root/overlay:/expected:ro" \
    "$image" /tests/image-contract.py
# The server/compiler live in the disposable test stage. Both generated ELF
# clients execute against the EXACT runtime filesystem and its ALSA config.
test_image=${WOLF_LUTRIS_TEST_IMAGE:-wolf-lutris:test}
artifacts=${WOLF_LUTRIS_ARTIFACT_DIR:-"$root/artifacts"}
mkdir -p "$artifacts"
chmod 0777 "$artifacts"
volume=$(docker volume create)
server=''
cleanup() {
    if [[ -n $server ]]; then docker rm -f "$server" >/dev/null 2>&1 || true; fi
    docker volume rm "$volume" >/dev/null
}
trap cleanup EXIT
server=$(docker run -d --network none --entrypoint bash -e PUID=1000 -e PGID=1000 -e UNAME=lutris \
    -v "$root/tests:/tests:ro" -v "$volume:/pulse" "$test_image" /tests/container-entrypoint.sh \
    'chown 1000:1000 /pulse; exec gosu "$UNAME" python3 /tests/runtime-audio.py server')
if ! docker run --rm --network none --user 1000:1000 --entrypoint python3 \
    -e HOME=/pulse -e PYTHONDONTWRITEBYTECODE=1 \
    -v "$root/tests:/tests:ro" -v "$volume:/pulse" "$image" /tests/runtime-audio.py client; then
    docker logs "$server" >&2
    exit 1
fi
status=$(docker wait "$server")
docker logs "$server"
[[ $status == 0 ]]
docker cp "$server:/pulse/result.json" "$artifacts/runtime-audio.json"
python3 - "$artifacts/runtime-audio.json" <<'PY'
import json, sys
from pathlib import Path
assert json.loads(Path(sys.argv[1]).read_text())['status'] == 'pass'
PY
