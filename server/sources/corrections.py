"""Corrections applied to the readings before any page sees them."""
from __future__ import annotations

from typing import Mapping

from epd_server.source import DataSource, Fetcher

from metrics import sea_level_hpa


def to_sea_level(doc: dict, altitude_m: float) -> dict:
    """``doc`` with ``pressure_hpa`` reduced to sea level and the measured value
    kept as ``pressure_station_hpa``. At altitude 0, ``doc`` itself."""
    hpa = doc.get("pressure_hpa")
    if hpa is None or not altitude_m:
        return doc
    return dict(doc, pressure_hpa=round(sea_level_hpa(hpa, altitude_m), 1), pressure_station_hpa=hpa)


class SeaLevelSource(DataSource):
    """Wraps a source so ``pressure_hpa`` is reduced to sea level.

    Forecasts and weather reports quote sea-level pressure; the sensor reads
    the pressure where it sits, about 1 hPa lower for every 8 m of height.
    The reading as measured stays under ``pressure_station_hpa``.
    """

    def __init__(self, inner: DataSource, altitude_m: float, keys=("latest", "history_24h", "history_72h")):
        self.inner = inner
        self.altitude_m = altitude_m
        self.keys = keys

    def correct(self, doc: dict) -> dict:
        return to_sea_level(doc, self.altitude_m)

    def datasets(self) -> Mapping[str, Fetcher]:
        inner = dict(self.inner.datasets())
        if not self.altitude_m:
            return inner
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
