#!/usr/bin/env python3
"""Real application-side assertions; launched ONLY through session.py."""
import argparse
import array
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import time


def run(argv, **kwargs):
    return subprocess.run(argv, check=True, capture_output=True, text=True, timeout=30, **kwargs).stdout


def wait(fn, timeout=30):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        result = fn()
        if result:
            return result
        time.sleep(.1)
    raise AssertionError('Timed out waiting for ' + repr(fn))


def windows():
    p = subprocess.run(['xdotool', 'search', '--onlyvisible', '--name', '.'], capture_output=True, text=True)
    return {wid: run(['xdotool', 'getwindowname', wid]).strip() for wid in p.stdout.split()}


def audio(root):
    env = os.environ.copy()
    env.pop('PULSE_SERVER', None)
    # A private server, no access to the host audio or a fixed production sink.
    socket = root / 'pulse.sock'
    env.update(PULSE_SERVER='unix:' + str(socket), PULSE_SINK='chosen')
    log = (root / 'pulse.log').open('w')
    pulse = subprocess.Popen(['pulseaudio', '--daemonize=no', '--exit-idle-time=-1', '-n',
                              '--load=module-native-protocol-unix socket=' + str(socket) + ' auth-anonymous=1',
                              '--load=module-null-sink sink_name=wrong',
                              '--load=module-null-sink sink_name=chosen'], env=env, stdout=log, stderr=log)
    results = []
    try:
        wait(lambda: socket.exists())
        run(['pactl', 'set-default-sink', 'wrong'], env=env)
        for bits in (64, 32):
            binary = root / ('audio-' + str(bits))
            run(['gcc', '-m' + str(bits), '/tests/audio-probe.c', '-o', str(binary), '-ldl', '-lm'])
            assert binary.read_bytes()[4] == (2 if bits == 64 else 1)
            recordings = []
            for sink in ('chosen', 'wrong'):
                path = root / f'{bits}-{sink}.raw'
                out = path.open('wb')
                proc = subprocess.Popen(['parec', '--device=' + sink + '.monitor', '--format=s16le',
                                         '--rate=48000', '--channels=2', '--raw'], env=env, stdout=out)
                recordings.append((proc, out, path))
            try:
                time.sleep(.3)
                run([str(binary)], env=env)
                time.sleep(.3)
            finally:
                for proc, out, path in recordings:
                    proc.terminate(); proc.wait(timeout=5); out.close()
            energies = []
            for _, _, path in recordings:
                samples = array.array('h'); samples.frombytes(path.read_bytes())
                assert len(samples) > 4800, f'No captured samples: {path}'
                energies.append(math.sqrt(sum(x*x for x in samples) / len(samples)))
            assert energies[0] > 500, energies
            assert energies[1] < 10, f'Audio leaked to the default, unselected sink: {energies}'
            results.append({'bits': bits, 'selected_rms': energies[0], 'default_rms': energies[1]})
        return results
    finally:
        pulse.terminate(); pulse.wait(timeout=10); log.close()


def gui(root):
    log = (root / 'lutris.log').open('w')
    lutris = subprocess.Popen(['lutris'], stdout=log, stderr=log)
    installer = None
    try:
        main = wait(lambda: next((w for w, title in windows().items() if title.lower() == 'lutris'), None), 90)
        # Verify this is a WM-managed normal client, not just an unmapped GTK process.
        tree = run(['xwininfo', '-id', main, '-tree'])
        state = run(['xprop', '-id', main, 'WM_STATE'])
        assert 'Normal' in state, state
        run(['xdotool', 'windowactivate', '--sync', main])
        script = root / 'offline-installer.yml'
        script.write_text('name: Harness Offline Game\ngame_slug: harness-offline-game\nversion: Local test\nslug: harness-offline-local\nrunner: linux\nscript:\n  game:\n    exe: /bin/true\n  installer: []\n')
        old = set(windows())
        installer = subprocess.Popen(['lutris', '-i', str(script)], stdout=log, stderr=log)
        dialog = wait(lambda: next(((w, t) for w, t in windows().items()
                                  if w not in old and ('install' in t.lower() or 'harness' in t.lower())), None), 60)
        return {'main_window': main, 'installer_window': dialog, 'window_tree': tree}
    finally:
        for p in (installer, lutris):
            if p is not None and p.poll() is None:
                p.terminate()
                try: p.wait(timeout=10)
                except subprocess.TimeoutExpired: p.kill(); p.wait()
        log.close()


def native(root):
    trigger = root / 'native-dialog'
    proc = subprocess.Popen(['python3', '/tests/native-window.py', str(trigger)])
    try:
        wid = wait(lambda: next((w for w, t in windows().items() if t == 'Harness Native Window'), None))
        wait(lambda: 'Normal' in run(['xprop', '-id', wid, 'WM_STATE']))
        run(['xdotool', 'windowactivate', '--sync', wid])
        wait(lambda: run(['xdotool', 'getwindowfocus']).strip() == wid)
        run(['xdotool', 'windowsize', '--sync', wid, '640', '360'])
        geometry = run(['xdotool', 'getwindowgeometry', '--shell', wid])
        assert 'WIDTH=640' in geometry and 'HEIGHT=360' in geometry, geometry
        # Exercise the WM's standard maximize request rather than assuming a
        # particular distro keybinding (Fedora Openbox does not bind Alt-F10).
        from Xlib import X, display, protocol
        connection = display.Display()
        event = protocol.event.ClientMessage(window=int(wid),
            client_type=connection.intern_atom('_NET_WM_STATE'),
            data=(32, [1, connection.intern_atom('_NET_WM_STATE_MAXIMIZED_HORZ'),
                       connection.intern_atom('_NET_WM_STATE_MAXIMIZED_VERT'), 1, 0]))
        connection.screen().root.send_event(event,
            event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
        connection.sync(); connection.close()
        state = wait(lambda: (s if 'MAXIMIZED_HORZ' in s and 'MAXIMIZED_VERT' in s else None)
                     if (s := run(['xprop', '-id', wid, '_NET_WM_STATE'])) else None)
        trigger.touch()
        dialog = wait(lambda: next((w for w, t in windows().items() if t == 'Harness Transient Dialog'), None))
        transient = run(['xprop', '-id', dialog, 'WM_TRANSIENT_FOR'])
        assert hex(int(wid)).lower() in transient.lower(), transient
        run(['xdotool', 'windowactivate', '--sync', dialog])
        wait(lambda: run(['xdotool', 'getwindowfocus']).strip() == dialog)
        return {'window': wid, 'geometry': geometry, 'maximized': state, 'dialog': dialog, 'transient': transient}
    finally:
        proc.terminate(); proc.wait(timeout=10)


def wine(root):
    import shutil
    exe = shutil.which('wine') or shutil.which('wine64')
    assert exe, 'System Wine executable missing'
    prefix = Path.home() / 'harness-wineprefix'
    assert not prefix.exists(), 'Wine test must use a new disposable prefix'
    env = os.environ | {'WINEPREFIX': str(prefix), 'WINEARCH': 'win64', 'WINEDEBUG': '-all',
                        'WINEDLLOVERRIDES': 'mscoree,mshtml='}
    result = subprocess.run([exe, 'cmd', '/c', 'ver'], env=env, capture_output=True, text=True, timeout=90)
    assert result.returncode == 0 and 'Windows' in result.stdout, (result.returncode, result.stdout, result.stderr)
    assert (prefix / 'system.reg').is_file(), 'Wine prefix was not initialized'
    return {'scope': 'system Wine only; not GE-Proton or a game', 'command': [exe, 'cmd', '/c', 'ver'],
            'exit': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr[-8000:]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--rate', type=int, required=True)
    parser.add_argument('--features', action='store_true')
    args = parser.parse_args()
    assert os.getuid() != 0
    root = args.root
    env = {key: os.environ.get(key) for key in ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY',
           'DBUS_SESSION_BUS_ADDRESS', 'HOME', 'XDG_RUNTIME_DIR', 'GDK_BACKEND', 'QT_QPA_PLATFORM')}
    assert env['DISPLAY'] and env['XAUTHORITY'] and env['DBUS_SESSION_BUS_ADDRESS'], env
    assert Path(env['XAUTHORITY']).stat().st_mode & 0o077 == 0
    assert Path(env['XDG_RUNTIME_DIR']).stat().st_mode & 0o077 == 0
    assert env['WAYLAND_DISPLAY'] is None and env['GDK_BACKEND'] == 'x11', env
    unauthorized = subprocess.run(['xdpyinfo'], env=os.environ | {'XAUTHORITY': str(root / 'no-cookie')},
                                  capture_output=True, text=True, timeout=5)
    assert unauthorized.returncode != 0, 'X11 server accepted a client without the private cookie'
    run(['dbus-send', '--session', '--print-reply', '--dest=org.freedesktop.DBus', '/', 'org.freedesktop.DBus.ListNames'])
    randr = run(['xrandr', '--current'])
    current = next(line for line in randr.splitlines() if '*' in line)
    hz = float(re.search(r'([0-9.]+)\*', current)[1])
    assert current.split()[0] == '1280x720' and abs(hz - args.rate) < 1, randr
    # A clean disposable HOME is reused between separate supervisor instances.
    marker = Path.home() / 'harness-persistence'
    previous = marker.read_text() if marker.exists() else None
    marker.write_text('retained across session recreation')
    present = json.loads(run(['/usr/local/libexec/wolf-lutris/present-probe']))
    result = {'env': env, 'pid': os.getpid(), 'randr': randr, 'randr_Hz': hz,
              'present': present, 'previous_marker': previous}
    (root / 'progress.json').write_text(json.dumps(result, indent=2))
    if args.features:
        for name, check in (('native', native), ('audio', audio), ('wine', wine), ('gui', gui)):
            result['running_feature'] = name
            (root / 'progress.json').write_text(json.dumps(result, indent=2))
            result[name] = check(root)
            (root / 'progress.json').write_text(json.dumps(result, indent=2))
        result.pop('running_feature', None)
    (root / 'ready.json').write_text(json.dumps(result, indent=2))
    # Session lifetime remains under the supervisor; SIGTERM must reap all children.
    while not (root / 'finish').exists():
        time.sleep(.1)


if __name__ == '__main__':
    main()
