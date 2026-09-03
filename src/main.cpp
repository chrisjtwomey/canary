// Mock-sensor demo: drives the four mocks against the simulated room and
// prints one readings document every 5 s. No display, no network yet — this
// exists so the mocks are proven on the target before the awake loop lands
// (docs/ARCHITECTURE.md §7).
#include <Arduino.h>

#include "sensors/Readings.h"
#include "sensors/mock/EnvModel.h"
#include "sensors/mock/MockBme688.h"
#include "sensors/mock/MockPmsa003i.h"
#include "sensors/mock/MockScd41.h"
#include "sensors/mock/MockShtc3.h"

static const uint32_t kEpochAtBoot = 1756900000;   // 2025-09-03 ~12:26 UTC
static const uint32_t kSampleMs = 5000;

static EnvModel     room(7);
static MockShtc3    shtc3(room);
static MockScd41    scd41(room);
static MockPmsa003i pm(room);
static MockBme688   bme(room);

static uint32_t lastSampleMs = 0;
static char json[640];

void setup() {
    Serial.begin(115200);
    delay(200);
    uint32_t now = millis();
    room.reset(kEpochAtBoot);

    shtc3.begin(now);
    scd41.begin(now);
    delay(MockScd41::kWakeMs);
    scd41.startPeriodicMeasurement(millis());
    pm.begin(now);
    bme.begin(now);
    bme.setOversampling(2, 16, 1);
    bme.setHeaterProfile(300, 100);
    Serial.println("mock sensors up; PM fan warming up for 30 s");
}

void loop() {
    uint32_t now = millis();
    if (now - lastSampleMs < kSampleMs) { delay(10); return; }
    lastSampleMs = now;
    room.advanceTo(kEpochAtBoot + now / 1000);

    Readings r = {};
    r.ts = room.epoch();

    // SHTC3: wake, measure, wait 13 ms, read, sleep.
    shtc3.wakeup(now);
    shtc3.measure(now, false);
    delay(MockShtc3::kNormalMs);
    r.shtc3Valid = shtc3.read(millis(), r.shtc3);
    shtc3.sleep();

    // BME688: one forced cycle; feed its pressure to the SCD41.
    bme.startForced(millis());
    delay(bme.measurementMs());
    r.bme688Valid = bme.fetchData(millis(), r.bme688);
    if (r.bme688Valid) scd41.setAmbientPressure((uint32_t)(r.bme688.pressureHpa * 100.0f));

    // SCD41: take whatever the periodic mode has ready.
    bool ready = false;
    scd41.getDataReadyStatus(millis(), ready);
    r.scd41Valid = ready && scd41.readMeasurement(millis(), r.scd41);

    // PMSA003I: read a frame, retry once on a bad checksum, ignore during warm-up.
    uint8_t frame[32];
    r.pmValid = false;
    if (pm.stable(millis())) {
        for (int attempt = 0; attempt < 2 && !r.pmValid; ++attempt) {
            if (pm.readFrame(millis(), frame)) r.pmValid = IPmsa003i::parseFrame(frame, r.pm);
        }
    }

    if (readingsToJson(r, "inkplate5-env-monitor", json, sizeof(json))) {
        Serial.println(json);
    } else {
        Serial.println("json buffer too small");
    }
}
