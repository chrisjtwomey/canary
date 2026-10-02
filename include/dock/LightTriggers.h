#pragma once
#include <cstdint>

#include "sensors/Readings.h"

// Whether the status light's Poor air quality and Calibrating triggers hold,
// judged from the latest reading, so the rules are tested on the host.

// The limits the server sets for poor air, each in its sensor's settings.
struct AirLimits {
    uint16_t co2Ppm;     // CO2 at or above
    float    pm25UgM3;   // PM2.5 at or above
    uint16_t iaq;        // BSEC's static index at or above, once it is calibrated
};

// The static index's accuracy from which it counts, as on the pages: Bosch
// rates the index at its best only at 3. Below it the sensor is calibrating.
static const uint8_t kCalibratedAccuracy = 3;

inline bool poorAir(const Readings& r, const AirLimits& limit) {
    if (r.scd41Valid && r.scd41.co2Ppm >= limit.co2Ppm) return true;
    if (r.pmValid && r.pm.pm2_5 >= limit.pm25UgM3) return true;
    return r.bme688Valid && r.bme688.hasStaticIaq &&
           r.bme688.staticIaqAccuracy >= kCalibratedAccuracy && r.bme688.staticIaq >= limit.iaq;
}

// `scd41Recalibrating`: a recalibration the server asked for waits for the
// SCD41 to have measured long enough.
inline bool calibrating(const Readings& r, bool scd41Recalibrating) {
    return scd41Recalibrating ||
           (r.bme688Valid && r.bme688.hasStaticIaq &&
            r.bme688.staticIaqAccuracy < kCalibratedAccuracy);
}
