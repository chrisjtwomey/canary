#pragma once
#include <cstdint>
#include "Readings.h"

// Plantower PMSA003I on the Adafruit breakout. It has no I2C commands: the
// host reads a 32-byte frame the sensor keeps updated, and the SET pin
// (a GPIO from the Inkplate) stops and starts the fan.
class IPmsa003i {
public:
    virtual ~IPmsa003i() {}
    virtual bool begin(uint32_t nowMs) = 0;
    // SET pin. High runs the fan; low sleeps the module and, on the Adafruit
    // board, its 5 V charge pump. Readings are unreliable for 30 s after
    // the fan restarts.
    virtual void setEnabled(bool on, uint32_t nowMs) = 0;
    // One 32-byte I2C read. False when the module does not answer (asleep,
    // or still booting).
    virtual bool readFrame(uint32_t nowMs, uint8_t out[32]) = 0;
    // Decode a frame. False on a bad start word, length or checksum.
    static bool parseFrame(const uint8_t frame[32], PmData& out);
    // True once the fan has run long enough for the data to be trusted.
    virtual bool stable(uint32_t nowMs) const = 0;
    // Whether SET is connected. False means the fan runs whenever the board
    // has power and setEnabled() cannot change that.
    virtual bool setLineWired() const = 0;
};
