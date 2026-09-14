#!/usr/bin/env bash
# Build the device firmware from a release tag, in a clean checkout.
#
#   build-firmware.sh [options] <tag> [<dest>]
#
# <dest> is the directory a server offers images from, local or host:path.
# The image goes there as <tag>.bin and replaces the one before it.
#
#   --signed-by <fingerprint>  refuse a tag this key did not sign
#   --key-url <url>            where to fetch the key (default: the owner's
#                              keys on GitHub)
#   --defaults <file>          build with this defaults.cpp, not the example
#   --upload                   also flash the build over USB
#
# The build is of a fresh clone, never the working tree, so its version is
# exactly the tag: epd offers an update only to a board on a tagged build.
set -euo pipefail

repo_url=${REPO_URL:-https://github.com/chrisjtwomey/inkplate5-env-monitor.git}
epd_url=${EPD_URL:-https://github.com/chrisjtwomey/epd.git}
key_url=https://github.com/chrisjtwomey.gpg
signed_by=
defaults=
upload=

usage() {
    awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0" >&2
    exit "$1"
}

while [ $# -gt 0 ]; do
    case $1 in
        --signed-by) signed_by=$(printf '%s' "${2:?}" | tr -d ' ' | tr a-f A-F); shift 2 ;;
        --key-url)   key_url=${2:?}; shift 2 ;;
        --defaults)  defaults=${2:?}; shift 2 ;;
        --upload)    upload=1; shift ;;
        -h|--help)   usage 0 ;;
        -*)          echo "unknown option: $1" >&2; usage 2 ;;
        *)           break ;;
    esac
done
[ $# -eq 1 ] || [ $# -eq 2 ] || usage 2
tag=$1
dest=${2:-}
[ -n "$dest" ] || [ -n "$upload" ] || { echo "nothing to do: give a <dest>, --upload, or both" >&2; exit 2; }
[ -z "$defaults" ] || [ -f "$defaults" ] || { echo "no such file: $defaults" >&2; exit 2; }

work=$(mktemp -d)
cleanup() {
    GNUPGHOME=$work/gnupg gpgconf --kill gpg-agent 2>/dev/null || true
    rm -rf "$work"
}
trap cleanup EXIT
src=$work/inkplate5-env-monitor

# One tag, shallow. Not `git clone --branch`, which warns that an annotated
# tag is not a commit.
checkout_tag() {  # <url> <tag> <dir>
    git init -q "$3"
    git -C "$3" fetch -q --depth 1 "$1" "refs/tags/$2:refs/tags/$2"
    git -C "$3" -c advice.detachedHead=false checkout -q "$2"
}

checkout_tag "$repo_url" "$tag" "$src"

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

pio run -d "$src" -e esp32 | tee "$work/build.log"
grep -qx "CLIENT_VERSION: $tag" "$work/build.log" \
    || { echo "built $(grep -m1 '^CLIENT_VERSION:' "$work/build.log"), not $tag" >&2; exit 1; }

[ -z "$upload" ] || pio run -d "$src" -e esp32 -t upload

bin=$src/.pio/build/esp32/firmware.bin
# Copied under another name, then renamed: the server offers any *.bin it
# finds, even one half-written.
case $dest in
    "") ;;
    *:*)
        host=${dest%%:*}
        dir=${dest#*:}
        scp -q "$bin" "$host:$dir/$tag.bin.tmp"
        ssh "$host" "cd '$dir' && mv -f '$tag.bin.tmp' '$tag.bin' && find . -maxdepth 1 -name '*.bin' ! -name '$tag.bin' -delete"
        ;;
    *)
        cp "$bin" "$dest/$tag.bin.tmp"
        mv -f "$dest/$tag.bin.tmp" "$dest/$tag.bin"
        find "$dest" -maxdepth 1 -name '*.bin' ! -name "$tag.bin" -delete
        ;;
esac
echo "$tag: $(wc -c < "$bin" | tr -d ' ') bytes${dest:+, in $dest}${upload:+, flashed over USB}"
