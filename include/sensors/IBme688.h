#pragma once
#include <cstdint>
#include "Readings.h"

// Bosch BME688 in forced mode: one T/P/H/gas cycle per trigger.
class IBme688 {
public:
    virtual ~IBme688() {}
    virtual bool begin(uint32_t nowMs) = 0;               // chip ID 0x61, variant 0x01
    virtual void setOversampling(uint8_t osT, uint8_t osP, uint8_t osH) = 0;
    virtual void setHeaterProfile(uint16_t degC, uint16_t ms) = 0;   // typically 300–320 C, 100–150 ms
    virtual bool startForced(uint32_t nowMs) = 0;         // ignored while a cycle runs
    // How long a cycle takes with the current oversampling and heater
    // profile. Bosch's API computes this too (bme68x_get_meas_dur).
    virtual uint32_t measurementMs() const = 0;
    // False until the cycle is complete.
    virtual bool fetchData(uint32_t nowMs, Bme688Data& out) = 0;
    virtual uint8_t chipId() = 0;
};
