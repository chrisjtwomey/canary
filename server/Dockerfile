FROM python:3.13-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    CHROME_BIN=/usr/bin/chromium

# git: requirements.txt takes epd-server from GitHub.
RUN apt-get update && apt-get install --no-install-recommends -y \
        git \
        chromium \
        chromium-driver \
        fonts-dejavu-core \
        tini \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/sh app
WORKDIR /app

COPY requirements.txt ./
RUN pip install --upgrade pip setuptools wheel && pip install -r requirements.txt

COPY . /app
# The example config makes the image runnable as it is; mount a real
# /app/config.yaml to replace it. /app/data is for the readings and
# calibration stores (point source.path and calibration.path there) and
# /app/firmware for OTA images: mount a volume on each to keep them.
RUN mkdir -p /app/data /app/firmware \
    && cp config.example.yaml config.yaml \
    && chown -R app:app /app

USER app
EXPOSE 8080

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "server.py"]
