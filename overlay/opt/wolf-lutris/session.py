#!/usr/bin/env python3
"""One native Lutris session on authenticated, rootful Xwayland (not UID root)."""
from contextlib import ExitStack
import fcntl
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time

from refresh import parent_modes, require_parent_mode


def requested(env):
    values = [env.get(k, '') for k in ('GAMESCOPE_WIDTH', 'GAMESCOPE_HEIGHT', 'GAMESCOPE_REFRESH')]
    if any(not re.fullmatch(r'[0-9]+', v) for v in values):
        raise ValueError('Wolf must supply integer GAMESCOPE_WIDTH/HEIGHT/REFRESH; no refresh default')
    w, h, r = map(int, values)
    if not (320 <= w <= 16384 and 200 <= h <= 16384 and 1 <= r <= 240):
        raise ValueError('Unsupported negotiated Wolf mode')
    return w, h, r


def completed(code, wanted, actual):
    try:
        require_parent_mode(actual, *wanted)
    except RuntimeError:
        return 75
    return code if code >= 0 else 128 - code


def lease(home):
    fd = os.open(home / '.wolf-lutris.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise ValueError('HOME lease must be a regular file')
    handle = os.fdopen(fd, 'w')
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        handle.close()
        raise
    return handle


def validate_runtime(path):
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError('XDG_RUNTIME_DIR must be a real directory owned by desktop UID, mode 0700')


def parent_socket(env):
    parent = env.get('WOLF_LUTRIS_PARENT_WAYLAND', '')
    if not parent.startswith('/') or not Path(parent).is_socket():
        raise ValueError('Exact absolute WOLF_LUTRIS_PARENT_WAYLAND socket required')
    return parent


def client_args(argv):
    return list(argv) if argv else ['/usr/bin/lutris']


def desktop_environment(source):
    env = source.copy()
    for key in ('WAYLAND_DISPLAY', 'WAYLAND_SOCKET', 'WOLF_LUTRIS_PARENT_WAYLAND',
                'DBUS_SESSION_BUS_ADDRESS', 'DBUS_SESSION_BUS_PID', 'SESSION_MANAGER'):
        env.pop(key, None)
    env.update(GDK_BACKEND='x11', QT_QPA_PLATFORM='xcb', XDG_SESSION_TYPE='x11',
               XDG_CURRENT_DESKTOP='Openbox', DESKTOP_SESSION='openbox')
    return env


def xwayland_environment(source, parent):
    env = source.copy()
    env.pop('WAYLAND_SOCKET', None)
    env['WAYLAND_DISPLAY'] = parent
    return env


def xwayland_args(mode, auth):
    w, h, rate = mode
    return ['/usr/local/libexec/wolf-lutris/Xwayland', ':0', '-fullscreen', '-geometry', f'{w}x{h}',
            '-fakescreenfps', str(rate), '-nolisten', 'tcp', '-noreset', '-auth', auth]


def seed_config(env):
    directory = Path(env.get('XDG_CONFIG_HOME', str(Path(env['HOME']) / '.config'))) / 'lutris'
    directory.mkdir(parents=True, exist_ok=True)
    try:
        with (directory / 'system.yml').open('x') as handle:
            handle.write('system:\n  game_path: /var/lutris/Games\n')
    except FileExistsError:
        pass


def shutdown(children, timeout=5):
    # Always signal owned groups, including after their leader exited.
    for child in reversed(children):
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + timeout
    while any(c.poll() is None for c in children) and time.monotonic() < deadline:
        time.sleep(.02)
    for child in reversed(children):
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.wait()


def monitor(xserver, desktop, mode, read_parent, stopped):
    while True:
        # Parent loss/change wins over simultaneous clean client or X exit.
        try:
            if completed(0, mode, read_parent()) == 75:
                print('Wolf parent mode changed; recreate lobby', file=sys.stderr)
                return 75
        except (OSError, RuntimeError, ValueError):
            print('Wolf parent lost; recreate lobby', file=sys.stderr)
            return 75
        if xserver.poll() is not None:
            return 1
        if stopped():
            return 0
        code = desktop.poll()
        if code is not None:
            return completed(code, mode, read_parent())
        time.sleep(.5)


def main(argv=None):
    if os.getuid() == 0:
        raise ValueError('Lutris must run as the unprivileged GoW user')
    env = os.environ.copy()
    runtime = Path(env['XDG_RUNTIME_DIR'])
    validate_runtime(runtime)
    parent = parent_socket(env)
    mode = requested(env)
    stopped = False
    def stop(signum, frame):
        nonlocal stopped
        stopped = True
    previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGTERM, signal.SIGINT)}
    children = []
    auth = None
    try:
        with ExitStack() as cleanup:
            cleanup.enter_context(lease(Path(env['HOME'])))
            cleanup.callback(shutdown, children)
            try:
                require_parent_mode(parent_modes(parent), *mode)
            except (OSError, RuntimeError, ValueError) as exc:
                print(f'Wolf parent unavailable or mismatched; recreate lobby: {exc}', file=sys.stderr)
                return 75
            seed_config(env)
            if not Path('/dev/snd/seq').exists():
                print('wolf-lutris: /dev/snd/seq absent; MIDI sequencer unavailable (not required for ordinary audio)', file=sys.stderr)
            fd, auth_name = tempfile.mkstemp(prefix='wolf-lutris.Xauthority-', dir=runtime)
            auth = Path(auth_name)
            os.close(fd)
            env.update(DISPLAY=':0', XAUTHORITY=str(auth))
            subprocess.run(['xauth', '-f', str(auth), 'add', ':0', '.', os.urandom(16).hex()], check=True, timeout=5)
            children.append(subprocess.Popen(xwayland_args(mode, str(auth)), env=xwayland_environment(env, parent), start_new_session=True))
            deadline = time.monotonic() + 30
            while True:
                try:
                    if completed(0, mode, parent_modes(parent)) == 75:
                        return 75
                except (OSError, RuntimeError, ValueError):
                    return 75
                if stopped:
                    return 0
                if children[0].poll() is not None:
                    raise RuntimeError('Xwayland exited before readiness')
                try:
                    if subprocess.run(['xdpyinfo'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1).returncode == 0:
                        break
                except subprocess.TimeoutExpired:
                    pass
                if time.monotonic() >= deadline:
                    raise RuntimeError('Xwayland readiness timed out after 30 seconds')
                time.sleep(.1)
            command = client_args(sys.argv[1:] if argv is None else argv)
            children.append(subprocess.Popen(['dbus-run-session', '--', 'python3', '/opt/wolf-lutris/desktop.py', *command],
                                             env=desktop_environment(env), start_new_session=True))
            print(f'wolf-lutris: native X11/Openbox {mode[0]}x{mode[1]}@{mode[2]} UID={os.getuid()}', flush=True)
            try:
                return monitor(children[0], children[1], mode, lambda: parent_modes(parent), lambda: stopped)
            except (OSError, RuntimeError):
                return 75
    finally:
        # Only remove the unique cookie created by this launch.
        if auth is not None:
            auth.unlink(missing_ok=True)
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print(f'wolf-lutris: {exc}', file=sys.stderr)
        sys.exit(1)
