# Builds the display's and the dock's firmware of the commit this image was
# built from, into the directory the server offers images from. See
# docs/releases.md, and the firmware-builder service in
# docker-compose.yml.
FROM python:3.13-slim-bookworm

# git: the dock's IDF build fetches a component from a git source.
RUN apt-get update && apt-get install --no-install-recommends -y \
        ca-certificates git tini \
    && rm -rf /var/lib/apt/lists/*

# Pinned, so a rebuild of this image builds the firmware the same way.
RUN pip install --no-cache-dir platformio==6.2.0

# The toolchain and Bosch's BSEC library download on the first build, and a
# volume at /platformio keeps the toolchain; the dock's is in /platformio/dock
# (build.sh). Open to every uid, because compose chooses the uid.
ENV PLATFORMIO_CORE_DIR=/platformio \
    HOME=/tmp
RUN mkdir -m 1777 /platformio

# The version the images are named by, stamped as the server image stamps
# its own; scripts/version.py reads it, since the image has no repository.
ARG CANARY_VERSION=dev
ENV CANARY_VERSION=${CANARY_VERSION}

# The firmware sources at this commit, with the example settings. The build
# downloads epd from the PlatformIO registry, at the version platformio.ini
# pins.
COPY platformio.ini partitions.csv /src/canary/
COPY include /src/canary/include
COPY lib /src/canary/lib
COPY src /src/canary/src
COPY scripts/version.py scripts/bsec.py scripts/dock_core.py /src/canary/scripts/
RUN cp /src/canary/src/defaults.example.cpp /src/canary/src/defaults.cpp

COPY --chmod=755 firmware-builder/build.sh /usr/local/bin/build-firmware
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["build-firmware"]
