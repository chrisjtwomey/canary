"""A mock readings source: the firmware's simulated room, in Python.

The same dynamics as ``src/sensors/mock/EnvModel.cpp`` (same constants,
same schedule), so pages developed against this see the shapes the device
will send. It produces documents in the layout of docs/READINGS.md.

    source = MockReadingsSource(seed=7)
    source.datasets()["latest"]()          # one document, now
    source.datasets()["history_24h"]()     # one document per minute, oldest first
"""
from __future__ import annotations

import math
import time
from typing import Callable, Mapping

from epd_server.source import DataSource, Fetcher

CO2_OUTDOOR = 420.0
CO2_PER_PERSON_PER_S = 4.0 / 60.0
ABS_HUM_OUTDOOR = 7.5
ABS_HUM_PER_PERSON_PER_S = 0.0003
TEMP_TAU_S = 2400.0
PM_BASELINE = 4.0
PM_TAU_S = 2700.0
VOC_BASELINE = 0.12
VOC_TAU_S = 3600.0
VOC_PER_PERSON_PER_S = 0.00002


def _between(h, lo, hi):
    return lo <= h < hi


def _occupancy(h):
    if _between(h, 7.0, 8.5):
        return 1
    if _between(h, 17.5, 23.0):
        return 2
    if _between(h, 23.0, 24.0):
        return 1
    return 0


def _heating_target(h):
    if _between(h, 6.5, 8.5):
        return 21.0
    if _between(h, 17.0, 23.0):
        return 21.5
    return 18.5


def _ventilation_tau(h):
    return 900.0 if (_between(h, 8.0, 8.5) or _between(h, 21.0, 21.25)) else 7200.0


def _pm_source(h):
    if _between(h, 18.0, 18.4):
        return 0.08
    if _between(h, 7.5, 7.65):
        return 0.03
    return 0.0


def _voc_source(h):
    if _between(h, 18.0, 18.5) or _between(h, 10.0, 10.33):
        return 0.0004
    return 0.0


def rh_from_abs(abs_hum: float, temp_c: float) -> float:
    es = 6.112 * math.exp(17.62 * temp_c / (243.12 + temp_c))
    return max(0.0, min(100.0, 100.0 * abs_hum * (temp_c + 273.15) / (216.7 * es)))


class EnvModel:
    """The room. See the C++ header for the dynamics."""

    def __init__(self, seed: int = 1):
        self._rng = seed if seed else 0x9E3779B9
        self.epoch = 0
        self.occupancy = 0
        self.temp = 20.0
        self.abs_hum = 7.5
        self.co2 = 450.0
        self.pm25 = 4.0
        self.voc = 0.15

    # xorshift32, so a seed gives the same sequence as the firmware mock
    def _rnd(self) -> int:
        x = self._rng
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFFFFFF
        self._rng = x & 0xFFFFFFFF
        return self._rng

    def uniform(self) -> float:
        return (self._rnd() >> 8) / 16777216.0

    def noise(self, sigma: float) -> float:
        return (self.uniform() + self.uniform() + self.uniform() - 1.5) * 2.0 * sigma

    @property
    def hour(self) -> float:
        return (self.epoch % 86400) / 3600.0

    @property
    def rh(self) -> float:
        return rh_from_abs(self.abs_hum, self.temp)

    @property
    def pressure_hpa(self) -> float:
        t = self.epoch % (3 * 86400)
        return 1013.0 + 8.0 * math.sin(2 * math.pi * t / (3 * 86400))

    @property
    def gas_ohm(self) -> float:
        pull = max(-0.5, min(1.0, (self.rh - 40.0) / 50.0))
        return 200000.0 * math.exp(-2.4 * self.voc) * (1.0 - 0.5 * pull)

    @property
    def pm1(self) -> float:
        return self.pm25 * 0.62

    @property
    def pm10(self) -> float:
        return self.pm25 * 1.35

    def reset(self, epoch_s: int) -> None:
        self.epoch = int(epoch_s)
        h = self.hour
        self.occupancy = _occupancy(h)
        self.temp = _heating_target(h)
        self.abs_hum = ABS_HUM_OUTDOOR + 0.8 * self.occupancy
        self.co2 = CO2_OUTDOOR + 80.0 + 150.0 * self.occupancy
        self.pm25 = PM_BASELINE
        self.voc = VOC_BASELINE + 0.05 * self.occupancy

    def advance_to(self, epoch_s: int) -> None:
        epoch_s = int(epoch_s)
        if epoch_s <= self.epoch:
            self.epoch = epoch_s
            return
        while self.epoch < epoch_s:
            dt = min(60, epoch_s - self.epoch)
            self._step(float(dt))
            self.epoch += dt

    def _step(self, dt: float) -> None:
        h = self.hour
        self.occupancy = _occupancy(h)
        tau = _ventilation_tau(h)
        self.co2 += dt * (CO2_PER_PERSON_PER_S * self.occupancy - (self.co2 - CO2_OUTDOOR) / tau)
        self.abs_hum += dt * (ABS_HUM_PER_PERSON_PER_S * self.occupancy - (self.abs_hum - ABS_HUM_OUTDOOR) / tau)
        target = _heating_target(h) + 0.3 * self.occupancy
        self.temp += dt * (target - self.temp) / TEMP_TAU_S
        self.pm25 = max(0.0, self.pm25 + dt * (_pm_source(h) - (self.pm25 - PM_BASELINE) / PM_TAU_S))
        self.voc = min(1.0, self.voc + dt * (_voc_source(h) + VOC_PER_PERSON_PER_S * self.occupancy
                                              - (self.voc - VOC_BASELINE) / VOC_TAU_S))


def _iaq_from_gas(gas_ohm: float) -> float:
    lg = math.log10(max(1000.0, gas_ohm))
    return max(0.0, min(500.0, 25.0 + (5.176 - lg) * 275.0))


def reading_from(room: EnvModel, device: str = "inkplate5-env-monitor") -> dict:
    """One docs/READINGS.md document from the room's current state, with the
    per-sensor quirks the firmware mocks add: SCD41 T runs +4 C less its
    default offset (net zero), BME688 T runs +1.5 C, repeatability noise."""
    t = room.temp
    rh = room.rh
    scd_t = t + room.noise(0.1)
    bme_t = t + 1.5 + room.noise(0.05)
    gas = room.gas_ohm * (1.0 + room.noise(0.02))
    pm25 = room.pm25
    return {
        "ts": room.epoch,
        "device": device,
        "temp_c": round(t + room.noise(0.1), 1),
        "rh_pct": round(rh + room.noise(0.1), 1),
        "co2_ppm": int(round(max(0.0, room.co2 + room.noise(10.0)))),
        "pm1_0": int(round(room.pm1)),
        "pm2_5": int(round(pm25)),
        "pm10": int(round(room.pm10)),
        "pc_0_3": int(round(pm25 * 150)), "pc_0_5": int(round(pm25 * 45)), "pc_1_0": int(round(pm25 * 8)),
        "pc_2_5": int(round(pm25 * 0.6)), "pc_5_0": int(round(pm25 * 0.15)), "pc_10": int(round(pm25 * 0.05)),
        "gas_ohm": int(round(gas)),
        "iaq": int(round(_iaq_from_gas(gas))),
        "iaq_accuracy": 3,
        "pressure_hpa": round(room.pressure_hpa + room.noise(0.02), 1),
        "scd41": {"temp_c": round(scd_t, 1),
                  "rh_pct": round(rh_from_abs(room.abs_hum, scd_t) + room.noise(0.4), 1)},
        "bme688": {"temp_c": round(bme_t, 1),
                   "rh_pct": round(rh_from_abs(room.abs_hum, bme_t) + room.noise(0.2), 1)},
        # The simulated room is always settled, so every measurement is
        # trustworthy here. The firmware drops keys it does not trust; see
        # docs/READINGS.md.
        "valid": {"temp_humidity": True, "co2": True, "particulates": True,
                  "pressure": True, "gas": True},
    }


class MockReadingsSource(DataSource):
    """Datasets: ``latest`` (one document) and ``history_24h`` (one per
    minute, oldest first). Deterministic for a seed and a clock."""

    def __init__(self, seed: int = 7, now: Callable[[], float] = time.time,
                 device: str = "inkplate5-env-monitor"):
        self.seed = seed
        self.now = now
        self.device = device

    def _room_at(self, start: int, end: int) -> tuple[EnvModel, list[dict]]:
        room = EnvModel(self.seed)
        room.reset(start)
        docs = []
        t = start
        while t <= end:
            room.advance_to(t)
            docs.append(reading_from(room, self.device))
            t += 60
        return room, docs

    def latest(self) -> dict:
        end = int(self.now())
        room, _ = self._room_at(end - 3 * 3600, end)   # three hours of run-up so state is settled
        room.advance_to(end)
        return reading_from(room, self.device)

    def history(self, hours: int = 24) -> list[dict]:
        end = int(self.now()) // 60 * 60
        _, docs = self._room_at(end - hours * 3600, end)
        return docs

    def datasets(self) -> Mapping[str, Fetcher]:
        return {
            "latest": self.latest,
            "history_24h": lambda: self.history(24),
            "history_72h": lambda: self.history(72),
        }
