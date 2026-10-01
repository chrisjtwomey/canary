"""Corrections applied to the readings before any page sees them."""
from __future__ import annotations

from typing import Mapping

from epd_server.source import DataSource, Fetcher

from metrics import sea_level_hpa

# Bosch rates the index at its best only at accuracy 3 (BME688 datasheet,
# Table 3). Below it, the index moves with BSEC's calibration as much as with
# the air.
IAQ_MIN_ACCURACY = 3


def to_sea_level(doc: dict, altitude_m: float) -> dict:
    """``doc`` with ``pressure_hpa`` reduced to sea level and the measured value
    kept as ``pressure_station_hpa``. At altitude 0, ``doc`` itself.

    Forecasts and weather reports quote sea-level pressure; the sensor reads
    the pressure where it sits, about 1 hPa lower for every 8 m of height.
    """
    hpa = doc.get("pressure_hpa")
    if hpa is None or not altitude_m:
        return doc
    return dict(doc, pressure_hpa=round(sea_level_hpa(hpa, altitude_m), 1), pressure_station_hpa=hpa)


def without_uncalibrated_iaq(doc: dict) -> dict:
    """``doc`` without ``iaq`` while its accuracy is below IAQ_MIN_ACCURACY.
    ``iaq_accuracy`` stays, so a page can say that the index is calibrating."""
    if doc.get("iaq") is None or (doc.get("iaq_accuracy") or 0) >= IAQ_MIN_ACCURACY:
        return doc
    return {k: v for k, v in doc.items() if k != "iaq"}


def correct(doc: dict, altitude_m: float) -> dict:
    """``doc`` as the pages see it: the pressure at sea level, and the index
    only at high accuracy."""
    return without_uncalibrated_iaq(to_sea_level(doc, altitude_m))


class CorrectedSource(DataSource):
    """Wraps a source so each reading has the corrections of ``correct``.
    The store keeps each reading as the board posted it."""

    def __init__(self, inner: DataSource, altitude_m: float, keys=("latest", "history_24h", "history_72h")):
        self.inner = inner
        self.altitude_m = altitude_m
        self.keys = keys

    def correct(self, doc: dict) -> dict:
        return correct(doc, self.altitude_m)

    def datasets(self) -> Mapping[str, Fetcher]:
        inner = dict(self.inner.datasets())
        for key in self.keys:
            if key in inner:
                inner[key] = self._wrap(inner[key])
        return inner

    def _wrap(self, fetch: Fetcher) -> Fetcher:
        def corrected():
            data = fetch()
            if data is None:
                return None
            if isinstance(data, list):
                return [self.correct(d) for d in data]
            return self.correct(data)
        return corrected

    def invalidate(self) -> None:
        self.inner.invalidate()
