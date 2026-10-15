#!/usr/bin/env python3
"""Optional non-redistributed Clone Hero fixture check, outside CI.

Use a trusted separately obtained Linux release read-only at /fixture. Software
OpenGL only; result distinguishes audio initialization from game survival.
"""
import argparse
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def client(fixture, output, dismiss_analytics=False):
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    env = os.environ | {'PULSE_SERVER': 'unix:' + str(root / 'pulse.sock'), 'PULSE_SINK': 'chosen'}
    with (root / 'pulse.log').open('w') as log:
        pulse = subprocess.Popen(['pulseaudio', '--daemonize=no', '--exit-idle-time=-1', '-n',
            '--load=module-native-protocol-unix socket=' + str(root / 'pulse.sock') + ' auth-anonymous=1',
            '--load=module-null-sink sink_name=chosen'], env=env, stdout=log, stderr=log)
    game = None
    try:
        for _ in range(100):
            if (root / 'pulse.sock').exists():
                break
            if pulse.poll() is not None:
                raise RuntimeError('Diagnostic Pulse server failed')
            time.sleep(.1)
        probe = subprocess.run(['python3', '/src/scripts/probe-bass.py', str(fixture / 'clonehero_Data/Plugins/libbass.so')],
                               env=env, capture_output=True, text=True, timeout=15)
        result = {'BASS_probe_exit': probe.returncode, 'BASS_probe': probe.stdout, 'BASS_stderr': probe.stderr,
                  'fixture': 'official Clone Hero Linux 1.1.0.6142', 'MIDI_device': Path('/dev/snd/seq').exists(),
                  'scope': 'software OpenGL startup only; no gameplay/MIDI/controller/Moonlight certification'}
        (root / 'clonehero.json').write_text(json.dumps(result, indent=2) + '\n')
        if probe.returncode:
            raise RuntimeError('Native BASS audio initialization failed: ' + probe.stdout + probe.stderr)
        with (root / 'game-stdout.log').open('w') as log:
            game = subprocess.Popen([str(fixture / 'clonehero'), '-force-glcore', '-screen-width', '1280',
                '-screen-height', '720', '-screen-fullscreen', '0', '-logFile', str(root / 'Player.log')],
                cwd=fixture, env=env, stdout=log, stderr=log)
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline and game.poll() is None:
            time.sleep(.2)
        result['alive_after_40s'] = game.poll() is None
        if dismiss_analytics and game.poll() is None:
            # Optional probe for the exact pinned fresh 1.1.0.6142 fixture at
            # 1280x720: visually verified opt-out link, NOT the age/opt-in button.
            # Never use against a real user's HOME or a different game version.
            subprocess.run(['xdotool', 'mousemove', '350', '468', 'click', '1'], check=True, timeout=5)
            result['analytics_opt_out_link_clicked'] = True
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline and game.poll() is None:
                time.sleep(.2)
            result['alive_after_opt_out_20s'] = game.poll() is None
        result['game_exit_before_cleanup'] = game.poll()
        result['windows'] = subprocess.run(['xwininfo', '-root', '-tree'], capture_output=True, text=True, timeout=5).stdout
        if game.poll() is None:
            # Capture actual composited X pixels, not just a process/window count.
            from PIL import ImageGrab
            ImageGrab.grab().save(root / 'clonehero.png')
            if dismiss_analytics:
                import array
                import math
                with (root / 'menu-audio.raw').open('wb') as audio:
                    recorder = subprocess.Popen(['parec', '--device=chosen.monitor', '--format=s16le',
                        '--rate=48000', '--channels=2', '--raw'], env=env, stdout=audio)
                    try:
                        time.sleep(3)
                    finally:
                        recorder.terminate(); recorder.wait(timeout=5)
                samples = array.array('h')
                samples.frombytes((root / 'menu-audio.raw').read_bytes())
                result['menu_audio_samples'] = len(samples)
                result['menu_audio_rms'] = math.sqrt(sum(x*x for x in samples) / len(samples)) if samples else 0
                result['menu_audio_captured'] = len(samples) > 4800 and result['menu_audio_rms'] > 50
        result['game_exit_before_cleanup'] = game.poll()
        result['Player_log_tail'] = (root / 'Player.log').read_text(errors='replace')[-20000:] if (root / 'Player.log').exists() else ''
        (root / 'clonehero.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, indent=2), flush=True)
        if result['game_exit_before_cleanup'] is not None:
            return 2
        if dismiss_analytics and not result.get('menu_audio_captured'):
            return 3
        return 0
    finally:
        if game is not None and game.poll() is None:
            game.terminate()
            try:
                game.wait(timeout=10)
            except subprocess.TimeoutExpired:
                game.kill(); game.wait()
        pulse.terminate(); pulse.wait(timeout=10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client', action='store_true')
    parser.add_argument('--dismiss-analytics', action='store_true', help='Opt out on the visually verified fresh pinned fixture only')
    parser.add_argument('--fixture', type=Path, default=Path('/fixture'))
    parser.add_argument('--output', type=Path, default=Path('/artifacts/clonehero'))
    args = parser.parse_args()
    assert os.getuid() != 0
    if args.client:
        return client(args.fixture, args.output, args.dismiss_analytics)
    spec = importlib.util.spec_from_file_location('headless_fixture', '/tests/headless.py')
    helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
    with tempfile.TemporaryDirectory(prefix='clonehero-') as name:
        root = Path(name)
        parent = helper.Parent(root, 60)
        try:
            home = root / 'home'; home.mkdir(mode=0o700)
            env = parent.env | {'HOME': str(home), 'WOLF_LUTRIS_PARENT_WAYLAND': str(parent.socket),
                'GAMESCOPE_WIDTH': '1280', 'GAMESCOPE_HEIGHT': '720', 'GAMESCOPE_REFRESH': '60'}
            return subprocess.run(['python3', '/opt/wolf-lutris/session.py', 'python3', '/tests/clonehero.py',
                '--client', '--fixture', str(args.fixture), '--output', str(args.output),
                *(['--dismiss-analytics'] if args.dismiss_analytics else [])], env=env, timeout=110).returncode
        finally:
            helper.stop(parent.proc)


if __name__ == '__main__':
    sys.exit(main())
