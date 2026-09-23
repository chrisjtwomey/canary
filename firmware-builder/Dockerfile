# Builds the head's and the dock's firmware of the commit this image was
# built from, into the directory the server offers images from. See
# CONTRIBUTING.md, Releases, and the firmware-builder service in
# docker-compose.yml.
FROM python:3.13-slim-bookworm

RUN apt-get update && apt-get install --no-install-recommends -y \
        ca-certificates git tini \
    && rm -rf /var/lib/apt/lists/*

# Pinned, so a rebuild of this image builds the firmware the same way.
RUN pip install --no-cache-dir platformio==6.2.0

# The toolchain and Bosch's BSEC library download on the first build, and a
# volume at /platformio keeps the toolchain. Open to every uid, because
# compose chooses the uid.
ENV PLATFORMIO_CORE_DIR=/platformio \
    HOME=/tmp
RUN mkdir -m 1777 /platformio

# The version the images are named by, stamped as the server image stamps
# its own; scripts/version.py reads it, since the image has no repository.
ARG CANARY_VERSION=dev
ENV CANARY_VERSION=${CANARY_VERSION}

# The firmware sources at this commit, with the example settings, and epd's
# at the tag the server pins, where platformio.ini's ../epd finds it.
COPY platformio.ini partitions.csv /src/canary/
COPY include /src/canary/include
COPY lib /src/canary/lib
COPY src /src/canary/src
COPY scripts/version.py scripts/bsec.py /src/canary/scripts/
COPY server/requirements.txt /src/canary/server/requirements.txt
RUN cp /src/canary/src/defaults.example.cpp /src/canary/src/defaults.cpp \
    && ref=$(sed -n 's|.*/epd\.git@\([^#]*\)#subdirectory=server.*|\1|p' /src/canary/server/requirements.txt) \
    && git -c advice.detachedHead=false clone -q --depth 1 --branch "$ref" https://github.com/chrisjtwomey/epd.git /src/epd \
    && rm -rf /src/epd/.git

COPY --chmod=755 firmware-builder/build.sh /usr/local/bin/build-firmware
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["build-firmware"]
