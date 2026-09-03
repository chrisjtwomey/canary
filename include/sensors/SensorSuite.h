#pragma once
#include <cstdint>

#include "sensors/IBme688.h"
#include "sensors/IClock.h"
#include "sensors/IPmsa003i.h"
#include "sensors/IScd41.h"
#include "sensors/IShtc3.h"
#include "sensors/Readings.h"

// The four sensors as one thing to start and one thing to sample.
//
// It holds interfaces, so the same code drives the mocks and the real
// drivers; the choice is made once, where the suite is constructed. The
// sequence it runs — wake, measure, wait the datasheet time, read, sleep —
// is the same either way, which is the point: the mocks exercise the code
// that will run on the device, not a parallel copy of it.
//
// A sample takes roughly 150 ms of wall clock, nearly all of it the BME688
// heater. At the intended 5 s cadence that is 3% of the time, and ::delay()
// yields on ESP32, so WiFi keeps running.
class SensorSuite {
public:
    SensorSuite(IClock& clock, IShtc3& shtc3, IScd41& scd41, IPmsa003i& pm, IBme688& bme)
        : clock_(clock), shtc3_(shtc3), scd41_(scd41), pm_(pm), bme_(bme) {}

    // Start every sensor and leave the SCD41 measuring. True when all four
    // came up; the per-sensor flags say which did.
    bool begin();

    bool shtc3Present()  const { return shtc3Ok_; }
    bool scd41Present()  const { return scd41Ok_; }
    bool pmPresent()     const { return pmOk_; }
    bool bme688Present() const { return bmeOk_; }

    // One reading set, stamped with `epoch`. Sensors that fail or are not
    // ready leave their `*Valid` flag false rather than filling in stale or
    // invented numbers.
    Readings sample(uint32_t epoch);

    // The PM fan. Low stops it and, on the Adafruit board, its 5 V charge
    // pump; readings are untrustworthy for 30 s after it restarts, which
    // sample() honours through IPmsa003i::stable().
    void setFanEnabled(bool on);

    // SCD41 power-up to idle, datasheet 30 ms max.
    static const uint32_t kScd41WakeMs = 30;
    // SHTC3 normal-mode conversion, datasheet 12.1 ms max.
    static const uint32_t kShtc3MeasureMs = 13;
    // BME688 forced-mode profile: 300 C for 100 ms is Bosch's indoor VOC
    // example, and the plate needs 20-30 ms of that to reach temperature.
    static const uint16_t kBmeHeaterC = 300;
    static const uint16_t kBmeHeaterMs = 100;
    // Oversampling: 2x temperature, 16x pressure, 1x humidity (datasheet 3.5).
    static const uint8_t kBmeOsT = 2, kBmeOsP = 16, kBmeOsH = 1;
    // A PM frame read can land on a bus glitch; one retry covers it.
    static const int kPmReadAttempts = 2;

private:
    void sampleShtc3(Readings& r);
    void sampleBme688(Readings& r);
    void sampleScd41(Readings& r);
    void samplePm(Readings& r);

    IClock&    clock_;
    IShtc3&    shtc3_;
    IScd41&    scd41_;
    IPmsa003i& pm_;
    IBme688&   bme_;

    bool shtc3Ok_ = false;
    bool scd41Ok_ = false;
    bool pmOk_ = false;
    bool bmeOk_ = false;
};
