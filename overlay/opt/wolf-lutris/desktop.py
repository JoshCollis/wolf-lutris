#!/usr/bin/env python3
"""Private-bus Openbox + native client; children stay in supervisor-owned group."""
import signal
import subprocess
import sys
import time


def main(argv=None):
    command = list(sys.argv[1:] if argv is None else argv)
    if not command:
        command = ['/usr/bin/lutris']
    stopped = False
    def stop(signum, frame):
        nonlocal stopped
        stopped = True
    handlers = {sig: signal.signal(sig, stop) for sig in (signal.SIGTERM, signal.SIGINT)}
    children = []
    try:
        children.append(subprocess.Popen(['openbox', '--sm-disable']))
        children.append(subprocess.Popen(command))
        while True:
            # Loss of WM is not a successful logout even if Lutris also exits.
            if children[0].poll() is not None:
                return 1
            if stopped:
                return 0
            code = children[1].poll()
            if code is not None:
                return code if code >= 0 else 128 - code
            time.sleep(.05)
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
        deadline = time.monotonic() + 4
        while any(c.poll() is None for c in children) and time.monotonic() < deadline:
            time.sleep(.02)
        for child in reversed(children):
            if child.poll() is None:
                child.kill()
            child.wait()
        for sig, handler in handlers.items():
            signal.signal(sig, handler)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print(f'wolf-lutris desktop: {exc}', file=sys.stderr)
        sys.exit(1)
