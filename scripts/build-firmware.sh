#!/usr/bin/env bash
# Build the device firmware from a release tag, in a clean checkout.
#
#   build-firmware.sh [options] <tag> [<dest>]
#   build-firmware.sh --dev [options] [<dest>]
#
# <dest> is the directory a server offers images from, local or host:path.
# Each board's image goes there as <product>/<version>.bin, beside the images
# already there: a server offers the one its own version calls for, which
# may be an older one.
#
#   --dev                      build this checkout's last commit instead of a
#                              tag; its version is what git describe says,
#                              such as v0.3.1-2-gab12cd4, and a server with
#                              offer_dev_builds offers it over the air
#   --signed-by <fingerprint>  refuse a tag this key did not sign
#   --key-url <url>            where to fetch the key (default: the owner's
#                              keys on GitHub)
#   --defaults <file>          build with this defaults.cpp, not the example
#   --upload <head|dock>       also flash that board's build over USB
#
# The build is of a fresh clone, never the working tree, so its version is
# exactly the tag, or the commit: uncommitted changes are never in it.
set -euo pipefail

repo_url=${REPO_URL:-https://github.com/chrisjtwomey/canary.git}
epd_url=${EPD_URL:-https://github.com/chrisjtwomey/epd.git}
key_url=https://github.com/chrisjtwomey.gpg
signed_by=
defaults=
upload=
dev=

usage() {
    awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0" >&2
    exit "$1"
}

while [ $# -gt 0 ]; do
    case $1 in
        --signed-by) signed_by=$(printf '%s' "${2:?}" | tr -d ' ' | tr a-f A-F); shift 2 ;;
        --key-url)   key_url=${2:?}; shift 2 ;;
        --defaults)  defaults=${2:?}; shift 2 ;;
        --dev)       dev=1; shift ;;
        --upload)    upload=${2:?}; shift 2
                     case $upload in head|dock) ;; *) echo "--upload takes head or dock" >&2; exit 2 ;; esac ;;
        -h|--help)   usage 0 ;;
        -*)          echo "unknown option: $1" >&2; usage 2 ;;
        *)           break ;;
    esac
done
if [ -n "$dev" ]; then
    [ $# -le 1 ] || usage 2
    [ -z "$signed_by" ] || { echo "--signed-by checks a tag; --dev builds a commit" >&2; exit 2; }
    tag=
    dest=${1:-}
else
    [ $# -eq 1 ] || [ $# -eq 2 ] || usage 2
    tag=$1
    dest=${2:-}
fi
[ -n "$dest" ] || [ -n "$upload" ] || { echo "nothing to do: give a <dest>, --upload, or both" >&2; exit 2; }
[ -z "$defaults" ] || [ -f "$defaults" ] || { echo "no such file: $defaults" >&2; exit 2; }

work=$(mktemp -d)
cleanup() {
    GNUPGHOME=$work/gnupg gpgconf --kill gpg-agent 2>/dev/null || true
    rm -rf "$work"
}
trap cleanup EXIT
src=$work/canary

# One tag, shallow. Not `git clone --branch`, which warns that an annotated
# tag is not a commit.
checkout_tag() {  # <url> <tag> <dir>
    git init -q "$3"
    git -C "$3" fetch -q --depth 1 "$1" "refs/tags/$2:refs/tags/$2"
    git -C "$3" -c advice.detachedHead=false checkout -q "$2"
}

if [ -n "$dev" ]; then
    here=$(git rev-parse --show-toplevel)
    git clone -q "$here" "$src"
    git -C "$src" -c advice.detachedHead=false checkout -q "$(git -C "$here" rev-parse HEAD)"
    tag=$(git -C "$src" describe --tags --match 'v*' --always)
    [ -z "$(git -C "$here" status --porcelain --untracked-files=no)" ] \
        || echo "note: uncommitted changes are not in $tag" >&2
else
    checkout_tag "$repo_url" "$tag" "$src"
fi

if [ -n "$signed_by" ]; then
    export GNUPGHOME=$work/gnupg
    mkdir -m 700 "$GNUPGHOME"
    curl -fsS "$key_url" | gpg --batch --quiet --import
    # VALIDSIG names the signing key first and its primary key last.
    git -C "$src" verify-tag --raw "$tag" 2>&1 \
        | awk -v fpr="$signed_by" '$2 == "VALIDSIG" && ($3 == fpr || $NF == fpr) { ok = 1 } END { exit !ok }' \
        || { echo "$tag is not signed by $signed_by" >&2; exit 1; }
fi

epd_tag=$(sed -n 's|.*/epd\.git@\([^#]*\)#subdirectory=server.*|\1|p' "$src/server/requirements.txt")
[ -n "$epd_tag" ] || { echo "server/requirements.txt pins no epd-server tag" >&2; exit 1; }
checkout_tag "$epd_url" "$epd_tag" "$work/epd"

cp "${defaults:-$src/src/defaults.example.cpp}" "$src/src/defaults.cpp"

# The PlatformIO environment each product builds in.
env_of() { case $1 in canary-head) echo esp32 ;; canary-dock) echo dock ;; esac; }

for product in canary-head canary-dock; do
    env=$(env_of "$product")
    pio run -d "$src" -e "$env" | tee "$work/$env.log"
    grep -qx "CLIENT_VERSION: $tag" "$work/$env.log" \
        || { echo "$env built $(grep -m1 '^CLIENT_VERSION:' "$work/$env.log"), not $tag" >&2; exit 1; }
done

case $upload in
    head) pio run -d "$src" -e esp32 -t upload ;;
    dock) pio run -d "$src" -e dock -t upload ;;
esac

# Copied under another name, then renamed: the server offers any *.bin it
# finds, even one half-written.
for product in canary-head canary-dock; do
    bin=$src/.pio/build/$(env_of "$product")/firmware.bin
    case $dest in
        "") ;;
        *:*)
            host=${dest%%:*}
            dir=${dest#*:}/$product
            ssh "$host" "mkdir -p '$dir'"
            scp -q "$bin" "$host:$dir/$tag.bin.tmp"
            ssh "$host" "mv -f '$dir/$tag.bin.tmp' '$dir/$tag.bin'"
            ;;
        *)
            mkdir -p "$dest/$product"
            cp "$bin" "$dest/$product/$tag.bin.tmp"
            mv -f "$dest/$product/$tag.bin.tmp" "$dest/$product/$tag.bin"
            ;;
    esac
    echo "$product $tag: $(wc -c < "$bin" | tr -d ' ') bytes${dest:+, in $dest/$product}"
done
[ -z "$upload" ] || echo "flashed the $upload over USB"
