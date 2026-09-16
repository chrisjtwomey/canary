#!/usr/bin/env bash
# Build each new release's firmware into the directory the server offers
# images from. Releases only: a build of main would be offered to the board,
# and the board would take a development build.
set -uo pipefail

repo=${REPO:-chrisjtwomey/inkplate5-env-monitor}
dir=${FIRMWARE_DIR:-/firmware}
poll=${POLL_SECONDS:-900}

log() { echo "$(date -u +%FT%TZ) $*"; }

if [ ! -w "$dir" ]; then
    log "$dir is not writable by uid $(id -u); chown the host directory to it"
    exit 1
fi

failed=
while :; do
    tag=$(curl -fsS -H 'Accept: application/vnd.github+json' \
            "https://api.github.com/repos/$repo/releases/latest" \
          | python3 -c 'import json, sys; print(json.load(sys.stdin)["tag_name"])') || tag=
    if [ -z "$tag" ]; then
        log "could not read the latest release of $repo"
    elif [ ! -e "$dir/$tag.bin" ] && [ "$tag" != "$failed" ]; then
        log "building $tag"
        if build-firmware ${SIGNED_BY:+--signed-by "$SIGNED_BY"} "$tag" "$dir"; then
            failed=
        else
            # A build that fails once would fail at every poll.
            log "$tag failed; restart the container to try it again"
            failed=$tag
        fi
    fi
    sleep "$poll"
done
