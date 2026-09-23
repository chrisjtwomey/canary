#pragma once
#include <cstddef>
#include <cstdint>

// What the dock knows about how its sensors are faring, as opposed to what
// they measure: posted as the "health" object beside the readings.
//
// A loose or noisy wire shows as damaged answers long before a sensor stops,
// so the checksum failures are counted rather than only dropped. Counts run
// from the dock's start.
struct SensorHealth {
    uint32_t restarts;            // sensors the suite had to start again
    uint32_t pmBadFrames;         // PMSA003I frames with a bad start, length or checksum
    uint32_t shtc3CrcFailures;
    uint32_t scd41CrcFailures;

    bool bme688Seen;              // the last sample had a BME688 reading
    bool gasValid;                // it carried a real gas conversion
    bool heatStable;              // its heater reached its target

    uint16_t bme688HeaterC;       // heater target, degrees C
    uint16_t bme688HeaterMs;      // time at the target before each gas conversion

    bool     scd41Read;           // the SCD41's identity was read at its start
    uint64_t scd41Serial;
    bool     ascKnown, asc;       // automatic self-calibration
    bool     offsetKnown;
    float    offsetC;             // temperature offset, degrees C
    bool     pressureKnown;
    uint32_t pressurePa;          // the ambient pressure last handed to the SCD41

    bool     pmSeen;              // a PMSA003I frame has been read
    uint8_t  pmVersion;           // the frame's version byte
    uint8_t  pmError;             // the frame's error code

    bool     shtc3IdKnown;        // the SHTC3's ID register was read at its start
    uint16_t shtc3Id;
    bool     shtc3LowPower;       // it measures in its low-power mode
};

// Encodes the "health" object. Returns the length written, or 0 if the
// buffer is too small (nothing partial is left behind).
size_t healthJson(const SensorHealth& h, char* buf, size_t len);
