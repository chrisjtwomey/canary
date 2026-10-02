#pragma once
#include <cstdint>

#include "sensors/Readings.h"

// How many BME688 cycles a mean holds: all of them, and those whose index
// counted.
struct Bme688Samples {
    uint16_t cycles;
    uint16_t iaq;
    uint16_t staticIaq;
};

// The mean of the BME688 cycles between two readings. Each value counts only
// its good cycles: the gas resistance those whose heater reached its target,
// each index those at kCountedAccuracy or above. A value with no good cycle
// is the newest cycle's, so a page can still say why it is not shown.
class Bme688Mean {
public:
    void add(const Bme688Data& cycle);
    // The mean of the cycles added, the newest of them, and the counts; then
    // empty. False when none was added.
    bool take(Bme688Data& mean, Bme688Data& newest, Bme688Samples& n);

    // The pages show an index only at this accuracy (docs/pages.md).
    static const uint8_t kCountedAccuracy = 3;

private:
    Bme688Data newest_ = {};
    uint16_t   cycles_ = 0, gasN_ = 0, iaqN_ = 0, staticIaqN_ = 0;
    double     tempSum_ = 0, pressureSum_ = 0, rhSum_ = 0, gasSum_ = 0, iaqSum_ = 0,
               staticIaqSum_ = 0;
    uint8_t    iaqAccuracy_ = 0, staticIaqAccuracy_ = 0;
};
