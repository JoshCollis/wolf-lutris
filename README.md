# wolf-lutris

A Lutris container for [Games on Whales](https://games-on-whales.github.io/wolf/stable/).

It provides Lutris, Wine, Openbox, Xwayland, Vulkan libraries, and PulseAudio support for 64-bit and 32-bit games.

## Image

```text
ghcr.io/joshcollis/wolf-lutris:latest
```

An example Wolf app configuration is available at [`examples/wolf-lutris.toml`](examples/wolf-lutris.toml). Update its host paths before use.

Persistent data is stored in:

- `/home/retro` for Lutris configuration and user data
- `/var/lutris` for installed games

## Build

```sh
docker pull --platform linux/amd64 ghcr.io/games-on-whales/base-app:fedora
base=$(docker image inspect ghcr.io/games-on-whales/base-app:fedora --format '{{index .RepoDigests 0}}')

docker buildx build --pull --load --platform linux/amd64 \
  --no-cache-filter xwayland,runtime-deps,runtime \
  --target runtime \
  --build-arg BASE_IMAGE="$base" \
  --build-arg BASE_DIGEST="${base#*@}" \
  -t wolf-lutris:local .
```

## Test

```sh
docker buildx build --pull --load --platform linux/amd64 \
  --target test \
  --build-arg BASE_IMAGE="$base" \
  --build-arg BASE_DIGEST="${base#*@}" \
  -t wolf-lutris:test .

bash tests/lint.sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
bash tests/run.sh wolf-lutris:test
bash tests/runtime-image.sh wolf-lutris:local
```

## Support and updates

CI resolves the current official GoW Fedora base to an immutable digest and builds
`linux/amd64` with `--pull`. Every run bypasses the package-stage cache, checks the
base's declared support end date (missing or expired dates fail closed), and runs
`dnf upgrade --refresh` within that Fedora release's signed repositories. There are
no COPRs/PPAs or cross-release DNF upgrades. Lutris, system Wine and GPU/audio
libraries follow Fedora packages, not an unverified claim of upstream "latest".

As checked on 2026-11-03, [upstream stable is v0.5.22](https://github.com/lutris/lutris/releases/latest)
(released 2026-02-25), and [Fedora 44 ships 0.5.22-1.fc44](https://packages.fedoraproject.org/pkgs/lutris/lutris/).
[Lutris recommends the official Fedora repositories](https://lutris.net/downloads).
If Fedora lags upstream, report the mismatch and review a supported signed route;
do not silently add an unsupported feed. Candidate OS/package versions and base
labels are recorded in CI's `acceptance-evidence` artifact; installed RPMs are also
listed in `/usr/share/wolf-lutris/packages.txt`.
The runtime contract checks supported Fedora and reviewed Lutris/Wine minimums;
it does not pin those packages to historical exact versions or prove "latest".

The private rootful Xwayland stays checksum-pinned to 24.1.14 with its refresh
patch. A newer distribution Xwayland causes the existing source-version guard to
fail: patch compatibility needs review, not removal of the guard. The inherited
GoW init, native parent handoff, multilib GPU/audio, HOME/game mounts and security
contract are unchanged. Refreshing the image does not mass-upgrade user runners
or Wine prefixes or migrate games.

Pull requests build and test only. Successful `main` push/manual runs and the
weekly **Monday 06:03 UTC** schedule publish `latest` and a unique SHA/run/attempt
tag. Both `tests/run.sh` and `tests/runtime-image.sh` must pass before the exact
tested runtime is exported, loaded and published without rebuilding. CPU/software
acceptance is not Moonlight/GPU/game acceptance. Publishing does not pull onto
Gill, deploy to Wolf, restart sessions or prove live adoption; those remain
separate operator actions.

## License

MIT. See [`NOTICE.md`](NOTICE.md) for third-party software information.
