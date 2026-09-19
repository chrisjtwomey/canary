#pragma once
#include <cstdint>
#include "Readings.h"

// Sensirion SCD41, the subset of its command set this device uses.
class IScd41 {
public:
    virtual ~IScd41() {}
    virtual bool begin(uint32_t nowMs) = 0;
    virtual bool startPeriodicMeasurement(uint32_t nowMs) = 0;          // 5 s interval
    virtual bool startLowPowerPeriodicMeasurement(uint32_t nowMs) = 0;  // 30 s interval
    virtual bool stopPeriodicMeasurement(uint32_t nowMs) = 0;           // busy 500 ms
    virtual bool measureSingleShot(uint32_t nowMs) = 0;                 // ready after 5000 ms
    virtual bool getDataReadyStatus(uint32_t nowMs, bool& ready) = 0;
    // NACKs (false) when no data is ready. Reading clears the buffer.
    virtual bool readMeasurement(uint32_t nowMs, Scd41Data& out) = 0;
    virtual bool setAmbientPressure(uint32_t pa) = 0;       // 70 000–120 000; allowed while periodic
    virtual bool setTemperatureOffset(float degC) = 0;      // idle only
    virtual bool powerDown() = 0;
    virtual bool wakeUp(uint32_t nowMs) = 0;                // not ACKed on the real part
    virtual bool getSerialNumber(uint64_t& serial) = 0;
    // The settings its accuracy rests on. Idle only; false when not read.
    virtual bool getAutomaticSelfCalibration(bool& on) { (void)on; return false; }
    virtual bool getTemperatureOffset(float& degC) { (void)degC; return false; }
    // Answers that arrived with a bad CRC, since start.
    virtual uint32_t crcFailures() const { return 0; }
};
