#!/usr/bin/env python3
"""Test-stage Pulse sidecar + untouched-runtime ALSA clients over one private volume."""
import array
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path('/pulse')
ENV = os.environ | {'PULSE_SERVER': 'unix:/pulse/native', 'PULSE_SINK': 'chosen'}


def wait(path, timeout=90):
    deadline = time.monotonic() + timeout
    while not path.exists():
        if time.monotonic() > deadline:
            raise AssertionError('Timed out: ' + str(path))
        time.sleep(.1)


def run(args, **kwargs):
    return subprocess.run(args, check=True, timeout=30, env=ENV, **kwargs)


def rms(path):
    samples = array.array('h'); samples.frombytes(path.read_bytes())
    assert len(samples) > 4800, f'Empty or short recording: {path}'
    return math.sqrt(sum(x*x for x in samples) / len(samples))


def server():
    assert os.getuid() == 1000
    for bits in (32, 64):
        run(['gcc', '-m' + str(bits), '/tests/audio-probe.c', '-o', f'/pulse/audio-{bits}', '-ldl', '-lm'])
    pulse = subprocess.Popen(['pulseaudio', '--daemonize=no', '--exit-idle-time=-1', '-n',
        '--load=module-native-protocol-unix socket=/pulse/native auth-anonymous=1',
        '--load=module-null-sink sink_name=wrong', '--load=module-null-sink sink_name=chosen'], env=ENV)
    results = []
    try:
        wait(ROOT / 'native')
        run(['pactl', 'set-default-sink', 'wrong'])
        (ROOT / 'ready').touch()
        for bits in (32, 64, 'aplay'):
            wait(ROOT / f'start-{bits}')
            recordings = []
            for sink in ('chosen', 'wrong'):
                path = ROOT / f'{bits}-{sink}.raw'; out = path.open('wb')
                proc = subprocess.Popen(['parec', '--raw', '--device=' + sink + '.monitor',
                    '--format=s16le', '--rate=48000', '--channels=2'], stdout=out, env=ENV)
                recordings.append((proc, out, path))
            try:
                time.sleep(.3)
                (ROOT / f'listening-{bits}').touch()
                wait(ROOT / f'done-{bits}')
                time.sleep(.3)
            finally:
                for proc, out, _ in recordings:
                    proc.terminate(); proc.wait(timeout=5); out.close()
            selected, default = [rms(path) for _, _, path in recordings]
            assert selected > 500 and default < 10, (bits, selected, default)
            results.append({'bits': bits, 'selected_rms': selected, 'default_rms': default})
        (ROOT / 'result.json').write_text(json.dumps({'status': 'pass', 'runtime_audio': results}, indent=2))
        print('PASS: untouched runtime ALSA routes real 32/64-bit PCM to PULSE_SINK, not the default sink')
    finally:
        pulse.terminate(); pulse.wait(timeout=10)


def client():
    assert os.getuid() == 1000
    wait(ROOT / 'ready')
    for bits in (32, 64, 'aplay'):
        if bits == 'aplay':
            import wave
            tone = ROOT / 'generated-tone.wav'
            samples = array.array('h')
            for i in range(72000):
                value = int(12000 * math.sin(2 * math.pi * 440 * i / 48000))
                samples.extend((value, value))
            with wave.open(str(tone), 'wb') as stream:
                stream.setnchannels(2); stream.setsampwidth(2); stream.setframerate(48000)
                stream.writeframes(samples.tobytes())
            command = ['aplay', '-q', str(tone)]
        else:
            binary = ROOT / f'audio-{bits}'
            assert binary.read_bytes()[:5] == b'\x7fELF' + bytes([1 if bits == 32 else 2])
            command = [str(binary)]
        (ROOT / f'start-{bits}').touch()
        wait(ROOT / f'listening-{bits}')
        run(command)
        (ROOT / f'done-{bits}').touch()
    wait(ROOT / 'result.json')
    result = json.loads((ROOT / 'result.json').read_text())
    assert result['status'] == 'pass' and len(result['runtime_audio']) == 3
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    {'server': server, 'client': client}[sys.argv[1]]()
