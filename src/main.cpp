// Reads the four sensors and prints one readings document every 5 s.
//
// Everything below the sensor-selection block runs unchanged against the
// mocks and against real drivers: it talks to SensorSuite, which talks to
// the IShtc3 / IScd41 / IPmsa003i / IBme688 interfaces. Swapping in real
// hardware means writing those four drivers and clearing USE_MOCK_SENSORS.
//
// Still to come (docs/ARCHITECTURE.md §7): the epd libraries, so the epoch
// comes from the Inkplate's RTC, readings are POSTed to the server, and the
// rendered PNG is fetched and drawn.
#include <Arduino.h>

#include "sensors/IClock.h"
#include "sensors/Readings.h"
#include "sensors/SensorSuite.h"

// ─── The only part that knows which implementation is in use ──────────────

#if defined(USE_MOCK_SENSORS)
#include "sensors/mock/EnvModel.h"
#include "sensors/mock/MockBme688.h"
#include "sensors/mock/MockPmsa003i.h"
#include "sensors/mock/MockScd41.h"
#include "sensors/mock/MockShtc3.h"

static EnvModel     room(7);
static MockShtc3    shtc3Impl(room);
static MockScd41    scd41Impl(room);
static MockPmsa003i pmImpl(room);
static MockBme688   bmeImpl(room);

// The simulated room only moves when it is told to.
static void advanceSimulation(uint32_t epoch) { room.advanceTo(epoch); }
static const char* kBanner = "mock sensors up; PM fan warming up for 30 s";

#else
#error "No real sensor drivers yet. Build with -DUSE_MOCK_SENSORS, or add \
Shtc3Driver / Scd41Driver / Pmsa003iDriver / Bme688Driver implementing the \
IShtc3 / IScd41 / IPmsa003i / IBme688 interfaces and wire them up here."
#endif

// ─── Everything below is implementation-agnostic ──────────────────────────

static const uint32_t kEpochAtBoot = 1756900000;   // stands in for the RTC
static const uint32_t kSampleIntervalMs = 5000;

static ArduinoClock wallClock;
static SensorSuite  sensors(wallClock, shtc3Impl, scd41Impl, pmImpl, bmeImpl);

static uint32_t lastSampleMs = 0;
static char json[640];

static uint32_t epochNow() { return kEpochAtBoot + millis() / 1000; }

void setup() {
    Serial.begin(115200);
    delay(200);

    advanceSimulation(epochNow());
    if (!sensors.begin()) {
        Serial.printf("sensor start incomplete: shtc3=%d scd41=%d pm=%d bme688=%d\n",
                      sensors.shtc3Present(), sensors.scd41Present(),
                      sensors.pmPresent(), sensors.bme688Present());
    }
    Serial.println(kBanner);
}

void loop() {
    if (millis() - lastSampleMs < kSampleIntervalMs) {
        delay(10);
        return;
    }
    lastSampleMs = millis();

    uint32_t epoch = epochNow();
    advanceSimulation(epoch);
    Readings r = sensors.sample(epoch);

    if (readingsToJson(r, "inkplate5-env-monitor", json, sizeof(json))) {
        Serial.println(json);
    } else {
        Serial.println("json buffer too small");
    }
}
