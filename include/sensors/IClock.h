#pragma once
#include <cstdint>

// The clock SensorSuite reads and waits on. Injected so the sampling
// sequence can run in host tests: the datasheet timings are real waits
// (13 ms for an SHTC3 conversion, ~140 ms for a BME688 cycle) and a test
// cannot afford them.
class IClock {
public:
    virtual ~IClock() {}
    virtual uint32_t millis() const = 0;
    virtual void waitMs(uint32_t ms) = 0;
};

#if !defined(NATIVE)
#include <Arduino.h>

// On ESP32 ::delay() yields to the scheduler, so waiting here does not
// starve WiFi.
class ArduinoClock : public IClock {
public:
    uint32_t millis() const override { return ::millis(); }
    void waitMs(uint32_t ms) override { ::delay(ms); }
};
#endif
