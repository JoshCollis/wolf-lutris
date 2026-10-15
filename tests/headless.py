#!/usr/bin/env python3
"""Disposable Sway + supervised Openbox/Lutris acceptance. No GPU/FPS claims."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

SESSION = '/opt/wolf-lutris/session.py'
spec = importlib.util.spec_from_file_location('refresh', '/opt/wolf-lutris/refresh.py')
refresh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(refresh)


def wait(fn, timeout=30, process=None, log=None):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if process is not None and process.poll() is not None:
            raise AssertionError(f'Process exited {process.returncode}: ' + (log.read_text()[-16000:] if log else ''))
        value = fn()
        if value:
            return value
        time.sleep(.1)
    raise AssertionError('Timed out: ' + (log.read_text()[-16000:] if log else repr(fn)))


def stop(p):
    if p is not None and p.poll() is None:
        p.terminate()
        try: p.wait(timeout=12)
        except subprocess.TimeoutExpired:
            p.kill(); p.wait(timeout=5)


def descendants(pid):
    found = set()
    todo = [pid]
    while todo:
        current = todo.pop()
        try:
            children = Path(f'/proc/{current}/task/{current}/children').read_text().split()
        except FileNotFoundError:
            continue
        for child in children:
            n = int(child)
            if n not in found:
                found.add(n); todo.append(n)
    return found


def alive(pid):
    try:
        # Zombies cannot own an X socket, audio stream or profile lease.
        return Path(f'/proc/{pid}/stat').read_text().split(') ', 1)[1][0] != 'Z'
    except FileNotFoundError:
        return False


class Parent:
    def __init__(self, root, rate):
        self.root = root
        self.runtime = root / 'runtime'; self.runtime.mkdir(mode=0o700)
        config = root / 'sway.conf'
        config.write_text(f'output HEADLESS-1 mode --custom 1280x720@{rate}Hz\nxwayland disable\n')
        self.env = os.environ | {'XDG_RUNTIME_DIR': str(self.runtime), 'WLR_BACKENDS': 'headless',
                                'WLR_LIBINPUT_NO_DEVICES': '1', 'WLR_RENDERER': 'pixman',
                                'LIBGL_ALWAYS_SOFTWARE': '1'}
        for key in ('WAYLAND_DISPLAY', 'WAYLAND_SOCKET', 'SWAYSOCK', 'DISPLAY', 'DBUS_SESSION_BUS_ADDRESS'):
            self.env.pop(key, None)
        self.log = root / 'sway.log'
        with self.log.open('w') as out:
            self.proc = subprocess.Popen(['sway', '--unsupported-gpu', '-c', str(config)], env=self.env, stdout=out, stderr=out)
        self.socket = wait(lambda: next((p for p in self.runtime.glob('wayland-*') if p.is_socket()), None), process=self.proc, log=self.log)
        def mode_ready():
            try:
                modes = refresh.parent_modes(str(self.socket))
                refresh.require_parent_mode(modes, 1280, 720, rate)
                return modes
            except (OSError, RuntimeError):
                return None
        self.modes = wait(mode_ready, process=self.proc, log=self.log)
        self.ipc = wait(lambda: next(self.runtime.glob('sway-ipc.*.sock'), None))

    def mode(self, rate):
        subprocess.run(['swaymsg', '-s', str(self.ipc),
                        f'output HEADLESS-1 mode --custom 1280x720@{rate}Hz'],
                       check=True, timeout=10, capture_output=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='/artifacts/headless.json')
    parser.add_argument('--require-cadence', action='store_true', help='Gate Present COPY rate within 5%%; still NOT Moonlight/GPU acceptance')
    args = parser.parse_args()
    assert os.getuid() != 0, 'Run through gosu "$UNAME" after the GoW init entrypoint'
    results = []
    output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='wolf-lutris-') as temp:
        base = Path(temp)
        home = base / 'home'; home.mkdir(mode=0o700)
        # Reusing this HOME across completely fresh parents proves persistence without
        # importing any real user profile. The final case removes/recreates HOME.
        cases = [(60, 'normal'), (90, 'normal'), (120, 'normal'), (144, 'normal'),
                 (60, 'mismatch'), (60, 'parent-loss'), (60, 'mode-change'),
                 (60, 'signal'), (60, 'recreated-home')]
        try:
            for index, (rate, action) in enumerate(cases):
                if action == 'recreated-home':
                    import shutil
                    shutil.rmtree(home); home.mkdir(mode=0o700)
                root = base / str(index); root.mkdir(mode=0o700)
                client = root / 'client'; client.mkdir(mode=0o700)
                parent = Parent(root, rate)
                proc = None
                record = {'parent_Hz': rate, 'action': action, 'parent_modes': parent.modes}
                try:
                    request = 144 if action == 'mismatch' else rate
                    env = parent.env | {'HOME': str(home), 'XDG_CONFIG_HOME': str(home / '.config'),
                        'XDG_DATA_HOME': str(home / '.local/share'), 'XDG_CACHE_HOME': str(home / '.cache'),
                        'WOLF_LUTRIS_PARENT_WAYLAND': str(parent.socket), 'WAYLAND_DISPLAY': str(parent.socket),
                        'GAMESCOPE_WIDTH': '1280', 'GAMESCOPE_HEIGHT': '720', 'GAMESCOPE_REFRESH': str(request)}
                    log = root / 'session.log'
                    command = ['python3', SESSION, 'python3', '/tests/session-client.py', '--root', str(client), '--rate', str(request)]
                    if index == 0: command.append('--features')
                    with log.open('w') as out:
                        proc = subprocess.Popen(command, env=env, stdout=out, stderr=out)
                    if action == 'mismatch':
                        code = proc.wait(timeout=20)
                        assert code == 75, f'Mismatched parent returned {code}: {log.read_text()}'
                        assert not (client / 'ready.json').exists()
                    else:
                        ready = client / 'ready.json'
                        wait(ready.exists, timeout=300, process=proc, log=log)
                        record.update(json.loads(ready.read_text()))
                        pids = descendants(proc.pid)
                        assert len(pids) >= 3, f'Expected Xwayland, Openbox and client children, got {pids}'
                        if index in (0, 8): assert record['previous_marker'] is None
                        else: assert record['previous_marker'] == 'retained across session recreation'
                        # A second supervisor must fail its lease before disturbing the first.
                        if index == 0:
                            duplicate = subprocess.run(['python3', SESSION, '/bin/true'], env=env, timeout=15, capture_output=True, text=True)
                            assert duplicate.returncode != 0, 'Concurrent HOME writer accepted'
                            assert proc.poll() is None, 'Duplicate supervisor killed the original'
                        if action == 'parent-loss': stop(parent.proc)
                        elif action == 'mode-change': parent.mode(90)
                        elif action == 'signal': proc.send_signal(signal.SIGTERM)
                        else: (client / 'finish').touch()
                        code = proc.wait(timeout=25)
                        expected = 75 if action in ('parent-loss', 'mode-change') else 0
                        assert code == expected, f'{action}: exit {code} != {expected}: {log.read_text()}'
                        wait(lambda: not any(alive(pid) for pid in pids), timeout=12)
                        record['children_reaped'] = sorted(pids)
                    record['exit'] = code
                    if 'present' in record:
                        copy_hz = record['present'].get('copy_Hz')
                        record['software_cadence_pass'] = bool(copy_hz and abs(copy_hz / rate - 1) <= .05)
                        if args.require_cadence:
                            assert record['software_cadence_pass'], record
                    record['status'] = 'pass'
                    results.append(record)
                    output.write_text(json.dumps({'status': 'running', 'cases': results}, indent=2) + '\n')
                    print(f'PASS {rate}Hz {action}', flush=True)
                except Exception as exc:
                    record['error'] = str(exc)
                    if (client / 'progress.json').exists():
                        record['client_progress'] = json.loads((client / 'progress.json').read_text())
                    record['client_logs'] = {p.name: p.read_text()[-16000:] for p in client.glob('*.log')}
                    record['session_log'] = (root / 'session.log').read_text()[-32000:] if (root / 'session.log').exists() else ''
                    record['sway_log'] = parent.log.read_text()[-16000:]
                    record['status'] = 'failed'; results.append(record)
                    raise
                finally:
                    stop(proc); stop(parent.proc)
            assert len(results) == len(cases)
        finally:
            output.write_text(json.dumps({'status': 'pass' if len(results) == len(cases) and all(r['status'] == 'pass' for r in results) else 'failed',
                                         'scope': 'software-headless only; no Wolf/encoder/Moonlight FPS certification',
                                         'cases': results}, indent=2) + '\n')
    print('PASS: actual GTK installer, 32/64-bit ALSA/Pulse routing, refresh matrix, lease/persistence and supervisor lifecycle')


if __name__ == '__main__':
    main()
