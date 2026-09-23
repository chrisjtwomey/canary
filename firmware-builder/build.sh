#!/usr/bin/env bash
# Build the head's and the dock's firmware of the commit this image was built
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

build() {  # <product> <environment>
    local product=$1 env=$2
    local out=$dir/$product/$version.bin
    if [ -e "$out" ]; then
        log "$product $version is already built"
        return
    fi
    log "building $product $version"
    if ! pio run -d "$work/canary" -e "$env" > "$work/$env.log" 2>&1; then
        tail -n 20 "$work/$env.log"
        log "$product $version failed; restart the container to try again"
        return
    fi
    if ! grep -qx "CLIENT_VERSION: $version" "$work/$env.log"; then
        log "$env built $(grep -m1 '^CLIENT_VERSION:' "$work/$env.log"), not $version"
        return
    fi
    mkdir -p "$dir/$product"
    # Copied under another name, then renamed: the server offers any *.bin it
    # finds, even one half-written.
    cp "$work/canary/.pio/build/$env/firmware.bin" "$out.tmp"
    mv -f "$out.tmp" "$out"
    log "$product $version: $(wc -c < "$out" | tr -d ' ') bytes"
}

build canary-head esp32
build canary-dock dock
idle
