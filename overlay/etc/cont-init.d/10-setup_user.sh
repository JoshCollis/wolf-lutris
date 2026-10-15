#!/usr/bin/env bash
# Replace GoW's destructive account recreation. Never remove accounts or homes.
set -e
[[ ${UNAME:-lutris} =~ ^[a-z_][a-z0-9_-]*$ && ${UNAME:-lutris} != root ]] || { printf '%s\n' 'Invalid desktop account name' >&2; exit 1; }
if getent passwd "$PUID" >/dev/null; then
    # Reuse the existing numeric identity. gosu must use its real account name.
    UNAME="$(getent passwd "$PUID" | cut -d: -f1)"
    export UNAME
    [[ $(id -g "$UNAME") = "$PGID" ]] || { printf '%s\n' 'Existing PUID has a different primary PGID; refusing account mutation' >&2; exit 1; }
elif getent passwd "$UNAME" >/dev/null; then
    printf '%s\n' 'Requested desktop name belongs to a different UID; refusing account mutation' >&2
    exit 1
else
    if ! getent group "$PGID" >/dev/null; then
        groupadd --gid "$PGID" "wolf-lutris-$PGID"
    fi
    useradd --no-create-home --home-dir "$HOME" --uid "$PUID" --gid "$PGID" --shell /bin/bash "$UNAME"
fi
# Mount roots only: never traverse user data or Wolf's socket directory.
for directory in "$HOME" /var/lutris; do
    [[ ! -L $directory ]] || { printf 'Refusing symlink mount root: %s\n' "$directory" >&2; exit 1; }
    mkdir -p -- "$directory"
    chown -- "$PUID:$PGID" "$directory"
done
if [[ ! -e /var/lutris/Games ]]; then
    install -d -m 0755 -o "$PUID" -g "$PGID" /var/lutris/Games
fi
umask "${UMASK:-022}"
