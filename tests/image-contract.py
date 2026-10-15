#!/usr/bin/env python3
"""Run against the exact runtime image, not the dependency-enriched test stage."""
import ctypes
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


def run(*args):
    p = subprocess.run(args, capture_output=True, text=True, timeout=30, check=True)
    return p.stdout + p.stderr


def main():
    # Refuse a stale tag: host-side unit tests must correspond to baked scripts.
    expected_root = Path('/expected')
    assert expected_root.is_dir(), 'Mount the reviewed overlay at /expected read-only'
    for relative in ('opt/gow/startup.sh', 'opt/wolf-lutris/session.py',
                     'opt/wolf-lutris/desktop.py', 'opt/wolf-lutris/refresh.py',
                     'etc/cont-init.d/05-lutris-runtime.sh', 'etc/cont-init.d/10-setup_user.sh',
                     'etc/alsa/conf.d/99-wolf-pulse.conf'):
        assert (expected_root / relative).read_bytes() == Path('/' + relative).read_bytes(), f'Stale image file: {relative}'
    assert not Path('/etc/cont-init.d/init-gamescope.sh').exists(), 'Unused gamescope user/group hook retained'
    release = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    assert release['ID'].strip('"') == 'fedora' and release['VERSION_ID'].strip('"') == '44', release
    for exe in ('lutris', 'openbox', 'wine', 'dbus-run-session', 'xauth', 'xdpyinfo', 'xrandr', 'pactl', 'aplay', 'gosu'):
        assert shutil.which(exe), exe
    # Lutris constructs its GTK application before parsing --version, and
    # deliberately refuses root. Read its installed package version here;
    # the headless test launches the real UI as the application UID.
    versions = {'lutris': run('rpm', '-q', '--qf', '%{VERSION}', 'lutris')}
    versions.update({exe: run(exe, '--version') for exe in ('openbox', 'wine')})
    assert re.search(r'\b0\.5\.22\b', versions['lutris']), versions
    assert re.search(r'wine-11\.', versions['wine']), versions
    xwayland = '/usr/local/libexec/wolf-lutris/Xwayland'
    assert '24.1.14' in run(xwayland, '-version')
    for arch, cls in (('/usr/lib64', 2), ('/usr/lib', 1)):
        for kind in ('pcm', 'ctl'):
            plugin = Path(arch) / 'alsa-lib' / f'libasound_module_{kind}_pulse.so'
            assert plugin.read_bytes()[:5] == b'\x7fELF' + bytes([cls]), str(plugin)
            if cls == 2:
                ctypes.CDLL(str(plugin), mode=os.RTLD_NOW)
    packages = []
    for base in ('alsa-plugins-pulseaudio', 'wine-core', 'wine-pulseaudio', 'mesa-dri-drivers',
                 'mesa-vulkan-drivers', 'mesa-libGL', 'mesa-libEGL', 'vulkan-loader'):
        for arch in ('x86_64', 'i686'):
            packages.append(run('rpm', '-q', base + '.' + arch).strip())
    alsa = ctypes.CDLL('libasound.so.2')
    alsa.snd_config_update.restype = ctypes.c_int
    alsa.snd_config_search.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(ctypes.c_void_p)]
    alsa.snd_config_get_string.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_char_p)]
    assert alsa.snd_config_update() >= 0
    config = ctypes.c_void_p.in_dll(alsa, 'snd_config')
    effective_defaults = {}
    for name in ('pcm.default', 'ctl.default'):
        node = ctypes.c_void_p(); value = ctypes.c_char_p()
        assert alsa.snd_config_search(config, (name + '.type').encode(), ctypes.byref(node)) >= 0, name
        assert alsa.snd_config_get_string(node, ctypes.byref(value)) >= 0
        effective_defaults[name] = value.value.decode()
        assert value.value == b'pulse', f'Runtime ALSA config overridden by another provider: {name}={value.value!r}'
    assert Path('/opt/gow/startup.sh').is_file()
    assert Path('/opt/wolf-lutris/session.py').is_file()
    assert not Path('/usr/bin/bwrap').stat().st_mode & 0o6000, 'bwrap must not be setuid/setgid'
    for path in ('/usr/share/doc/wolf-lutris/xwayland/source.tar.xz',
                 '/usr/share/doc/wolf-lutris/xwayland/refresh.patch',
                 '/usr/share/wolf-lutris/packages.txt'):
        assert Path(path).stat().st_size > 0, path
    print(json.dumps({'status': 'pass', 'versions': versions, 'effective_alsa_defaults': effective_defaults, 'multilib_packages': packages}, indent=2))


if __name__ == '__main__':
    main()
