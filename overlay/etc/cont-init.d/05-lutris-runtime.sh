#!/usr/bin/env bash
# Sourced by the retained GoW entrypoint before device/Nvidia hooks.
# Adapted from whale-plasma (MIT): exact socket only, never shared tree changes.
export PUID="${PUID:-1000}" PGID="${PGID:-1000}" UNAME="${UNAME:-lutris}"
export HOME="${HOME:-/home/retro}"
[[ $PUID =~ ^[0-9]+$ && $PGID =~ ^[0-9]+$ && $PUID != 0 && $PGID != 0 ]] || { printf '%s\n' 'Nonzero numeric PUID/PGID required' >&2; exit 1; }
if [[ -z ${WOLF_LUTRIS_PARENT_WAYLAND:-} ]]; then
    if [[ ${WAYLAND_DISPLAY:-} = /* ]]; then
        export WOLF_LUTRIS_PARENT_WAYLAND="$WAYLAND_DISPLAY"
    else
        export WOLF_LUTRIS_PARENT_WAYLAND="${XDG_RUNTIME_DIR:?Wolf runtime directory required}/${WAYLAND_DISPLAY:?Wolf Wayland display required}"
    fi
fi
[[ $WOLF_LUTRIS_PARENT_WAYLAND = /* && -S $WOLF_LUTRIS_PARENT_WAYLAND && ! -L $WOLF_LUTRIS_PARENT_WAYLAND ]] || { printf '%s\n' 'Exact absolute Wolf parent socket required' >&2; exit 1; }
chown -- "$PUID:$PGID" "$WOLF_LUTRIS_PARENT_WAYLAND"
install -d -m 1777 /tmp/.X11-unix /tmp/.ICE-unix
export XDG_RUNTIME_DIR="/run/user/$PUID"
[[ ! -L $XDG_RUNTIME_DIR ]] || { printf '%s\n' 'Runtime directory must not be a symlink' >&2; exit 1; }
install -d -m 0700 -o "$PUID" -g "$PGID" "$XDG_RUNTIME_DIR"
