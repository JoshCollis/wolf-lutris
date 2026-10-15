#!/usr/bin/env bash
set -euo pipefail
umask "${UMASK:-022}"
if [[ $(id -u) = 0 ]]; then
    printf '%s\n' 'Lutris must run as the GoW desktop user, not root.' >&2
    exit 1
fi
# Synthetic acceptance commands are argv, never shell-evaluated environment text.
exec tini -s -- python3 /opt/wolf-lutris/session.py "$@"
