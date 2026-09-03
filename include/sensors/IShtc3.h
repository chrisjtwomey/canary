#pragma once
#include <cstdint>
#include "Readings.h"

// Sensirion SHTC3, as the firmware drives it. Times are the caller's
// millisecond clock so the mock and the tests can run without millis().
class IShtc3 {
public:
    virtual ~IShtc3() {}
    virtual bool begin(uint32_t nowMs) = 0;          // wake, check ID, soft reset, sleep
    virtual bool wakeup(uint32_t nowMs) = 0;         // 0x3517; ready after 240 us
    virtual bool sleep() = 0;                        // 0xB098
    // Start a measurement. Normal mode takes 12.1 ms, low-power 0.8 ms; the
    // part NACKs (returns false) if it is asleep.
    virtual bool measure(uint32_t nowMs, bool lowPower) = 0;
    // Read the result. False until the measurement time has elapsed.
    virtual bool read(uint32_t nowMs, Shtc3Data& out) = 0;
    virtual uint16_t readId() = 0;                   // (id & 0x083F) == 0x0807 for an SHTC3
};
