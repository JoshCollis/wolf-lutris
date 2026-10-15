# syntax=docker/dockerfile:1.7
ARG BASE_IMAGE=ghcr.io/games-on-whales/base-app:fedora
FROM ${BASE_IMAGE} AS xwayland
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN source /etc/os-release && test "$ID" = fedora && \
    test -n "$SUPPORT_END" && test "$(date -u +%F)" '<' "$SUPPORT_END" && \
    dnf upgrade -y --refresh --setopt=install_weak_deps=False && \
    dnf install -y --setopt=install_weak_deps=False \
      gcc meson ninja-build patch tar xz python3 pkgconf-pkg-config \
      wayland-devel wayland-protocols-devel libepoxy-devel libdrm-devel \
      openssl-devel libtirpc-devel pixman-devel libX11-devel libXau-devel \
      libXdmcp-devel libXext-devel libXfixes-devel libXfont2-devel libXi-devel \
      libXinerama-devel libxkbfile-devel libXmu-devel libXrender-devel libXres-devel \
      libxshmfence-devel xorg-x11-proto-devel xorg-x11-xtrans-devel libXtst-devel \
      libXv-devel libxcvt-devel libdecor-devel liboeffis-devel libei-devel \
      mesa-libGL-devel mesa-libEGL-devel mesa-libgbm-devel audit-libs-devel \
      libselinux-devel libunwind-devel xcb-util-devel xcb-util-image-devel \
      xcb-util-wm-devel xcb-util-keysyms-devel xcb-util-renderutil-devel && dnf clean all
WORKDIR /build
RUN (curl -fSL --retry 3 --retry-all-errors --connect-timeout 30 --max-time 180 \
       https://xorg.freedesktop.org/archive/individual/xserver/xwayland-24.1.14.tar.xz -o source.tar.xz || \
     curl -fSL --retry 3 --retry-all-errors --connect-timeout 30 --max-time 180 \
       https://mirrors.xmission.com/slackware/slackware64-current/source/x/xorg-server-xwayland/xwayland-24.1.14.tar.xz -o source.tar.xz) && \
    echo '4eb6b98d678299a4b96138d886345b294130695760345ef84596225a8224078a  source.tar.xz' | sha256sum -c - && \
    tar -xf source.tar.xz
COPY build/xwayland-rootful-refresh.patch /build/refresh.patch
COPY tests/xwayland-modes.py /build/test-modes.py
RUN patch --fuzz=0 -p1 -d xwayland-24.1.14 < refresh.patch && \
    python3 test-modes.py xwayland-24.1.14/hw/xwayland/xwayland-output.c && \
    meson setup out xwayland-24.1.14 --prefix=/usr --buildtype=release \
      -Ddefault_font_path=catalogue:/etc/X11/fontpath.d,built-ins \
      -Dxkb_dir=/usr/share/X11/xkb -Dxkb_bin_dir=/usr/bin -Dxkb_output_dir=/var/lib/xkb \
      -Dserverconfigdir=/usr/share/xwayland -Dxcsecurity=true -Dglamor=true -Ddri3=true && \
    meson compile -C out -j 2 && meson test -C out --print-errorlogs && \
    mkdir -p /assets/libexec/wolf-lutris /assets/doc/wolf-lutris/xwayland && \
    install -m 0755 out/hw/xwayland/Xwayland /assets/libexec/wolf-lutris/Xwayland && \
    cp source.tar.xz refresh.patch xwayland-24.1.14/COPYING /assets/doc/wolf-lutris/xwayland/ && \
    cp out/meson-logs/testlog.txt /assets/doc/wolf-lutris/xwayland/upstream-tests.txt
COPY build/present-probe.c /build/present-probe.c
# pkg-config intentionally emits separate compiler arguments.
# hadolint ignore=SC2046
RUN gcc -O2 -Wall -Werror present-probe.c -o /assets/libexec/wolf-lutris/present-probe \
      $(pkg-config --cflags --libs xcb xcb-present) && \
    cp present-probe.c /assets/doc/wolf-lutris/xwayland/

FROM ${BASE_IMAGE} AS runtime-deps
ARG BASE_IMAGE
ARG BASE_DIGEST=unrecorded-local-build
ARG IMAGE_SOURCE=""
ARG IMAGE_REVISION=local
LABEL org.opencontainers.image.title="wolf-lutris" \
      org.opencontainers.image.description="Classic Lutris gaming session for Games-on-Whales Wolf" \
      org.opencontainers.image.source=${IMAGE_SOURCE} \
      org.opencontainers.image.revision=${IMAGE_REVISION} \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.base.name=${BASE_IMAGE} \
      org.opencontainers.image.base.digest=${BASE_DIGEST}
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
# Stay within the base's signed distribution repositories; no PPAs/COPRs.
RUN source /etc/os-release && test "$ID" = fedora && \
    test -n "$SUPPORT_END" && test "$(date -u +%F)" '<' "$SUPPORT_END" && \
    dnf upgrade -y --refresh --setopt=install_weak_deps=False && \
    dnf install -y --setopt=install_weak_deps=False \
      lutris openbox wine-core.x86_64 wine-core.i686 \
      wine-pulseaudio.x86_64 wine-pulseaudio.i686 winetricks \
      alsa-plugins-pulseaudio.x86_64 alsa-plugins-pulseaudio.i686 \
      alsa-lib.x86_64 alsa-lib.i686 pulseaudio-libs.x86_64 pulseaudio-libs.i686 \
      mesa-dri-drivers.x86_64 mesa-dri-drivers.i686 \
      mesa-vulkan-drivers.x86_64 mesa-vulkan-drivers.i686 \
      mesa-libGL.x86_64 mesa-libGL.i686 mesa-libEGL.x86_64 mesa-libEGL.i686 \
      vulkan-loader.x86_64 vulkan-loader.i686 \
      libstdc++.x86_64 libstdc++.i686 SDL3.x86_64 SDL3.i686 \
      sdl2-compat.x86_64 sdl2-compat.i686 openal-soft.x86_64 openal-soft.i686 \
      pulseaudio-utils alsa-utils dbus-daemon dbus-tools gnome-keyring \
      xdg-utils xdg-user-dirs xorg-x11-xauth xdpyinfo xrandr xprop xwininfo \
      xdotool python3-pillow util-linux tini cabextract 7zip unzip tar xz \
      procps-ng file glibc-langpack-en && \
    dnf clean all && \
    test "$(rpm --eval "%{lua: print(rpm.vercmp(\"$(rpm -q --qf '%{VERSION}' xorg-x11-server-Xwayland)\", \"24.1.14\"))}")" -le 0 && \
    test -f /usr/lib64/alsa-lib/libasound_module_pcm_pulse.so && \
    test -f /usr/lib/alsa-lib/libasound_module_pcm_pulse.so && \
    chmod 0755 /usr/bin/bwrap && \
    mkdir -p /usr/share/wolf-lutris && \
    cp /etc/os-release /usr/share/wolf-lutris/base-os-release && \
    rpm -qa | sort > /usr/share/wolf-lutris/packages.txt
FROM runtime-deps AS runtime
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
COPY --from=xwayland /assets/libexec/ /usr/local/libexec/
COPY --from=xwayland /assets/doc/ /usr/share/doc/
COPY overlay/ /
COPY LICENSE NOTICE.md /usr/share/doc/wolf-lutris/
RUN dnf install -y --setopt=install_weak_deps=False vulkan-tools pciutils libatomic.x86_64 libatomic.i686 && dnf clean all && \
    rpm -qa | sort > /usr/share/wolf-lutris/packages.txt && \
    chmod 0755 /opt/gow/startup.sh /opt/wolf-lutris/*.py \
      /etc/cont-init.d/05-lutris-runtime.sh /etc/cont-init.d/10-setup_user.sh && \
    /usr/local/libexec/wolf-lutris/Xwayland -version && \
    rm -rf /home/retro/.local && \
    rm -f /etc/cont-init.d/init-gamescope.sh
# The unused GoW gamescope hook changes ownership to UNAME:UNAME; this image
# supports existing numeric groups and never launches through that compositor.
ENV UNAME=lutris UMASK=022 TZ=UTC LANG=en_US.UTF-8
WORKDIR /home/retro

FROM runtime AS test
# Test-only Pulse server replaces PipeWire's Pulse provider in this disposable image.
RUN dnf install -y --allowerasing --setopt=install_weak_deps=False \
      pulseaudio gcc glibc-devel.i686 alsa-lib-devel.x86_64 alsa-lib-devel.i686 \
      libX11-devel.x86_64 libX11-devel.i686 vulkan-tools && dnf clean all
COPY tests/ /opt/wolf-lutris/tests/
