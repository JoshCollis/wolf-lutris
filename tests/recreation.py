#!/usr/bin/env python3
"""One fresh container/parent per phase, sharing only a disposable HOME volume."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from headless import Parent, SESSION, descendants, alive, stop, wait

phase = int(sys.argv[1])
assert phase in (1, 2)
with tempfile.TemporaryDirectory(prefix='recreation-') as temp:
    root = Path(temp)
    parent = Parent(root, 60 if phase == 1 else 90)
    proc = None
    try:
        client = root / 'client'; client.mkdir(mode=0o700)
        rate = 60 if phase == 1 else 90
        env = parent.env | {'HOME': os.environ['HOME'], 'WOLF_LUTRIS_PARENT_WAYLAND': str(parent.socket),
                            'GAMESCOPE_WIDTH': '1280', 'GAMESCOPE_HEIGHT': '720', 'GAMESCOPE_REFRESH': str(rate)}
        log = root / 'session.log'
        with log.open('w') as out:
            proc = subprocess.Popen(['python3', SESSION, 'python3', '/tests/session-client.py',
                                     '--root', str(client), '--rate', str(rate)], env=env, stdout=out, stderr=out)
        ready = client / 'ready.json'
        wait(ready.exists, timeout=60, process=proc, log=log)
        result = json.loads(ready.read_text())
        assert result['previous_marker'] == (None if phase == 1 else 'retained across session recreation'), result
        config = Path.home() / '.config/lutris/system.yml'
        sentinel = '# harness: user configuration must survive GoW container init\n'
        if phase == 1:
            assert '/var/lutris/Games' in config.read_text()
            with config.open('a') as out: out.write(sentinel)
        else:
            assert sentinel in config.read_text(), 'Second container overwrote user configuration'
        pids = descendants(proc.pid)
        (client / 'finish').touch()
        assert proc.wait(timeout=25) == 0, log.read_text()
        wait(lambda: not any(alive(pid) for pid in pids), timeout=12)
        result.update(status='pass', recreation_phase=phase, config=config.read_text())
        Path(f'/artifacts/recreation-{phase}.json').write_text(json.dumps(result, indent=2))
        print(f'PASS disposable HOME volume across real container recreation, phase {phase}')
    finally:
        stop(proc); stop(parent.proc)
