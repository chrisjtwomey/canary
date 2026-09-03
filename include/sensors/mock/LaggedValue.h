#pragma once
#include <cstdint>

// A reading that trails what it is measuring, the way a real sensing element
// does. Sensirion and Bosch quote this as tau63: the time to cover 63% of a
// step change.
//
// Two uses in the mocks, both first-order:
//   - a reading following the room (tau63 from the datasheet)
//   - self-heating rising from nothing after power-on toward its steady
//     offset, which is why a cold device reads low for the first few minutes
//
// The first update adopts its target rather than ramping to it: a device that
// has been sitting in the room is already at room temperature. Use primeAt()
// for the self-heating case, where the starting value is known and is not the
// target.
class LaggedValue {
public:
    explicit LaggedValue(float tauSeconds) : tau_(tauSeconds) {}

    // Advance to `nowMs` and return the new reading.
    float update(float target, uint32_t nowMs);

    // Start at `value` instead of adopting the first target.
    void primeAt(float value, uint32_t nowMs);

    float value() const { return value_; }
    bool primed() const { return primed_; }
    void reset() { primed_ = false; }

private:
    float tau_;
    float value_ = 0.0f;
    uint32_t lastMs_ = 0;
    bool primed_ = false;
};
