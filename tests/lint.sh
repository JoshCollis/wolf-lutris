#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
mapfile -t scripts < <(python3 - "$root" <<'PY'
from pathlib import Path
import sys
root = Path(sys.argv[1])
for folder in ('tests', 'overlay'):
    for path in sorted((root / folder).rglob('*.sh')):
        print(path)
PY
)
for script in "${scripts[@]}"; do bash -n "$script"; done
if [[ ${#scripts[@]} -gt 0 ]]; then
    docker run --rm -v "$root:/src:ro" koalaman/shellcheck:v0.10.0 \
        --severity=warning "${scripts[@]/$root/\/src}"
fi
docker run --rm --entrypoint /bin/hadolint -v "$root:/src:ro" -w /src hadolint/hadolint:v2.12.0 \
    --config .hadolint.yaml Dockerfile
docker run --rm -v "$root:/src:ro" -w /src rhysd/actionlint:1.7.7 \
    -shellcheck='' .github/workflows/image.yml
python3 - "$root" <<'PY'
import ast
from pathlib import Path
import sys
root = Path(sys.argv[1])
count = 0
for folder in ('tests', 'overlay', 'build', 'scripts'):
    for path in (root / folder).rglob('*.py'):
        ast.parse(path.read_text(), filename=str(path))
        count += 1
print(f'PASS: parsed {count} Python files')
PY
