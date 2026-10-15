# Notices

The wolf-lutris integration scripts, tests and build recipes are MIT-licensed; see LICENSE. They adapt MIT integration work from Josh Collis's wolf-plasma, wolf-steam and wolf-jellyfin projects. Distribution packages retain their own licenses: the image as a whole is not exclusively MIT.

The official Games-on-Whales base-app is MIT-licensed integration code with separately licensed distribution software. Its entrypoint, device-group and NVIDIA-injection hooks are retained. Upstream: https://github.com/games-on-whales/gow .

Lutris is GPL-3.0-or-later software, distributed unmodified through signed Fedora RPMs. License and source references: https://github.com/lutris/lutris and https://src.fedoraproject.org/rpms/lutris . Wine, Mesa, ALSA, PulseAudio, Openbox and the remaining Fedora packages retain the licenses recorded in RPM metadata and /usr/share/licenses. The package manifest is /usr/share/wolf-lutris/packages.txt. Fedora corresponding source packages can be obtained from https://src.fedoraproject.org/ and the Fedora source repositories for the exact manifest versions; retain distribution source/license obligations when redistributing.

The private Xwayland build is upstream 24.1.14 with the rootful mode-rate patch adapted from wolf-plasma. Its verified upstream source archive, exact applied patch, upstream COPYING (MIT/X11 and the component notices it enumerates), Present probe source and upstream test log are included under /usr/share/doc/wolf-lutris/xwayland. Rootless scheduling and Wayland frame callbacks are not patched. Upstream source: https://xorg.freedesktop.org/archive/individual/xserver/xwayland-24.1.14.tar.xz .

No proprietary games, songs, BASS library, account credentials or gamepad frontend binaries are included. Clone Hero is used only as an optional separately obtained local acceptance fixture, not redistributed in this image.
