# Builds the device firmware for each new release. See CONTRIBUTING.md,
# Releases, and the firmware-builder service in docker-compose.yml.
FROM python:3.13-slim-bookworm

RUN apt-get update && apt-get install --no-install-recommends -y \
        ca-certificates curl git gnupg tini \
    && rm -rf /var/lib/apt/lists/*

# Pinned, so a rebuild of this image builds the firmware the same way.
RUN pip install --no-cache-dir platformio==6.2.0

# The toolchain downloads on the first build, and a volume at /platformio
# keeps it. Open to every uid, because compose chooses the uid.
ENV PLATFORMIO_CORE_DIR=/platformio \
    HOME=/tmp
RUN mkdir -m 1777 /platformio

COPY --chmod=755 scripts/build-firmware.sh /usr/local/bin/build-firmware
COPY --chmod=755 firmware-builder/watch.sh /usr/local/bin/watch-releases

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["watch-releases"]
