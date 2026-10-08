#!/usr/bin/env bash
# Build the display's and the dock's firmware of the commit this image was built
# from, into the directory the server offers images from, then wait. The
# server beside it offers each board the newest image that works with its own
# version, so a redeploy moves the server and the boards together.
set -uo pipefail

dir=${FIRMWARE_DIR:-/firmware}
src=${SOURCE_DIR:-/src}
version=${CANARY_VERSION:-dev}

log() { echo "$(date -u +%FT%TZ) $*"; }

# Nothing more to build until the image changes, and exiting would restart it.
idle() { exec sleep infinity; }

if [ "$version" = dev ]; then
    log "this image was built without CANARY_VERSION, so its firmware has no version to offer"
    idle
fi
if [ ! -w "$dir" ]; then
    log "$dir is not writable by uid $(id -u); chown the host directory to it"
    idle
fi

# PlatformIO writes beside the project, and compose may run this as any uid.
work=$(mktemp -d)
cp -r "$src"/. "$work"/

# Copied under another name, then renamed: the server offers any *.bin it
# finds, even one half-written.
place() {  # <built file> <destination>
    cp "$1" "$2.tmp" && mv -f "$2.tmp" "$2"
}

build() {  # <product> <environment> [<PlatformIO folder>]
    local product=$1 env=$2 core=${3:-$PLATFORMIO_CORE_DIR}
    local out=$dir/$product/$version.bin
    local merged=$dir/$product/$version.merged.bin
    if [ -e "$out" ] && [ -e "$merged" ]; then
        log "$product $version is already built"
        return
    fi
    log "building $product $version"
    # PlatformIO's output goes to the container's log as it builds, and to a
    # file for the version check below. pipefail keeps pio's exit status.
    if ! PLATFORMIO_CORE_DIR=$core pio run -d "$work/canary" -e "$env" 2>&1 | tee "$work/$env.log"; then
        log "$product $version failed; restart the server to try again"
        return
    fi
    if ! grep -qx "CLIENT_VERSION: $version" "$work/$env.log"; then
        log "$env built $(grep -m1 '^CLIENT_VERSION:' "$work/$env.log"), not $version"
        return
    fi
    mkdir -p "$dir/$product"
    if ! place "$work/canary/.pio/build/$env/firmware.factory.bin" "$merged" ||
       ! place "$work/canary/.pio/build/$env/firmware.bin" "$out"; then
        log "$product $version: copy to $dir/$product failed; restart the server to try again"
        return
    fi
    log "$product $version: $(wc -c < "$out" | tr -d ' ') bytes"
}

build canary-display esp32
# The dock compiles its own IDF libraries, which break the display's build in a
# shared folder. A subfolder keeps them in the same volume.
build canary-dock dock "$PLATFORMIO_CORE_DIR/dock"
idle
