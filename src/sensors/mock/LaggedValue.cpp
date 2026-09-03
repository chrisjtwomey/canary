#include "sensors/mock/LaggedValue.h"
#include <cmath>

void LaggedValue::primeAt(float value, uint32_t nowMs) {
    value_ = value;
    lastMs_ = nowMs;
    primed_ = true;
}

float LaggedValue::update(float target, uint32_t nowMs) {
    if (!primed_) {
        primeAt(target, nowMs);
        return value_;
    }
    // Unsigned subtraction, so a millis() rollover still gives the elapsed time.
    uint32_t elapsed = nowMs - lastMs_;
    lastMs_ = nowMs;
    if (elapsed == 0 || tau_ <= 0.0f) return value_;

    float alpha = 1.0f - expf(-(elapsed / 1000.0f) / tau_);
    value_ += (target - value_) * alpha;
    return value_;
}
