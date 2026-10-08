#!/bin/sh
# Starts canary's server for the first time on this computer: writes
# server/config.yaml from the example, set for a real install, makes
# server/firmware, and starts the stack. It keeps a config that exists, so it
# can run again at any time. The boards' Wi-Fi is set on the install page.

cd "$(dirname "$0")" || exit 1

fail() {
    printf '%s\n' "$*" >&2
    exit 1
}

# The host port that docker-compose.yml maps to container port $1.
host_port() {
    sed -n "s/^ *- \"\{0,1\}\([0-9]*\):$1\"\{0,1\} *\$/\1/p" docker-compose.yml | head -n 1
}

# This computer's time zone, as an IANA name such as Europe/Dublin.
host_zone() {
    zone=$(timedatectl show -p Timezone --value 2>/dev/null)
    [ -n "$zone" ] || zone=$(readlink /etc/localtime 2>/dev/null | sed -n 's|.*zoneinfo/||p')
    printf '%s' "$zone"
}

# This computer's name on the local network, as mDNS answers it. macOS keeps
# that name apart from its host name, which can be just "Mac".
local_name() {
    name=$(scutil --get LocalHostName 2>/dev/null) || name=$(hostname -s)
    printf '%s.local' "$name"
}

docker compose version >/dev/null 2>&1 ||
    fail "Docker Compose not found. Install Docker, then try again."

name=$(local_name)
port=$(host_port 8080)
https_port=$(host_port 8443)

docker compose run --rm -e SETUP_TIMEZONE="$(host_zone)" \
    -e SETUP_SERVER_URL="http://$name:${port:-8080}" setup || exit 1
docker compose up -d || exit 1

printf '\n%s\n' "Canary is running."
printf '%s\n' "Install the boards: https://$name:${https_port:-8443}/web/install"
printf '%s\n' "Your browser warns about the certificate first. Select Advanced, then continue."
printf '%s\n' "The first firmware build takes some minutes. To follow it: docker compose logs -f firmware-builder"
