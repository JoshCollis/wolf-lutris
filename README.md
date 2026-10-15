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
docker pull ghcr.io/games-on-whales/base-app:fedora
base=$(docker image inspect ghcr.io/games-on-whales/base-app:fedora --format '{{index .RepoDigests 0}}')

docker build \
  --target runtime \
  --build-arg BASE_IMAGE="$base" \
  --build-arg BASE_DIGEST="${base#*@}" \
  -t wolf-lutris:local .
```

## Test

```sh
docker build \
  --target test \
  --build-arg BASE_IMAGE="$base" \
  --build-arg BASE_DIGEST="${base#*@}" \
  -t wolf-lutris:test .

bash tests/lint.sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
bash tests/run.sh wolf-lutris:test
bash tests/runtime-image.sh wolf-lutris:local
```

## License

MIT. See [`NOTICE.md`](NOTICE.md) for third-party software information.
