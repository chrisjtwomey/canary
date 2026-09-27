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

// Delays until `ms` milliseconds have passed on the millisecond clock, not
// until one delay of `ms` returns: while the chip light-sleeps a delay can
// return early by that clock (up to 51 ms short of a two-second wait on the
// dock), and a sensor read before its conversion time fails.
template <typename MillisFn, typename DelayFn>
inline void delayForMs(uint32_t ms, MillisFn millis, DelayFn delay) {
    const uint32_t start = millis();
    for (uint32_t left = ms; left != 0;) {
        delay(left);
        const uint32_t passed = millis() - start;
        if (passed >= ms) return;
        left = ms - passed;
    }
}

#if !defined(NATIVE)
#include <Arduino.h>

// On ESP32 ::delay() yields to the scheduler, so waiting here does not
// starve WiFi.
class ArduinoClock : public IClock {
public:
    uint32_t millis() const override { return ::millis(); }
    void waitMs(uint32_t ms) override {
        delayForMs(ms, [] { return ::millis(); }, [](uint32_t m) { ::delay(m); });
    }
};
#endif
